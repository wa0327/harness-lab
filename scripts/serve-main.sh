#!/usr/bin/env bash
# 單一模型模式：給 Codex、OpenCode、Cline、Claude Code、Pi(models.json) 用
# 端點：OpenAI /v1/chat/completions、/v1/responses，Anthropic /v1/messages
set -euo pipefail
source "$(dirname "$0")/../env.sh"
[[ -n "$MAIN_FILE" ]] || { echo "MODEL=$MODEL 是遠端模型（$MAIN_URL），不在本機啟動，直接用 harness 連過去" >&2; exit 1; }
unset LLAMA_API_KEY   # 這是給 Pi 的；llama-server 也會讀同名變數當自己的 key，伺服器的 key 一律由 --api-key 傳入

exec "$LLAMA_BIN/llama-server" \
  -m "$MODELS_DIR/$MAIN_FILE" --alias "$MAIN_ALIAS" \
  --host "$HOST" --port "$MAIN_PORT" \
  --api-key "$API_KEY" \
  -ngl 999 --n-cpu-moe "$N_CPU_MOE" --fit off \
  -c "$CTX" -ctk "$KV_TYPE" -ctv "$KV_TYPE" -fa on \
  -b "$BATCH" -ub "$UBATCH" -lm "$LOAD_MODE" -t "$THREADS" \
  --jinja \
  --ctx-checkpoints 32 --checkpoint-min-step 0 \
  "$@"
