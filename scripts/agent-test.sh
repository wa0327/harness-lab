#!/usr/bin/env bash
# 用同一個題目測不同 harness：複製 evals/<題目> 到 logs/runs/，讓 harness 非互動解題，再自動驗證
# 用法：scripts/agent-test.sh <pi|pi-router|codex|opencode|qwen> [題目]   需要先啟動 scripts/serve-main.sh
set -euo pipefail
source "$(dirname "$0")/../env.sh"

harness="${1:?用法：scripts/agent-test.sh <pi|pi-router|codex|opencode|qwen> [題目]}"
task="${2:-fix-inventory}"
TIMEOUT="${TIMEOUT:-1800}"
PI_THINKING="${PI_THINKING:-}"   # 例：PI_THINKING=off scripts/agent-test.sh pi
CODEX_MODEL="${CODEX_MODEL:-}"   # 例：接 router 時 CODEX_MODEL=Qwen3.6-35B-A3B-UD-Q4_K_XL

# run 目錄在 harness-lab 的 git repo 裡，agent 有可能跑去改題目原檔。原檔不乾淨就不跑，免得複製到被改過的版本
evals_state() { git -C "$LAB_DIR" status --porcelain --untracked-files=all -- "evals/$task"; }
if [[ -n "$(evals_state)" ]]; then
  echo "evals/$task 有未提交的改動，先還原（git checkout -- evals/$task，並刪掉多出來的檔案）再跑：" >&2
  evals_state >&2; exit 1
fi

run="$LOG_DIR/runs/$task-$harness-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$run"
cp -a "$LAB_DIR/evals/$task/." "$run/"
prompt="$(cat "$run/PROMPT.md")"
before="$(sha256sum "$run"/test_*.py)"

# 每次執行留下：agent.jsonl（結構化事件，給 compare-runs.py）、agent.stderr、final.md（最終回覆）、meta.json
start=$(date +%s)
set +e
case "$harness" in
  pi)
    (cd "$run" && timeout "$TIMEOUT" pi -p --mode json --no-session ${PI_THINKING:+--thinking "$PI_THINKING"} --model "harness-lab/$MAIN_ALIAS" "$prompt") \
      > "$run/agent.jsonl" 2> "$run/agent.stderr" ;;
  pi-router)
    # 需要 serve-router.sh，且在 Pi 互動模式跑過一次 /llama（模型清單才會存進 .home/pi）
    (cd "$run" && timeout "$TIMEOUT" pi -p --mode json --no-session ${PI_THINKING:+--thinking "$PI_THINKING"} --model "llama.cpp/${MAIN_FILE%.gguf}" "$prompt") \
      > "$run/agent.jsonl" 2> "$run/agent.stderr" ;;
  codex)
    timeout "$TIMEOUT" codex exec --json -o "$run/final.md" -C "$run" --skip-git-repo-check -s workspace-write --ephemeral ${CODEX_MODEL:+-c "model=\"$CODEX_MODEL\""} "$prompt" \
      > "$run/agent.jsonl" 2> "$run/agent.stderr" ;;
  opencode)
    # OpenCode 以 git 根目錄當專案根目錄，不 git init 的話會是 harness-lab，實測模型因此跑去改了 evals/ 的原檔
    git -C "$run" init -q
    # 沒有沙箱；--auto 讓預設要詢問的權限自動通過（非互動時沒人能回答）；--thinking 才會把思考內容寫進 JSON
    (cd "$run" && timeout "$TIMEOUT" opencode run --format json --auto --thinking -m "harness-lab/$MAIN_ALIAS" "$prompt") \
      > "$run/agent.jsonl" 2> "$run/agent.stderr" ;;
  qwen)
    # 沒有沙箱（-y 自動核准所有工具）；--chat-recording false 相當於 Pi 的 --no-session
    (cd "$run" && QWEN_CODE_SUPPRESS_YOLO_WARNING=1 timeout "$TIMEOUT" qwen -o stream-json -y --chat-recording false -m "$MAIN_ALIAS" "$prompt") \
      > "$run/agent.jsonl" 2> "$run/agent.stderr" ;;
  *) echo "未知的 harness：$harness" >&2; exit 2 ;;
esac
agent_exit=$?
set -e
secs=$(( $(date +%s) - start ))
[[ -f "$run/final.md" ]] || python3 "$LAB_DIR/scripts/compare-runs.py" --final "$run" > "$run/final.md" || true

if (cd "$run" && python3 -m unittest -q) > "$run/verify.log" 2>&1; then verdict=PASS; else verdict=FAIL; fi
if [[ "$before" == "$(sha256sum "$run"/test_*.py)" ]]; then tests_ok=未改; else tests_ok=被改; verdict=FAIL; fi
summary="$(tail -1 "$run/verify.log")"
if [[ -n "$(evals_state)" ]]; then
  # agent 跑出 run 目錄改了題目原檔：run 目錄裡的結果不代表它解了題
  git -C "$LAB_DIR" diff -- "evals/$task" > "$run/escaped.diff"
  verdict=FAIL summary="改到 evals/$task 原檔（見 escaped.diff）"
  echo "警告：$harness 改到了 evals/$task 的原檔，請檢查後還原：git -C $LAB_DIR status evals/$task" >&2
fi
label="$harness${PI_THINKING:+ (thinking=$PI_THINKING)}${CODEX_MODEL:+ (router)}"
[[ "$MODEL" == qwen ]] || label="$label [$MAIN_ALIAS]"   # 預設模型不加，和舊紀錄的標籤一致

python3 -I -c 'import json,sys; k=["harness","label","task","secs","agent_exit","verdict","tests","model"]; json.dump(dict(zip(k,sys.argv[2:])),open(sys.argv[1],"w"),ensure_ascii=False,indent=2)' \
  "$run/meta.json" "$harness" "$label" "$task" "$secs" "$agent_exit" "$verdict" "$tests_ok" "$MAIN_ALIAS"

log="$LOG_DIR/agent-runs.md"
[[ -f "$log" ]] || printf '| 時間 | harness | 題目 | 秒數 | agent 結束碼 | 結果 | 測試檔 | 驗證輸出 | 紀錄 |\n|---|---|---|---|---|---|---|---|---|\n' > "$log"
printf '| %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
  "$(date '+%F %T')" "$label" "$task" "$secs" "$agent_exit" "$verdict" "$tests_ok" "$summary" "${run#$LAB_DIR/}" >> "$log"
echo "$harness $task：$verdict（${secs}s，測試檔$tests_ok）→ $run"
