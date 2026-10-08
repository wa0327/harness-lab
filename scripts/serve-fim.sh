#!/usr/bin/env bash
# Tab 補全（FIM）伺服器，給 llama.vscode / Continue 用
# 參數取自 llama.vscode 的 Qwen2.5-Coder 1.5B 預設配置，context 與 batch 縮小以便和主模型共存
# 會和主模型分享 VRAM：同時開的話，主模型的 N_CPU_MOE 可能要調高
set -euo pipefail
source "$(dirname "$0")/../env.sh"
unset LLAMA_API_KEY   # 這是給 Pi 的；llama-server 也會讀同名變數當自己的 key，伺服器的 key 一律由 --api-key 傳入

exec "$LLAMA_BIN/llama-server" \
  -m "$MODELS_DIR/$FIM_FILE" \
  --host "$HOST" --port "$FIM_PORT" \
  ${API_KEY:+--api-key "$API_KEY"} \
  -ngl 99 -fa on -ub "$FIM_BATCH" -b "$FIM_BATCH" \
  -c "$FIM_CTX" --cache-reuse 256 \
  "$@"
