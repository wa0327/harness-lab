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

# 各 harness 的設定（範本只在不存在時複製）
scripts/place-configs.sh

echo "hf:    $(hf version 2>/dev/null || hf --version)"
echo "pi:    $(pi --version)"
echo "codex: $(codex --version)"
echo "opencode: $(opencode --version)"
echo "qwen:  $(qwen --version)"
