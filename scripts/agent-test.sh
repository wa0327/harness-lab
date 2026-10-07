#!/usr/bin/env bash
# 用同一個題目測不同 harness：複製 tasks/<task> 到 runs/，讓 harness 非互動解題，再自動驗證
# 用法：scripts/agent-test.sh <pi|pi-router|codex> [task]   需要先啟動 scripts/serve-main.sh
set -euo pipefail
source "$(dirname "$0")/../env.sh"

harness="${1:?用法：scripts/agent-test.sh <pi|pi-router|codex> [task]}"
task="${2:-fix-inventory}"
TIMEOUT="${TIMEOUT:-1800}"
PI_THINKING="${PI_THINKING:-}"   # 例：PI_THINKING=off scripts/agent-test.sh pi
CODEX_MODEL="${CODEX_MODEL:-}"   # 例：接 router 時 CODEX_MODEL=Qwen3.6-35B-A3B-UD-Q4_K_XL

run="$LAB_DIR/runs/$task-$harness-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$run"
cp -a "$LAB_DIR/tasks/$task/." "$run/"
prompt="$(cat "$run/PROMPT.md")"
before="$(sha256sum "$run"/test_*.py)"

start=$(date +%s)
set +e
case "$harness" in
  pi)
    (cd "$run" && timeout "$TIMEOUT" pi -p --no-session ${PI_THINKING:+--thinking "$PI_THINKING"} --model "harness-lab/$MAIN_ALIAS" "$prompt") \
      > "$run/agent.log" 2>&1 ;;
  pi-router)
    # 需要 serve-router.sh，且在 Pi 互動模式跑過一次 /llama（模型清單才會存進 .home/pi）
    (cd "$run" && timeout "$TIMEOUT" pi -p --no-session ${PI_THINKING:+--thinking "$PI_THINKING"} --model "llama.cpp/${MAIN_FILE%.gguf}" "$prompt") \
      > "$run/agent.log" 2>&1 ;;
  codex)
    timeout "$TIMEOUT" codex exec -C "$run" --skip-git-repo-check -s workspace-write --ephemeral ${CODEX_MODEL:+-c "model=\"$CODEX_MODEL\""} "$prompt" \
      > "$run/agent.log" 2>&1 ;;
  *) echo "未知的 harness：$harness" >&2; exit 2 ;;
esac
agent_exit=$?
set -e
secs=$(( $(date +%s) - start ))

if (cd "$run" && python3 -m unittest -q) > "$run/verify.log" 2>&1; then verdict=PASS; else verdict=FAIL; fi
if [[ "$before" == "$(sha256sum "$run"/test_*.py)" ]]; then tests_ok=未改; else tests_ok=被改; verdict=FAIL; fi
summary="$(tail -1 "$run/verify.log")"

log="$LAB_DIR/results/agent-runs.md"
[[ -f "$log" ]] || printf '| 時間 | harness | 題目 | 秒數 | agent 結束碼 | 結果 | 測試檔 | 驗證輸出 | 紀錄 |\n|---|---|---|---|---|---|---|---|---|\n' > "$log"
printf '| %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
  "$(date '+%F %T')" "$harness${PI_THINKING:+ (thinking=$PI_THINKING)}${CODEX_MODEL:+ (router)}" "$task" "$secs" "$agent_exit" "$verdict" "$tests_ok" "$summary" "${run#$LAB_DIR/}" >> "$log"
echo "$harness $task：$verdict（${secs}s，測試檔$tests_ok）→ $run"
