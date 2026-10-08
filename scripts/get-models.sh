#!/usr/bin/env bash
# 下載主模型與 FIM 補全模型到 $MODELS_DIR
# 用法：scripts/get-models.sh [main|fim|all]（預設 all）
set -euo pipefail
source "$(dirname "$0")/../env.sh"

what="${1:-all}"
mkdir -p "$MODELS_DIR"

if [[ "$what" == main || "$what" == all ]]; then
  if [[ -n "$MAIN_FILE" ]]; then
    hf download "$MAIN_REPO" "$MAIN_FILE" --local-dir "$MODELS_DIR"
  else
    echo "MODEL=$MODEL 是遠端模型（$MAIN_URL），不用下載" >&2
    [[ "$what" == all ]] || exit 1
  fi
fi
if [[ "$what" == fim || "$what" == all ]]; then
  hf download "$FIM_REPO" "$FIM_FILE" --local-dir "$MODELS_DIR"
fi
ls -lh "$MODELS_DIR"
