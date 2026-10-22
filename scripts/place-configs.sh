#!/usr/bin/env bash
# 放好各 harness 的設定：configs/ 的範本只在不存在時複製，已存在的只把 key 的舊寫法改成讀 API_KEY。
# setup-tools.sh 會呼叫它；主機上的部署不跑 setup-tools.sh（npm 套件由 Teamind 的 node 環境裝），只跑這支（HL-1）
set -euo pipefail
source "$(dirname "$0")/../env.sh"
cd "$LAB_DIR"

# 設定檔：只在不存在時複製，避免覆蓋 harness 自己寫回的內容
opencode_cfg="$LAB_DIR/.home/opencode/config/opencode"
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
