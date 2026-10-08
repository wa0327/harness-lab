#!/usr/bin/env bash
# 測試 Codex 目前連線的 router（backend）是哪個
# 用法：source env.sh && scripts/test-codex-router.sh

set -euo pipefail
source "$(dirname "$0")/../env.sh"

CONFIG="$CODEX_HOME/config.toml"
auth=(-H "Authorization: Bearer $API_KEY")

echo "=== Codex Router 檢查 ==="
echo ""

# 1. 讀取 config.toml 的 model_provider 設定
echo "[1] 連線設定（來自 $CONFIG）"
if [[ -f "$CONFIG" ]]; then
  # 設定裡可能有多組 provider（例如 ds4），只看 model_provider 指定的那組
  mapfile -t cfg < <(python3 -I -c '
import sys, tomllib
c = tomllib.load(open(sys.argv[1], "rb"))
p = c.get("model_provider", "")
s = c.get("model_providers", {}).get(p, {})
for v in (p, s.get("name", ""), s.get("base_url", ""), c.get("model", ""), s.get("wire_api", "")):
    print(v)
' "$CONFIG")
  provider_name="${cfg[1]} (${cfg[0]})" base_url="${cfg[2]}" model="${cfg[3]}" wire_api="${cfg[4]}"
  echo "  provider   = $provider_name"
  echo "  base_url   = $base_url"
  echo "  model      = $model"
  echo "  wire_api   = $wire_api"
else
  echo "  ❌ 找不到 config.toml"
  exit 1
fi
echo ""

# 2. 連線測試：直接 call base_url/models
echo "[2] 連線測試（curl $base_url/models）"
resp=$(curl -s -w "\n%{http_code}" "${auth[@]}" "$base_url/models" 2>&1 || true)
http_code=$(echo "$resp" | tail -1)
body=$(echo "$resp" | sed '$d')

if [[ "$http_code" == "200" ]]; then
  echo "  ✅ HTTP $http_code"
  echo ""
  echo "  回傳的 model 清單："
  echo "$body" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for m in data.get('data', []):
  print(f\"  - {m.get('id', '?')}\")
" 2>/dev/null || echo "  $body"
elif [[ "$http_code" == "401" ]]; then
  echo "  ❌ HTTP 401 — API key 不符（檢查伺服器啟動時的 API_KEY）"
else
  echo "  ❌ HTTP $http_code — router 可能沒在跑"
fi
echo ""

# 3. 實際發一個簡單 request 看回傳哪個 model
# 取 router 實際可用的模型來測
echo "[3] 實際呼叫測試（1 token 的 chat completion）"
actual_model=$(curl -s "${auth[@]}" "$base_url/models" 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data['data'][0]['id'] if data.get('data') else '')
" 2>/dev/null)
[[ -z "$actual_model" ]] && actual_model="$model"
echo "  (用實際模型: $actual_model)"

chat_resp=$(curl -s -w "\n%{http_code}" -X POST "${auth[@]}" "$base_url/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"$actual_model\",
    \"messages\": [{\"role\": \"user\", \"content\": \"Say 'OK' in 1 word.\"}],
    \"max_tokens\": 5
  }" 2>&1 || true)
chat_code=$(echo "$chat_resp" | tail -1)
chat_body=$(echo "$chat_resp" | sed '$d') || true

if [[ "$chat_code" == "200" ]]; then
  used_model=$(echo "$chat_body" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('model', '?'))
" 2>/dev/null)
  echo "  ✅ HTTP $chat_code"
  echo "  used_model = $used_model"
  content=$(echo "$chat_body" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data['choices'][0]['message']['content'] if 'choices' in data else '?')
" 2>/dev/null)
  echo "  response   = $content"
else
  echo "  ❌ HTTP $chat_code"
  echo "$chat_body" | head -5 || true
fi
echo ""
echo "=== 檢查完畢 ==="
