#!/usr/bin/env bash
# 用同一個題目測不同 harness：複製 evals/<題目> 到 logs/runs/，讓 harness 非互動解題，再自動驗證
# 用法：scripts/agent-test.sh <pi|pi-router|codex> [題目]   需要先啟動 scripts/serve-main.sh
set -euo pipefail
source "$(dirname "$0")/../env.sh"

harness="${1:?用法：scripts/agent-test.sh <pi|pi-router|codex> [題目]}"
task="${2:-fix-inventory}"
TIMEOUT="${TIMEOUT:-1800}"
PI_THINKING="${PI_THINKING:-}"   # 例：PI_THINKING=off scripts/agent-test.sh pi
CODEX_MODEL="${CODEX_MODEL:-}"   # 例：接 router 時 CODEX_MODEL=Qwen3.6-35B-A3B-UD-Q4_K_XL

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
  *) echo "未知的 harness：$harness" >&2; exit 2 ;;
esac
agent_exit=$?
set -e
secs=$(( $(date +%s) - start ))
[[ -f "$run/final.md" ]] || python3 "$LAB_DIR/scripts/compare-runs.py" --final "$run" > "$run/final.md" || true

if (cd "$run" && python3 -m unittest -q) > "$run/verify.log" 2>&1; then verdict=PASS; else verdict=FAIL; fi
if [[ "$before" == "$(sha256sum "$run"/test_*.py)" ]]; then tests_ok=未改; else tests_ok=被改; verdict=FAIL; fi
summary="$(tail -1 "$run/verify.log")"
label="$harness${PI_THINKING:+ (thinking=$PI_THINKING)}${CODEX_MODEL:+ (router)}"

python3 -I -c 'import json,sys; k=["harness","label","task","secs","agent_exit","verdict","tests"]; json.dump(dict(zip(k,sys.argv[2:])),open(sys.argv[1],"w"),ensure_ascii=False,indent=2)' \
  "$run/meta.json" "$harness" "$label" "$task" "$secs" "$agent_exit" "$verdict" "$tests_ok"

log="$LOG_DIR/agent-runs.md"
[[ -f "$log" ]] || printf '| 時間 | harness | 題目 | 秒數 | agent 結束碼 | 結果 | 測試檔 | 驗證輸出 | 紀錄 |\n|---|---|---|---|---|---|---|---|---|\n' > "$log"
printf '| %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
  "$(date '+%F %T')" "$label" "$task" "$secs" "$agent_exit" "$verdict" "$tests_ok" "$summary" "${run#$LAB_DIR/}" >> "$log"
echo "$harness $task：$verdict（${secs}s，測試檔$tests_ok）→ $run"
