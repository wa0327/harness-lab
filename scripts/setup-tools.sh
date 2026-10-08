#!/usr/bin/env bash
# 在專案內安裝工具：Python venv（hf CLI）、npm 套件（Pi、Codex、OpenCode、Qwen Code），並放好各 harness 的設定
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
.venv/bin/pip install -q -U pip huggingface_hub rich   # rich：watch-agent.py 在終端機呈現 Markdown

npm install --ignore-scripts --no-fund --no-audit
# opencode-ai 的 postinstall 只是把平台對應的執行檔連結到 bin/opencode.exe，--ignore-scripts 時要自己跑。
# 它會執行一次 opencode --version 驗證，所以 XDG 也要先導向 .home/opencode（同 bin/opencode），不然會在家目錄建目錄
oc_home="$LAB_DIR/.home/opencode"
(cd node_modules/opencode-ai && XDG_CONFIG_HOME="$oc_home/config" XDG_DATA_HOME="$oc_home/data" \
  XDG_CACHE_HOME="$oc_home/cache" XDG_STATE_HOME="$oc_home/state" node postinstall.mjs)

# 設定檔：只在不存在時複製，避免覆蓋 harness 自己寫回的內容
opencode_cfg="$oc_home/config/opencode"
mkdir -p "$PI_CODING_AGENT_DIR" "$CODEX_HOME" "$QWEN_HOME" "$opencode_cfg"
[[ -f "$PI_CODING_AGENT_DIR/models.json" ]] || cp configs/pi/models.json "$PI_CODING_AGENT_DIR/"
[[ -f "$CODEX_HOME/config.toml" ]] || cp configs/codex/config.toml "$CODEX_HOME/"
[[ -f "$QWEN_HOME/settings.json" ]] || cp configs/qwen/settings.json "$QWEN_HOME/"
[[ -f "$opencode_cfg/opencode.json" ]] || cp configs/opencode/opencode.json "$opencode_cfg/"

# 已存在的設定：以前預設不驗證，key 的舊寫法（Pi 寫死 "none"、Codex 註解掉 env_key、短暫用過的 CLIENT_API_KEY）
# 一律改成讀 API_KEY（env.sh 保證它有值）。其它內容不動
python3 -I -c '
import json, sys
p = sys.argv[1]; d = json.load(open(p))
prov = d.get("providers", {}).get("harness-lab")
if prov is not None and prov.get("apiKey") in ("none", "$CLIENT_API_KEY"):
    prov["apiKey"] = "$API_KEY"
    json.dump(d, open(p, "w"), ensure_ascii=False, indent=2); open(p, "a").write("\n")
' "$PI_CODING_AGENT_DIR/models.json"
codex_cfg="$CODEX_HOME/config.toml"
sed -i -E 's/^env_key = "CLIENT_API_KEY".*/env_key = "API_KEY"/; /^api_key = /d; /^# 預設伺服器只聽本機、不驗證，所以不送 key。/d' "$codex_cfg"
if ! grep -q '^env_key = ' "$codex_cfg"; then
  sed -i -E 's/^# env_key = "API_KEY".*/env_key = "API_KEY"/' "$codex_cfg"
fi

echo "hf:    $(hf version 2>/dev/null || hf --version)"
echo "pi:    $(pi --version)"
echo "codex: $(codex --version)"
echo "opencode: $(opencode --version)"
echo "qwen:  $(qwen --version)"
