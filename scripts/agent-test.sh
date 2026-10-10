#!/usr/bin/env bash
# 用同一個題目測不同 harness：複製 evals/<題目> 到 logs/runs/<題目>/<harness>/<日期_時間>/，讓 harness 非互動解題，再自動驗證
# 用法：scripts/agent-test.sh [--monitor] [--thinking off] [--model <模型>] <題目> <pi|pi-router|codex|opencode|qwen|harness|claude>   需要先啟動 scripts/serve-main.sh（claude 除外）
# harness 是本專案自製的極簡 harness（harness/ 模組），目前只接本機的 Qwen
# --monitor：執行期間即時顯示 agent 的思考、回覆、工具呼叫與結果（scripts/watch-agent.py）
# --thinking off：關掉模型的思考，各 harness 用各自實測有效的方法（見下方 thinking_cfg）；claude 沒有關法，直接報錯
# --model：qwen、glm、ds4（同 env.sh 的 MODEL，蓋過環境變數），或 luna（見下方）
set -euo pipefail

usage="用法：scripts/agent-test.sh [--monitor] [--thinking off] [--model <模型>] <題目> <pi|pi-router|codex|opencode|qwen|harness|claude>，題目是 evals/ 下的目錄名稱"
monitor="" thinking=""; args=()
while (( $# )); do
  case "$1" in
    --monitor) monitor=1 ;;
    --thinking) thinking="${2:-}"; shift ;;
    --thinking=*) thinking="${1#*=}" ;;
    --model) MODEL="${2:?--model 要接模型名稱}"; shift ;;
    --model=*) MODEL="${1#*=}" ;;
    *) args+=("$1") ;;
  esac
  shift
done
# luna（OpenAI 的 GPT-6 Luna）只有這裡用：只給 Codex，走 Codex 內建的 openai provider 和 ChatGPT 帳號的額度
# （先 source env.sh 再 codex login，登入資料存在 .home/codex）。env.sh 不認得 luna，先拿掉 MODEL 再 source
luna=""; [[ "${MODEL:-}" != luna ]] || { luna=1; unset MODEL; }
source "$(dirname "$0")/../env.sh"
[[ -z "$luna" ]] || MODEL=luna MAIN_PROVIDER=openai MAIN_ALIAS=gpt-6-luna
[[ -z "$thinking" || "$thinking" == off ]] || { echo "--thinking 只支援 off（不加就是 harness 預設的思考設定）" >&2; exit 2; }
task="${args[0]:?$usage}"
harness="${args[1]:?$usage}"
PI_THINKING="${PI_THINKING:-}"   # 例：PI_THINKING=off scripts/agent-test.sh fix-inventory pi
CODEX_MODEL="${CODEX_MODEL:-}"   # 例：接 router 時 CODEX_MODEL=Qwen3.6-35B-A3B-UD-Q4_K_XL
CLAUDE_MODEL=claude-opus-5-5     # claude 是上限標竿：固定用 Anthropic 的雲端模型，不走本地伺服器，不受 MODEL 影響
# SNAPSHOT 題目的快照放哪裡。刻意放在 harness-lab 外面：放在底下時，agent 會從工作目錄的路徑推出上層才是
# 真正的專案，實測 Qwen Code 因此 3 次裡有 2 次跑去審查工作區；搬出去後 3 次都待在快照裡。
# 快照只是從 git 解壓出來的快取，/tmp 被清掉時會自動重建
SNAPSHOT_DIR=/tmp/agent-snapshots

task_dir="$LAB_DIR/evals/$task"
[[ -d "$task_dir" ]] || { echo "沒有這個題目：evals/$task" >&2; exit 2; }
case "$harness" in pi|pi-router|codex|opencode|qwen|harness|claude) ;; *) echo "未知的 harness：$harness" >&2; exit 2 ;; esac
[[ "$harness" != harness || ( -z "$luna" && "$MODEL" == qwen ) ]] || { echo "harness 目前只接本機的 Qwen（MODEL=qwen）" >&2; exit 2; }
# Claude Code 的 alwaysThinkingEnabled=false、CLAUDE_CODE_DISABLE_THINKING=1 實測都關不掉 Opus 5.5 的思考
[[ "$thinking" != off || "$harness" != claude ]] || { echo "claude 沒有關掉思考的方法，不支援 --thinking off" >&2; exit 2; }
# 限時（秒）：命令列的 TIMEOUT 優先，其次是題目目錄的 TIMEOUT 檔，都沒有就 1800。時間到就結束 harness，照常評分
TIMEOUT="${TIMEOUT:-$(cat "$task_dir/TIMEOUT" 2>/dev/null || echo 1800)}"

# 開跑前確認模型伺服器連得到（本機模型要先跑 serve-main.sh；ds4 是按需開機的遠端主機），免得白跑一輪
if [[ -n "$luna" && "$harness" != claude ]]; then
  # luna 走 Codex 的 ChatGPT 登入，沒有可以 curl 的伺服器，改查登入狀態
  [[ "$harness" == codex ]] || { echo "MODEL=luna 只支援 codex（用 ChatGPT 帳號的額度，其他 harness 要 API key）" >&2; exit 2; }
  codex login status 2>&1 | grep -q ChatGPT || {
    echo "Codex 沒有用 ChatGPT 帳號登入：先 source env.sh 再執行 codex login（登入資料存在 .home/codex）" >&2; exit 1; }
elif [[ "$harness" != claude ]]; then
  [[ "$harness" != pi-router || -n "$MAIN_FILE" ]] || { echo "pi-router 只能用本機模型，MODEL=$MODEL 是遠端模型" >&2; exit 2; }
  key="$API_KEY"; [[ "$MAIN_PROVIDER" != ds4 ]] || key="$DS4_API_KEY"
  curl -sf -m 10 -o /dev/null -H "Authorization: Bearer $key" "$MAIN_URL/models" || {
    echo "連不到模型伺服器 $MAIN_URL（MODEL=$MODEL）" >&2; exit 1; }
fi

# run 目錄在 harness-lab 裡，agent 有可能跑出 run 目錄改到題目原檔：開跑前把 evals/<題目> 複製一份到 /tmp，
# 結束時比對，被改過就判 FAIL。不要求原檔已提交，正在寫的新題目也能直接跑。
# SNAPSHOT 題目的內容來自指定的 commit，不從 evals/ 複製，不比對（跑出去新增檔案的情況由結束時的 lab_untracked 抓）
snapshot=""; [[ -f "$task_dir/SNAPSHOT" ]] && snapshot=1
# ISOLATE 題目：agent 在 /tmp 的工作目錄作答，題目檔（模擬器、測試…）複製進去並設成唯讀。跑完把工作目錄複製到
# run 目錄的 output/，再用原檔蓋回題目檔、在那裡跑測試：agent 改了自己那份也影響不到成績，改了照樣判 FAIL。
# 不在 run 目錄作答，是因為 agent 會從路徑推到 harness-lab，看到 logs/runs/ 底下別的 harness 交的答案
# ACCEPT 題目（內容是驗收次數上限）：同樣在 /tmp 作答，但看不到題目檔，只能用 ./accept 送出驗收
# （評分由本腳本做）；次數用完就結束 harness，成績照交卷內容算
isolate=""; [[ -f "$task_dir/ISOLATE" ]] && isolate=1
accept_max=""; [[ -f "$task_dir/ACCEPT" ]] && accept_max="$(cat "$task_dir/ACCEPT")" isolate=1
# 題目檔：評分時一律用原檔蓋回去的那些（PROMPT.md 與標記檔以外的檔案）
task_files=(); while IFS= read -r f; do task_files+=("$f"); done < <(
  cd "$task_dir" && find . -name __pycache__ -prune -o -type f ! -name PROMPT.md ! -name ISOLATE ! -name ACCEPT ! -name SNAPSHOT ! -name TIMEOUT -printf '%P\n' | LC_ALL=C sort)
# harness-lab 裡沒被 .gitignore 排除的未追蹤檔案（logs/、.cache/ 不算），開始和結束時比對，抓 agent 用絕對路徑寫到外面
lab_untracked() { git -C "$LAB_DIR" ls-files --others --exclude-standard | LC_ALL=C sort; }
tmp_dirs=()   # 本次用到的 /tmp 目錄，結束時（包括中途出錯、被中斷）一律刪掉
# 不管怎麼結束（出錯、被 kill、終端機關掉）都先收掉 harness：實測主程序意外結束時，背景的 harness 會繼續跑、
# 一直佔著模型伺服器推理
trap 'declare -F stop_harness > /dev/null && stop_harness; rm -rf "${tmp_dirs[@]}"' EXIT
# --thinking off：伺服器開了 --reasoning off 也不夠，Pi 每個請求都自己帶 enable_thinking=true 蓋過伺服器預設。
# 以下各 harness 的關法都經 logproxy 側錄請求、對 llama-server 實測過：伺服器只認 chat_template_kwargs 的
# enable_thinking=false 和 reasoning effort "none"（minimal、low 照樣思考）
codex_thinking=() harness_thinking=()
if [[ "$thinking" == off ]]; then
  thinking_cfg="$(mktemp -d)"; tmp_dirs+=("$thinking_cfg")
  case "$harness" in
    pi|pi-router) PI_THINKING=off ;;   # 送 enable_thinking=false，取樣參數也自動換成不思考用的
    codex) codex_thinking=(-c 'model_reasoning_effort="none"') ;;   # 送 reasoning.effort=none
    harness) harness_thinking=(--thinking off) ;;   # 送 enable_thinking=false，取樣參數換成不思考用的
    opencode)
      # 疊加一份設定讓這個模型送 reasoning_effort=none（內建的 --variant none 對自訂模型沒作用，什麼都不送）
      printf '{"provider":{"%s":{"models":{"%s":{"options":{"reasoningEffort":"none"}}}}}}\n' "$MAIN_PROVIDER" "$MAIN_ALIAS" > "$thinking_cfg/opencode.json"
      export OPENCODE_CONFIG="$thinking_cfg/opencode.json" ;;
    qwen)
      # Qwen Code 沒有對應的旗標：另給一份系統設定，每個模型的 generationConfig 加 reasoning=false（送 enable_thinking=false）。
      # 設定檔是帶 // 註解行的 JSON，去掉註解行再解析
      python3 -I - "$QWEN_HOME/settings.json" "$thinking_cfg/qwen-system.json" <<'EOF'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
d = json.loads("\n".join(l for l in open(src) if not l.lstrip().startswith("//")))
providers = d["modelProviders"]
for models in providers.values():
    for m in models:
        m.setdefault("generationConfig", {})["reasoning"] = False
json.dump({"modelProviders": providers}, open(dst, "w"), ensure_ascii=False)
EOF
      export QWEN_CODE_SYSTEM_SETTINGS_PATH="$thinking_cfg/qwen-system.json" ;;
  esac
fi
if [[ -z "$snapshot" ]]; then
  task_orig="$(mktemp -d)"; tmp_dirs+=("$task_orig")
  cp -a "$task_dir/." "$task_orig/"
fi

run="$LOG_DIR/runs/$task/$harness/$(date +%Y%m%d_%H%M%S)"
work="$run"   # agent 的工作目錄
if [[ -n "$snapshot" ]]; then
  # 題目就是 harness-lab 本身（例如審查 README）：在 SNAPSHOT 指定 commit 的快照裡工作。
  # 快照每個 commit 只拉一次，存在 $SNAPSHOT_DIR，本身是只有一個 commit 的 git repo（看不到之後的歷史），
  # 各 harness 以 git 根目錄判斷專案根目錄時也會停在這裡。開跑前一律 reset + clean 回到乾淨狀態，
  # 產出寫到快照裡的 output/，跑完再複製到 run 目錄。PROMPT.md 不放進快照，免得 agent 把它當成專案的一部分
  rev="$(git -C "$LAB_DIR" rev-parse --verify "$(cat "$task_dir/SNAPSHOT")^{commit}")"
  work="$SNAPSHOT_DIR/$rev"
  mkdir -p "${work%/*}"
  # 快照是共用的，同時只能有一個 run 在用。先拿鎖再建 run 目錄，拿不到時才不會留下空的 run 目錄（會被當成最新一次）。
  # harness 執行時關掉 fd 9（見下方 case 結尾），免得它留在背景的子程序一直佔著鎖
  exec 9> "$work.lock"
  flock -n 9 || { echo "另一個 run 正在用 $work" >&2; exit 1; }
fi
mkdir -p "$run"
if [[ -n "$snapshot" ]]; then
  if [[ ! -d "$work" ]]; then
    rm -rf "$work.tmp" && mkdir "$work.tmp"
    git -C "$LAB_DIR" archive "$rev" | tar -x -C "$work.tmp"
    git -C "$work.tmp" init -q && git -C "$work.tmp" add -A
    git -C "$work.tmp" -c user.name=harness-lab -c user.email=harness-lab@localhost commit -qm "harness-lab $rev"
    echo /output >> "$work.tmp/.git/info/exclude"
    mv -T "$work.tmp" "$work"
  fi
  git -C "$work" reset -q --hard && git -C "$work" clean -qffdx
  # output/ 是快照裡的真實目錄，不是連到 run 目錄的符號連結，harness 也就不用另外加可寫目錄：
  # 實測 Qwen Code 會從額外目錄的路徑（harness-lab/logs/runs/…）推出上層的專案根目錄並跑過去
  mkdir "$work/output"
else
  cp -a "$task_dir/." "$run/"
fi
if [[ -n "$isolate" ]]; then
  work="$(mktemp -d /tmp/agent-work.XXXXXX)"
  # 暫時保留不刪（debug 用），路徑記在 run 目錄的 tmp-dirs.txt
  echo "$work" > "$run/tmp-dirs.txt"
  if [[ -z "$accept_max" ]]; then
    for f in "${task_files[@]}"; do mkdir -p "$work/$(dirname "$f")" && cp -a "$task_dir/$f" "$work/$f" && chmod a-w "$work/$f"; done
  fi
fi
# 把工作目錄的作答複製到 $1，再用原檔蓋回題目檔（評分一律用原檔）
submission() {
  rm -rf "$1" && mkdir -p "$1" && cp -a "$work/." "$1/" && rm -rf "$1/accept" "$1/.git"
  find "$1" -name __pycache__ -type d -prune -exec rm -rf {} +
  local f; for f in "${task_files[@]}"; do mkdir -p "$1/$(dirname "$f")"; rm -f "$1/$f"; cp "$task_orig/$f" "$1/$f"; done
}
if [[ -n "$accept_max" ]]; then
  # 題目檔不放進工作目錄，./accept 裡也不寫評分檔的路徑：實測 Pi 會照 ./accept 裡的路徑去讀模擬器，
  # 題目寫了不准也照讀。./accept 只在佇列目錄放一張請求單，由 agent-test.sh 本身（在 agent 的程序之外）
  # 評分、寫回結果，次數也由這邊算，agent 改不了。佇列在 /tmp：Codex 的 workspace-write 沙箱只能寫工作目錄和 /tmp
  queue="$(mktemp -d /tmp/agent-accept.XXXXXX)"
  echo "$queue" >> "$run/tmp-dirs.txt"
  mkdir "$run/accept"
  n_accept=0 exam_over=""
  cat > "$work/accept" <<EOF
#!/usr/bin/env bash
# 驗收：送出目前工作目錄的內容評分，最多 $accept_max 次，最後一次跑完考試結束
q=$queue
id=\$\$-\$RANDOM
: > "\$q/req-\$id"
for _ in \$(seq 1800); do   # 最多等 15 分鐘
  [[ -e "\$q/resp-\$id" ]] && { cat "\$q/resp-\$id"; exit 0; }
  sleep 0.5
done
echo "等不到評分結果" >&2; exit 1
EOF
  chmod +x "$work/accept"
  accept_sha="$(sha256sum < "$work/accept")"
fi
# 處理一張驗收請求：作答存成 run 目錄的 accept/<次>/ 並在那裡跑測試，output/ 也換成這一份，結果寫回佇列。
# 輸出裡的 run 目錄路徑先去掉，不讓 agent 知道評分檔在哪
grade_request() {
  local id="${1##*/req-}" msg log sub
  rm -f "$1"
  if (( n_accept >= accept_max )); then
    msg="驗收次數已用完（共 $accept_max 次），考試已結束"
  else
    n_accept=$(( n_accept + 1 ))
    sub="$run/accept/$n_accept" log="$run/accept/accept-$n_accept.log"
    submission "$sub"
    rm -rf "$run/output" && cp -a "$sub" "$run/output"
    (cd "$sub" && python3 -m unittest -q) 2>&1 | sed "s#$sub/##g; s#$run/##g" > "$log"
    msg="$(cat "$log")"
    if (( n_accept < accept_max )); then
      msg+=$'\n'"第 $n_accept 次驗收（共 $accept_max 次），還剩 $(( accept_max - n_accept )) 次"
    else
      msg+=$'\n'"第 $n_accept 次驗收（共 $accept_max 次）：驗收次數用完，考試結束"
      exam_over=1
    fi
  fi
  printf '%s\n' "$msg" > "$queue/resp-$id.tmp" && mv "$queue/resp-$id.tmp" "$queue/resp-$id"
}
prompt="$(cat "$task_dir/PROMPT.md")"
# 題目有 TIMEOUT 檔時把限時告訴 agent，讓它分配時間（沒有的題目維持原本的題目，和舊紀錄可比）
if [[ -f "$task_dir/TIMEOUT" ]]; then
  limit="$(( TIMEOUT / 60 )) 分鐘"; (( TIMEOUT % 60 == 0 )) || limit="$(( TIMEOUT / 60 )) 分 $(( TIMEOUT % 60 )) 秒"
  prompt+=$'\n\n'"本題限時 $limit，時間到會直接結束，以當時工作目錄的內容評分。收尾工作（例如寫說明文件）請預留時間。"
fi
# 實際送出的題目存一份：Claude Code、Codex 的紀錄裡不會有題目，限時那句只有這裡看得到
printf '%s\n' "$prompt" > "$run/prompt.md"
has_tests=$(compgen -G "$run/test_*.py" > /dev/null && echo 1 || true)   # 沒有標準答案的題目不放測試，結果由人工判斷
before="$([[ -z "$has_tests" ]] || sha256sum "$run"/test_*.py)"

# 每次執行留下：agent.jsonl（結構化事件，給 compare-runs.py）、agent.stderr、final.md（最終回覆）、meta.json
untracked_before="$(lab_untracked)"
start=$(date +%s)
run_harness() {
case "$harness" in
  pi)
    (cd "$work" && timeout "$TIMEOUT" pi -p --mode json --no-session ${PI_THINKING:+--thinking "$PI_THINKING"} --model "$MAIN_PROVIDER/$MAIN_ALIAS" "$prompt") \
      > "$run/agent.jsonl" 2> "$run/agent.stderr" ;;
  pi-router)
    # 需要 serve-router.sh，且在 Pi 互動模式跑過一次 /llama（模型清單才會存進 .home/pi）
    (cd "$work" && timeout "$TIMEOUT" pi -p --mode json --no-session ${PI_THINKING:+--thinking "$PI_THINKING"} --model "llama.cpp/${MAIN_FILE%.gguf}" "$prompt") \
      > "$run/agent.jsonl" 2> "$run/agent.stderr" ;;
  codex)
    # 不加 --ephemeral：要讓 Codex 寫 rollout 檔，子 agent 的紀錄才收得到（見下方 collect-subagents.py）
    timeout "$TIMEOUT" codex exec --json -o "$run/final.md" -C "$work" --skip-git-repo-check -s workspace-write -c "model_provider=\"$MAIN_PROVIDER\"" -c "model=\"${CODEX_MODEL:-$MAIN_ALIAS}\"" "${codex_thinking[@]}" "$prompt" \
      > "$run/agent.jsonl" 2> "$run/agent.stderr" ;;
  opencode)
    # OpenCode 以 git 根目錄當專案根目錄，不 git init 的話會是 harness-lab，實測模型因此跑去改了 evals/ 的原檔
    git -C "$work" init -q
    # 沒有沙箱；--auto 讓預設要詢問的權限自動通過（非互動時沒人能回答）；--thinking 才會把思考內容寫進 JSON。
    # OPENCODE_DISABLE_CLAUDE_CODE：不讀 Claude Code 的設定。否則它會把家目錄 ~/.claude/skills/ 的 skills
    # 全列進系統提示（實測 13 個、約 12K 字元），那些不是 OpenCode 自己的，換台機器就沒有
    (cd "$work" && OPENCODE_DISABLE_CLAUDE_CODE=1 timeout "$TIMEOUT" opencode run --format json --auto --thinking -m "$MAIN_PROVIDER/$MAIN_ALIAS" "$prompt") \
      > "$run/agent.jsonl" 2> "$run/agent.stderr" ;;
  qwen)
    # 沒有沙箱（-y 自動核准所有工具）；--chat-recording false 相當於 Pi 的 --no-session
    (cd "$work" && QWEN_CODE_SUPPRESS_YOLO_WARNING=1 timeout "$TIMEOUT" qwen -o stream-json -y --chat-recording false -m "$MAIN_ALIAS" "$prompt") \
      > "$run/agent.jsonl" 2> "$run/agent.stderr" ;;
  harness)
    # 沒有沙箱；事件格式照 Pi，compare-runs.py、watch-agent.py 直接沿用 Pi 的解析。key 用環境變數傳，不放命令列
    (cd "$work" && HARNESS_API_KEY="$key" timeout "$TIMEOUT" python3 -I "$LAB_DIR/harness" --base-url "$MAIN_URL" --model "$MAIN_ALIAS" --ctx "$CTX" "${harness_thinking[@]}" "$prompt") \
      > "$run/agent.jsonl" 2> "$run/agent.stderr" ;;
  claude)
    # 用家目錄裡的 Claude Code 和你的登入，不另外設定。
    # --strict-mcp-config 不載入帳號的 MCP connector（其他 harness 都沒有，而且會在最終回覆提醒授權）；
    # 沒有 stdin 時它會等 3 秒，所以接 /dev/null
    (cd "$work" && timeout "$TIMEOUT" claude -p --output-format stream-json --verbose --model "$CLAUDE_MODEL" \
        --permission-mode bypassPermissions --no-session-persistence --strict-mcp-config "$prompt" < /dev/null) \
      > "$run/agent.jsonl" 2> "$run/agent.stderr" ;;
esac
}
# 本次 run 的 timeout 程序：用環境變數裡的隨機標記認，不沿父子關係找——被 kill 整個程序群組時，
# 中間的子 shell 會先死，timeout 改掛到 init 底下，沿父子關係就找不到了（實測 harness 因此沒被結束）
export AGENT_TEST_ID="$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
harness_pids() {
  local p
  for p in $(pgrep -x timeout); do
    tr '\0' '\n' < "/proc/$p/environ" 2>/dev/null | grep -qxF "AGENT_TEST_ID=$AGENT_TEST_ID" && echo "$p"
  done
  return 0
}
# 對 timeout 送 TERM，由它轉送給執行中的 harness
stop_harness() { local p; for p in $(harness_pids); do kill -TERM "$p" 2>/dev/null; done; return 0; }
set +e
# 一律放背景跑再等它：harness 在 timeout 自己的程序群組裡，收不到終端機的 Ctrl+C，而前景執行時 bash 要等
# harness 結束才處理訊號——實測按 Ctrl+C 要等 harness 自己跑完。現在由 trap 結束 harness，再照常收尾、記錄。
# 0<&0：背景工作預設 stdin 是 /dev/null，維持和前景一樣。
# 9>&-：不讓 harness 繼承快照鎖：鎖跟著 fd 走，背景子程序沒結束的話，下一個 run 會拿不到
run_harness 0<&0 9>&- &
hpid=$!
# --monitor：harness 結束後，監看讀完剩下的事件就自己停
[[ -z "$monitor" ]] || { python3 -I "$LAB_DIR/scripts/watch-agent.py" --pid "$hpid" "$run" 9>&- & wpid=$!; }
interrupted=""
trap 'interrupted=1; stop_harness' INT TERM HUP
while kill -0 "$hpid" 2>/dev/null; do
  if [[ -n "$accept_max" ]]; then
    # ACCEPT 題目：處理驗收請求；最後一次驗收完就結束 harness
    for req in "$queue"/req-*; do [[ -e "$req" ]] && grade_request "$req"; done
    if [[ -n "$exam_over" ]]; then
      sleep 3   # 讓 harness 先收到、記下最後一次驗收的輸出
      stop_harness
      break
    fi
  fi
  sleep 1
done
# wait 被訊號打斷時會提早回來，harness 還沒結束就再等
while :; do wait "$hpid"; agent_exit=$?; kill -0 "$hpid" 2>/dev/null || break; done
# 子 shell 被訊號殺掉時 timeout 可能還在跑：等它把 harness 收掉，最多 15 秒
for _ in {1..15}; do [[ -n "$(harness_pids)" ]] || break; stop_harness; sleep 1; done
trap - INT TERM HUP
[[ -z "$monitor" ]] || wait "$wpid"
set -e
# 子 agent 的紀錄不在 agent.jsonl 裡，從各 harness 的存放位置複製到 run 目錄的 subagents/
python3 -I "$LAB_DIR/scripts/collect-subagents.py" "$harness" "$run" "$work" "$start" || true
if [[ -n "$snapshot" ]]; then
  mkdir -p "$run/output" && cp -a "$work/output/." "$run/output/"
  # 快照裡 output/ 以外的改動下次開跑前會被清掉，先存一份
  changes="$(git -C "$work" status --porcelain --untracked-files=all)"
  [[ -z "$changes" ]] || { echo "$changes"; git -C "$work" diff; } > "$run/snapshot.diff"
fi
vdir="$run"   # 跑驗證的目錄
if [[ -n "$isolate" ]]; then
  # 交卷內容放在 output/（題目檔已用原檔蓋回），驗證就在那裡跑。ACCEPT 驗收用完時是最後一次驗收的那份
  # （已經在 output/；結束 harness 前的幾秒內 agent 可能又改了檔案），其餘情況是工作目錄最後的內容
  [[ -n "${exam_over:-}" ]] || submission "$run/output"
  vdir="$run/output"
  # 工作目錄裡的題目檔被改過或刪掉：成績不受影響（評分用原檔），但照樣判 FAIL
  changed=()
  if [[ -z "$accept_max" ]]; then
    for f in "${task_files[@]}"; do cmp -s "$task_orig/$f" "$work/$f" || changed+=("$f"); done
  fi
  # agent 的紀錄裡出現 run 目錄或題目原檔的路徑＝它跑出工作目錄，找到了評分檔或別的 harness 交的答案
  peeked=""; grep -qF -e "$LOG_DIR/runs" -e "$LAB_DIR/evals" "$run/agent.jsonl" 2>/dev/null && peeked=1
  echo "保留作答目錄 $(tr '\n' ' ' < "$run/tmp-dirs.txt")（debug 用，看完自己刪）" >&2
fi
[[ -z "$accept_max" ]] || { accept_ok=1; [[ "$accept_sha" == "$(sha256sum < "$work/accept" 2>/dev/null)" ]] || accept_ok=""; }
secs=$(( $(date +%s) - start ))
[[ -f "$run/final.md" ]] || python3 "$LAB_DIR/scripts/compare-runs.py" --final "$run" > "$run/final.md" || true

if [[ -z "$has_tests" ]]; then
  verdict=人工 tests_ok=無 summary="沒有自動驗證"
else
  if (cd "$vdir" && python3 -m unittest -q) > "$run/verify.log" 2>&1; then verdict=PASS; else verdict=FAIL; fi
  if [[ "$before" == "$(sha256sum "$run"/test_*.py)" ]]; then tests_ok=未改; else tests_ok=被改; verdict=FAIL; fi
  summary="$(tail -1 "$run/verify.log")"
fi
if [[ -n "$accept_max" ]]; then
  summary="$summary；驗收 $n_accept/$accept_max 次"
  [[ "$n_accept" -lt "$accept_max" ]] || summary="$summary（用完，結束 harness）"
  [[ -n "$accept_ok" ]] || { verdict=FAIL summary="$summary；./accept 被改過或刪掉"; }
fi
if [[ -n "$isolate" ]]; then
  (( ${#changed[@]} == 0 )) || { verdict=FAIL summary="$summary；改了題目檔 ${changed[*]}"; }
  [[ -z "$peeked" ]] || { verdict=FAIL summary="$summary；agent 跑到 harness-lab 的 logs/runs 或 evals（見 agent.jsonl）"; }
fi
[[ -z "$interrupted" ]] || summary="$summary；被中斷（Ctrl+C）"
if [[ -z "$snapshot" ]]; then
  # __pycache__ 不算：在題目目錄跑過 Python 就會產生，不是 agent 改的
  if ! diff -r -x __pycache__ "$task_orig" "$task_dir" > /dev/null 2>&1; then
    # agent 跑出 run 目錄改了題目原檔：run 目錄裡的結果不代表它解了題。原本的內容在 escaped.diff 的 - 那一側
    diff -ruN -x __pycache__ "$task_orig" "$task_dir" > "$run/escaped.diff" || true
    verdict=FAIL summary="改到 evals/$task 原檔（見 escaped.diff）"
    echo "警告：$harness 改到了 evals/$task 的原檔，請照 $run/escaped.diff 還原" >&2
  fi
  rm -rf "$task_orig"
fi
new_files="$(LC_ALL=C comm -13 <(echo "$untracked_before") <(lab_untracked))"
if [[ -n "$new_files" ]]; then
  # 實測 Qwen Code 在快照裡把 output/ 寫成絕對路徑 harness-lab/output/。也可能是你自己在這段時間新增的。
  # 複製一份到 run 目錄的 escaped/，原檔留著讓你檢查後自己刪；已經存在的檔案被改不會被抓到
  echo "$new_files" > "$run/escaped-files.txt"
  mkdir -p "$run/escaped"
  (cd "$LAB_DIR" && echo "$new_files" | xargs -d '\n' cp --parents -t "$run/escaped/") || true
  summary="$summary；harness-lab 多了 $(echo "$new_files" | wc -l) 個檔案，可能是 agent 寫到工作目錄外（見 escaped-files.txt）"
  echo "警告：執行期間 harness-lab 多了以下檔案，可能是 $harness 寫到工作目錄外（已複製到 $run/escaped/）：" >&2
  echo "$new_files" >&2
fi
th="${thinking:-$PI_THINKING}"; [[ "$harness" == pi* || -n "$thinking" ]] || th=""   # PI_THINKING 只對 Pi 有作用
label="$harness${th:+ (thinking=$th)}${CODEX_MODEL:+ (router)}"
model="$MAIN_ALIAS"; [[ "$harness" != claude ]] || model="$CLAUDE_MODEL"
[[ "$MODEL" == qwen || "$harness" == claude ]] || label="$label [$MAIN_ALIAS]"   # 預設模型不加，和舊紀錄的標籤一致

python3 -I -c 'import json,sys; k=["harness","label","task","secs","agent_exit","verdict","tests","model"]; json.dump(dict(zip(k,sys.argv[2:])),open(sys.argv[1],"w"),ensure_ascii=False,indent=2)' \
  "$run/meta.json" "$harness" "$label" "$task" "$secs" "$agent_exit" "$verdict" "$tests_ok" "$model"

log="$LOG_DIR/agent-runs.md"
[[ -f "$log" ]] || printf '| 時間 | harness | 題目 | 秒數 | agent 結束碼 | 結果 | 測試檔 | 驗證輸出 | 紀錄 |\n|---|---|---|---|---|---|---|---|---|\n' > "$log"
printf '| %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
  "$(date '+%F %T')" "$label" "$task" "$secs" "$agent_exit" "$verdict" "$tests_ok" "$summary" "${run#$LAB_DIR/}" >> "$log"
# 通過數：從 verify.log 的「Ran N tests」與最後一行的 failures／errors 算
passed=""
if [[ -f "$run/verify.log" ]]; then
  n_ran=$(grep -oE '^Ran [0-9]+' "$run/verify.log" | grep -oE '[0-9]+' || true)
  n_bad=$(tail -1 "$run/verify.log" | grep -oE '(failures|errors)=[0-9]+' | grep -oE '[0-9]+' | paste -sd+ | bc 2>/dev/null || true)
  [[ -z "$n_ran" ]] || passed="，通過 $(( n_ran - ${n_bad:-0} ))/$n_ran"
fi
echo "$harness $task：$verdict$passed（${secs}s，測試檔$tests_ok）→ $run"
