#!/usr/bin/env bash
# 在專案內安裝工具：Python venv（hf CLI）、npm 套件（Pi、Codex），並放好各 harness 的設定
set -euo pipefail
source "$(dirname "$0")/../env.sh"
cd "$LAB_DIR"

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -U pip huggingface_hub

npm install --ignore-scripts --no-fund --no-audit

# 設定檔：只在不存在時複製，避免覆蓋 harness 自己寫回的內容
mkdir -p "$PI_CODING_AGENT_DIR" "$CODEX_HOME"
[[ -f "$PI_CODING_AGENT_DIR/models.json" ]] || cp configs/pi/models.json "$PI_CODING_AGENT_DIR/"
[[ -f "$CODEX_HOME/config.toml" ]] || cp configs/codex/config.toml "$CODEX_HOME/"

# 已存在的設定：補上讀 $API_KEY 的設定，其它內容不動
python3 -I -c '
import json, sys
p = sys.argv[1]; d = json.load(open(p))
prov = d.get("providers", {}).get("harness-lab")
if prov is not None and prov.get("apiKey") != "$API_KEY":
    prov["apiKey"] = "$API_KEY"
    json.dump(d, open(p, "w"), ensure_ascii=False, indent=2); open(p, "a").write("\n")
' "$PI_CODING_AGENT_DIR/models.json"
grep -q '^env_key = "API_KEY"' "$CODEX_HOME/config.toml" \
  || sed -i '/^api_key = /d; /^wire_api = /a env_key = "API_KEY"' "$CODEX_HOME/config.toml"

echo "hf:    $(hf version 2>/dev/null || hf --version)"
echo "pi:    $(pi --version)"
echo "codex: $(codex --version)"
