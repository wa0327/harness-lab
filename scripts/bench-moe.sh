#!/usr/bin/env bash
# 掃描 --n-cpu-moe，找出 VRAM 放得下的最小值（越小越快，太小會 OOM）
# 用法：scripts/bench-moe.sh [N...]   例：scripts/bench-moe.sh 36 34 32 30
# 其他參數沿用 env.sh（UBATCH、KV_TYPE、LOAD_MODE、THREADS…），可用環境變數覆寫
set -euo pipefail
source "$(dirname "$0")/../env.sh"

values=("${@:-40 38 36 34 32 30 28 26}")
read -r -a values <<< "${values[*]}"
PP="${PP:-8192}"   # 模擬 agent 每回合送出的長前綴
TG="${TG:-128}"

mkdir -p "$LAB_DIR/results"
out="$LAB_DIR/results/bench-$(hostname)-$(date +%Y%m%d-%H%M).md"
{
  echo "# n-cpu-moe 掃描 $(hostname) $(date '+%F %T')"
  echo
  echo "- GPU: $(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader)"
  echo "- llama.cpp: $LLAMA_BUILD (CUDA $LLAMA_CUDA)"
  echo "- 模型: $MAIN_FILE"
  echo "- 參數: -b $BATCH -ub $UBATCH -ctk/-ctv $KV_TYPE -lm $LOAD_MODE -t $THREADS -p $PP -n $TG"
  echo
} > "$out"

for n in "${values[@]}"; do
  echo "== --n-cpu-moe $n" | tee -a "$out"
  if ! llama-bench -m "$MODELS_DIR/$MAIN_FILE" \
      -ngl 999 --n-cpu-moe "$n" -fa on -ctk "$KV_TYPE" -ctv "$KV_TYPE" \
      -b "$BATCH" -ub "$UBATCH" -lm "$LOAD_MODE" -t "$THREADS" \
      -p "$PP" -n "$TG" -r 2 -o md 2>>"$out.log" | tee -a "$out"; then
    echo "失敗（多半是 VRAM 不足），停止往下掃" | tee -a "$out"
    break
  fi
  echo >> "$out"
done
echo "結果：$out"
