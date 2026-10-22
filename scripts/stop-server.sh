#!/usr/bin/env bash
# 停止 serve-*.sh 啟動的伺服器：只停 pid 檔（logs/serve-<名稱>.pid）記的那個程序，不用 pkill，
# 因為同一台主機可能還有別的專案的 llama-server
# 用法：scripts/stop-server.sh <main|fim|router>
set -euo pipefail
source "$(dirname "$0")/../env.sh"

name="${1:-}"
[[ "$name" =~ ^(main|fim|router)$ ]] || { echo "用法：$0 <main|fim|router>" >&2; exit 2; }
f="$(lab_pid_file "$name")"
if ! pid="$(lab_server_pid "$name")"; then
  if [[ -e "$f" ]]; then
    echo "$name 伺服器沒有在執行，移除過時的 $f"
    rm -f "$f"
  else
    echo "$name 伺服器沒有在執行"
  fi
  exit 0
fi

kill "$pid"
for _ in $(seq 60); do
  kill -0 "$pid" 2>/dev/null || break
  sleep 0.5
done
if kill -0 "$pid" 2>/dev/null; then
  echo "$name 伺服器（pid $pid）30 秒內沒有結束，沒有強制停止；確認後可自己 kill -9 $pid" >&2
  exit 1
fi
rm -f "$f"
echo "已停止 $name 伺服器（pid $pid）"
