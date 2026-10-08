#!/usr/bin/env bash
# Router 模式：Pi 官方建議的接法（Pi 裡用 /login llama.cpp、/llama、/model）
# 不帶 -m；router 會掃描 $MODELS_DIR，任何 harness 送出請求時依 model 欄位自動載入
# 已驗證：MoE 卸載等參數會傳給 router 啟動的模型程序；模型名稱是檔名（不含 .gguf）
# --models-max 1：8GB VRAM 同時只放得下一個主模型；必須寫在命令列，寫在 preset INI 裡無效
#   代價：請求別的模型（例如誤填 FIM 模型名稱）會把主模型卸載。FIM 請另用 serve-fim.sh
# context 不跟 MODEL 的 CTX：router 用同一組參數載入任何模型，GLM 在 128K 會 OOM，所以固定 64K（可用 ROUTER_CTX 覆寫）
set -euo pipefail
source "$(dirname "$0")/../env.sh"
[[ -n "$MAIN_FILE" ]] || { echo "MODEL=$MODEL 是遠端模型（$MAIN_URL），不在本機啟動，直接用 harness 連過去" >&2; exit 1; }
unset LLAMA_API_KEY   # 這是給 Pi 的；llama-server 也會讀同名變數當自己的 key，伺服器的 key 一律由 --api-key 傳入

exec "$LLAMA_BIN/llama-server" \
  --models-dir "$MODELS_DIR" --models-max 1 \
  --host "$HOST" --port "$MAIN_PORT" \
  --api-key "$API_KEY" \
  -ngl 999 --n-cpu-moe "$N_CPU_MOE" --fit off \
  -c "${ROUTER_CTX:-65536}" -ctk "$KV_TYPE" -ctv "$KV_TYPE" -fa on \
  -b "$BATCH" -ub "$UBATCH" -lm "$LOAD_MODE" -t "$THREADS" \
  --jinja \
  --ctx-checkpoints 32 --checkpoint-min-step 0 \
  "$@"
