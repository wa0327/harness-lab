#!/usr/bin/env bash
# harness-lab 的 check（Teamind TM-430）：簽入的 shell 腳本跑 bash -n、Python 只做語法檢查（不寫 __pycache__），
# 不跑 evals/ 的題目（那是受測 agent 的任務，有的故意留了 bug）。最後跑 Teamind 的資安檢查（經 .teamind/root）。
set -euo pipefail
cd "$(dirname "$0")"
git ls-files -z -- '*.sh' | xargs -0 -r -n1 bash -n
git ls-files -z -- '*.py' ':!evals/' | xargs -0 -r python3 -I -c '
import ast, sys
for f in sys.argv[1:]:
    ast.parse(open(f, encoding="utf-8").read(), f)
'
python3 -I .teamind/root/tools/check_secrets.py
echo "check: ok"
