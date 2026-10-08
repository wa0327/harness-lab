#!/usr/bin/env bash
# 用同一個題目測不同 harness：複製 evals/<題目> 到 logs/runs/<題目>/<harness>/<日期_時間>/，讓 harness 非互動解題，再自動驗證
# 用法：scripts/agent-test.sh <題目> <pi|pi-router|codex|opencode|qwen|claude>   需要先啟動 scripts/serve-main.sh（claude 除外）
set -euo pipefail
source "$(dirname "$0")/../env.sh"

usage="用法：scripts/agent-test.sh <題目> <pi|pi-router|codex|opencode|qwen|claude>，題目是 evals/ 下的目錄名稱"
task="${1:?$usage}"
harness="${2:?$usage}"
TIMEOUT="${TIMEOUT:-1800}"
PI_THINKING="${PI_THINKING:-}"   # 例：PI_THINKING=off scripts/agent-test.sh fix-inventory pi
CODEX_MODEL="${CODEX_MODEL:-}"   # 例：接 router 時 CODEX_MODEL=Qwen3.6-35B-A3B-UD-Q4_K_XL
CLAUDE_MODEL=claude-opus-5-5     # claude 是上限標竿：固定用 Anthropic 的雲端模型，不走本地伺服器，不受 MODEL 影響

task_dir="$LAB_DIR/evals/$task"
[[ -d "$task_dir" ]] || { echo "沒有這個題目：evals/$task" >&2; exit 2; }

# run 目錄在 harness-lab 的 git repo 裡，agent 有可能跑出 run 目錄改到題目原檔，開始和結束時各檢查一次；
# 原檔不乾淨就不跑，免得複製到被改過的版本。
# SNAPSHOT 題目的內容來自指定的 commit，不從 evals/ 複製，不檢查（跑出去新增檔案的情況由結束時的 lab_untracked 抓）
snapshot=""; [[ -f "$task_dir/SNAPSHOT" ]] && snapshot=1
lab_state() { git -C "$LAB_DIR" status --porcelain --untracked-files=all -- "evals/$task"; }
# harness-lab 裡沒被 .gitignore 排除的未追蹤檔案（logs/、.cache/ 不算），開始和結束時比對，抓 agent 用絕對路徑寫到外面
lab_untracked() { git -C "$LAB_DIR" ls-files --others --exclude-standard | LC_ALL=C sort; }
if [[ -z "$snapshot" ]]; then
  state_before="$(lab_state)"
  if [[ -n "$state_before" ]]; then
    echo "evals/$task 有未提交的改動，先還原（git checkout -- evals/$task，並刪掉多出來的檔案）再跑：" >&2
    echo "$state_before" >&2; exit 1
  fi
fi

run="$LOG_DIR/runs/$task/$harness/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$run"
work="$run" extra_dir=""   # agent 的工作目錄；extra_dir 是工作目錄以外還要讓它寫的地方
if [[ -n "$snapshot" ]]; then
  # 題目就是 harness-lab 本身（例如審查 README）：在 SNAPSHOT 指定 commit 的快照裡工作。
  # 快照每個 commit 只拉一次，存在 .cache/snapshots/，本身是只有一個 commit 的 git repo（看不到之後的歷史），
  # 各 harness 以 git 根目錄判斷專案根目錄時也會停在這裡。開跑前一律 reset + clean 回到乾淨狀態，
  # 產出寫到 output/，它是指向 run 目錄的符號連結。PROMPT.md 不放進快照，免得 agent 把它當成專案的一部分
  rev="$(git -C "$LAB_DIR" rev-parse --verify "$(cat "$task_dir/SNAPSHOT")^{commit}")"
  work="$LAB_DIR/.cache/snapshots/$rev"
  mkdir -p "${work%/*}"
  exec 9> "$work.lock"   # 快照是共用的，同時只能有一個 run 在用
  flock -n 9 || { echo "另一個 run 正在用 $work" >&2; exit 1; }
  if [[ ! -d "$work" ]]; then
    rm -rf "$work.tmp" && mkdir "$work.tmp"
    git -C "$LAB_DIR" archive "$rev" | tar -x -C "$work.tmp"
    git -C "$work.tmp" init -q && git -C "$work.tmp" add -A
    git -C "$work.tmp" -c user.name=harness-lab -c user.email=harness-lab@localhost commit -qm "harness-lab $rev"
    echo /output >> "$work.tmp/.git/info/exclude"
    mv -T "$work.tmp" "$work"
  fi
  git -C "$work" reset -q --hard && git -C "$work" clean -qffdx
  extra_dir="$run/output"
  mkdir "$extra_dir" && ln -s "$extra_dir" "$work/output"
else
  cp -a "$task_dir/." "$run/"
fi
prompt="$(cat "$task_dir/PROMPT.md")"
has_tests=$(compgen -G "$run/test_*.py" > /dev/null && echo 1 || true)   # 沒有標準答案的題目不放測試，結果由人工判斷
before="$([[ -z "$has_tests" ]] || sha256sum "$run"/test_*.py)"

# 每次執行留下：agent.jsonl（結構化事件，給 compare-runs.py）、agent.stderr、final.md（最終回覆）、meta.json
untracked_before="$(lab_untracked)"
start=$(date +%s)
set +e
case "$harness" in
  pi)
    (cd "$work" && timeout "$TIMEOUT" pi -p --mode json --no-session ${PI_THINKING:+--thinking "$PI_THINKING"} --model "harness-lab/$MAIN_ALIAS" "$prompt") \
      > "$run/agent.jsonl" 2> "$run/agent.stderr" ;;
  pi-router)
    # 需要 serve-router.sh，且在 Pi 互動模式跑過一次 /llama（模型清單才會存進 .home/pi）
    (cd "$work" && timeout "$TIMEOUT" pi -p --mode json --no-session ${PI_THINKING:+--thinking "$PI_THINKING"} --model "llama.cpp/${MAIN_FILE%.gguf}" "$prompt") \
      > "$run/agent.jsonl" 2> "$run/agent.stderr" ;;
  codex)
    timeout "$TIMEOUT" codex exec --json -o "$run/final.md" -C "$work" ${extra_dir:+--add-dir "$extra_dir"} --skip-git-repo-check -s workspace-write --ephemeral ${CODEX_MODEL:+-c "model=\"$CODEX_MODEL\""} "$prompt" \
      > "$run/agent.jsonl" 2> "$run/agent.stderr" ;;
  opencode)
    # OpenCode 以 git 根目錄當專案根目錄，不 git init 的話會是 harness-lab，實測模型因此跑去改了 evals/ 的原檔
    git -C "$work" init -q
    # 沒有沙箱；--auto 讓預設要詢問的權限自動通過（非互動時沒人能回答）；--thinking 才會把思考內容寫進 JSON
    (cd "$work" && timeout "$TIMEOUT" opencode run --format json --auto --thinking -m "harness-lab/$MAIN_ALIAS" "$prompt") \
      > "$run/agent.jsonl" 2> "$run/agent.stderr" ;;
  qwen)
    # 沒有沙箱（-y 自動核准所有工具）；--chat-recording false 相當於 Pi 的 --no-session
    (cd "$work" && QWEN_CODE_SUPPRESS_YOLO_WARNING=1 timeout "$TIMEOUT" qwen -o stream-json -y --chat-recording false ${extra_dir:+--include-directories "$extra_dir"} -m "$MAIN_ALIAS" "$prompt") \
      > "$run/agent.jsonl" 2> "$run/agent.stderr" ;;
  claude)
    # 用家目錄裡的 Claude Code 和你的登入，不另外設定。--add-dir 可以接多個目錄，要放在其他選項前面，否則會把題目也吃掉；
    # --strict-mcp-config 不載入帳號的 MCP connector（其他 harness 都沒有，而且會在最終回覆提醒授權）；
    # 沒有 stdin 時它會等 3 秒，所以接 /dev/null
    (cd "$work" && timeout "$TIMEOUT" claude -p ${extra_dir:+--add-dir "$extra_dir"} --output-format stream-json --verbose --model "$CLAUDE_MODEL" \
        --permission-mode bypassPermissions --no-session-persistence --strict-mcp-config "$prompt" < /dev/null) \
      > "$run/agent.jsonl" 2> "$run/agent.stderr" ;;
  *) echo "未知的 harness：$harness" >&2; exit 2 ;;
esac
agent_exit=$?
set -e
if [[ -n "$extra_dir" ]]; then
  # 快照裡 output/ 以外的改動下次開跑前會被清掉，先存一份
  changes="$(git -C "$work" status --porcelain --untracked-files=all)"
  [[ -z "$changes" ]] || { echo "$changes"; git -C "$work" diff; } > "$run/snapshot.diff"
fi
secs=$(( $(date +%s) - start ))
[[ -f "$run/final.md" ]] || python3 "$LAB_DIR/scripts/compare-runs.py" --final "$run" > "$run/final.md" || true

if [[ -z "$has_tests" ]]; then
  verdict=人工 tests_ok=無 summary="沒有自動驗證"
else
  if (cd "$run" && python3 -m unittest -q) > "$run/verify.log" 2>&1; then verdict=PASS; else verdict=FAIL; fi
  if [[ "$before" == "$(sha256sum "$run"/test_*.py)" ]]; then tests_ok=未改; else tests_ok=被改; verdict=FAIL; fi
  summary="$(tail -1 "$run/verify.log")"
fi
if [[ -z "$snapshot" && -n "$(lab_state)" ]]; then
  # agent 跑出 run 目錄改了題目原檔：run 目錄裡的結果不代表它解了題
  git -C "$LAB_DIR" diff -- "evals/$task" > "$run/escaped.diff"
  verdict=FAIL summary="改到 evals/$task 原檔（見 escaped.diff）"
  echo "警告：$harness 改到了 evals/$task 的原檔，請檢查後還原：git -C $LAB_DIR status evals/$task" >&2
fi
new_files="$(LC_ALL=C comm -13 <(echo "$untracked_before") <(lab_untracked))"
if [[ -n "$new_files" ]]; then
  # 實測 Qwen Code 在快照裡把 output/ 寫成絕對路徑 harness-lab/output/。也可能是你自己在這段時間新增的。
  # 複製一份到 run 目錄的 escaped/，原檔留著讓你檢查後自己刪；已經存在的檔案被改不會被抓到
  echo "$new_files" > "$run/escaped-files.txt"
  mkdir -p "$run/escaped"
  (cd "$LAB_DIR" && echo "$new_files" | xargs -d '\n' cp --parents -t "$run/escaped/") || true
  summary="$summary；harness-lab 多了 $(echo "$new_files" | wc -l) 個檔案，可能是 agent 寫到工作目錄外（見 escaped-files.txt）"
  echo "警告：執行期間 harness-lab 多了以下檔案，可能是 $harness 寫到工作目錄外（已複製到 $run/escaped/）：" >&2
  echo "$new_files" >&2
fi
label="$harness${PI_THINKING:+ (thinking=$PI_THINKING)}${CODEX_MODEL:+ (router)}"
model="$MAIN_ALIAS"; [[ "$harness" != claude ]] || model="$CLAUDE_MODEL"
[[ "$MODEL" == qwen || "$harness" == claude ]] || label="$label [$MAIN_ALIAS]"   # 預設模型不加，和舊紀錄的標籤一致

python3 -I -c 'import json,sys; k=["harness","label","task","secs","agent_exit","verdict","tests","model"]; json.dump(dict(zip(k,sys.argv[2:])),open(sys.argv[1],"w"),ensure_ascii=False,indent=2)' \
  "$run/meta.json" "$harness" "$label" "$task" "$secs" "$agent_exit" "$verdict" "$tests_ok" "$model"

log="$LOG_DIR/agent-runs.md"
[[ -f "$log" ]] || printf '| 時間 | harness | 題目 | 秒數 | agent 結束碼 | 結果 | 測試檔 | 驗證輸出 | 紀錄 |\n|---|---|---|---|---|---|---|---|---|\n' > "$log"
printf '| %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
  "$(date '+%F %T')" "$label" "$task" "$secs" "$agent_exit" "$verdict" "$tests_ok" "$summary" "${run#$LAB_DIR/}" >> "$log"
echo "$harness $task：$verdict（${secs}s，測試檔$tests_ok）→ $run"
