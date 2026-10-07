#!/usr/bin/env bash
# Router 模式：Pi 官方建議的接法（Pi 裡用 /login llama.cpp、/llama、/model）
# 不帶 -m；router 會掃描 $MODELS_DIR，由 Pi 的 /llama 指令載入模型
# 已驗證：MoE 卸載等參數會傳給 router 啟動的模型程序；模型名稱是檔名（不含 .gguf）
set -euo pipefail
source "$(dirname "$0")/../env.sh"

exec "$LLAMA_BIN/llama-server" \
  --models-dir "$MODELS_DIR" --no-models-autoload \
  --host "$HOST" --port "$MAIN_PORT" \
  -ngl 999 --n-cpu-moe "$N_CPU_MOE" --fit off \
  -c "$CTX" -ctk "$KV_TYPE" -ctv "$KV_TYPE" -fa on \
  -b "$BATCH" -ub "$UBATCH" -lm "$LOAD_MODE" -t "$THREADS" \
  --jinja \
  --ctx-checkpoints 32 --checkpoint-min-step 0 \
  "$@"
