#!/usr/bin/env bash
# 在專案內安裝工具：Python venv（hf CLI）、npm 套件（Pi、Codex），並放好各 harness 的設定
set -euo pipefail
source "$(dirname "$0")/../env.sh"
cd "$LAB_DIR"

# 前置需求（系統層級，不在專案內安裝）：缺的話先列出來，不要裝到一半才失敗
missing=()
for c in git curl tar python3 node npm; do
  command -v "$c" >/dev/null || missing+=("$c")
done
if command -v node >/dev/null; then
  node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>22||(a===22&&b>=19)?0:1)' \
    || missing+=("Node.js 22.19 以上（目前 $(node --version)）")
fi
if command -v python3 >/dev/null && ! python3 -c 'import venv, ensurepip' 2>/dev/null; then
  missing+=("python3 的 venv 模組（Ubuntu：sudo apt install python3-venv）")
fi
if (( ${#missing[@]} )); then
  printf '缺少前置需求：\n' >&2; printf '  - %s\n' "${missing[@]}" >&2; exit 1
fi
command -v nvidia-smi >/dev/null || echo "警告：找不到 nvidia-smi，llama.cpp 的 CUDA 版需要 NVIDIA 驅動" >&2

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -U pip huggingface_hub

npm install --ignore-scripts --no-fund --no-audit

# 設定檔：只在不存在時複製，避免覆蓋 harness 自己寫回的內容
mkdir -p "$PI_CODING_AGENT_DIR" "$CODEX_HOME"
[[ -f "$PI_CODING_AGENT_DIR/models.json" ]] || cp configs/pi/models.json "$PI_CODING_AGENT_DIR/"
[[ -f "$CODEX_HOME/config.toml" ]] || cp configs/codex/config.toml "$CODEX_HOME/"

# 已存在的設定：短暫用過的 CLIENT_API_KEY 換回 API_KEY；其它內容（包括免 key 的 "none"）不動
python3 -I -c '
import json, sys
p = sys.argv[1]; d = json.load(open(p))
prov = d.get("providers", {}).get("harness-lab")
if prov is not None and prov.get("apiKey") == "$CLIENT_API_KEY":
    prov["apiKey"] = "$API_KEY"
    json.dump(d, open(p, "w"), ensure_ascii=False, indent=2); open(p, "a").write("\n")
' "$PI_CODING_AGENT_DIR/models.json"
sed -i 's/^env_key = "CLIENT_API_KEY".*/env_key = "API_KEY"/; /^api_key = /d' "$CODEX_HOME/config.toml"

echo "hf:    $(hf version 2>/dev/null || hf --version)"
echo "pi:    $(pi --version)"
echo "codex: $(codex --version)"
