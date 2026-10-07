#!/usr/bin/env bash
# 單一模型模式：給 Codex、OpenCode、Cline、Claude Code、Pi(models.json) 用
# 端點：OpenAI /v1/chat/completions、/v1/responses，Anthropic /v1/messages
set -euo pipefail
source "$(dirname "$0")/../env.sh"

exec "$LLAMA_BIN/llama-server" \
  -m "$MODELS_DIR/$MAIN_FILE" --alias "$MAIN_ALIAS" \
  --host "$HOST" --port "$MAIN_PORT" \
  -ngl 999 --n-cpu-moe "$N_CPU_MOE" --fit off \
  -c "$CTX" -ctk "$KV_TYPE" -ctv "$KV_TYPE" -fa on \
  -b "$BATCH" -ub "$UBATCH" -lm "$LOAD_MODE" -t "$THREADS" \
  --jinja \
  --ctx-checkpoints 32 --checkpoint-min-step 0 \
  "$@"
