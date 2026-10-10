# harness-lab 共用環境：所有工具、模型、設定、快取都在本目錄內。
# 互動使用：source env.sh 之後，pi、codex、hf、llama-* 都會指向專案內的版本。
# 任何變數都可以先用環境變數覆寫，例如：N_CPU_MOE=32 scripts/serve-main.sh

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export LAB_DIR
export LOG_DIR="${LOG_DIR:-$LAB_DIR/logs}"   # 自動產生的紀錄，不進版控

# 這台機器自己的設定（不進版控，範本見 env.local.sh.example）。
# 在下面的預設值之前讀入，所以會蓋過預設值；命令列上的環境變數仍然優先
if [[ -f "$LAB_DIR/env.local.sh" ]]; then
  source "$LAB_DIR/env.local.sh"
fi

# llama.cpp 預編譯版本（固定 build，避免追新版踩到工具呼叫解析的回歸）
export LLAMA_BUILD="${LLAMA_BUILD:-b11469}"
export LLAMA_CUDA="${LLAMA_CUDA:-13.4}"
export LLAMA_BIN="${LLAMA_BIN:-$LAB_DIR/vendor/llama.cpp/current}"

# 模型
export MODELS_DIR="${MODELS_DIR:-$LAB_DIR/models}"
# 主模型用 MODEL 切換（qwen｜glm｜ds4），各值仍可個別覆寫，例：MODEL=glm scripts/serve-main.sh
# 互動 shell 可直接帶參數：. env.sh glm（腳本 source 時 $1 是腳本自己的參數，所以只認直接 source 的）
# N_CPU_MOE 和模型的層數有關，所以跟著模型走；各機器的值寫在 env.local.sh 的 N_CPU_MOE_<模型>
# CTX 也跟著模型走：KV cache 大小依架構差很多，同樣 128K，Qwen3.6 放得下、GLM 會 OOM；可用 CTX_<模型> 覆寫
# MAIN_PROVIDER 是各 harness 設定裡的 provider 名稱：本機的模型都是 harness-lab，遠端的模型各有一組
_LAB_PER_MODEL="MAIN_REPO MAIN_FILE MAIN_ALIAS N_CPU_MOE MAIN_PROVIDER CTX"
if [[ ${#BASH_SOURCE[@]} -eq 1 && -n "${1:-}" ]]; then
  # 明確指定模型（. env.sh glm）：一律用該模型的值，不沿用 shell 裡既有的
  MODEL="$1"
  unset $_LAB_PER_MODEL
fi
export MODEL="${MODEL:-qwen}"
# 在已 source 過的 shell 裡重新 source 時，清掉上次算出的值，好依目前的 MODEL 和 env.local.sh 重算
# （和上次算出的值不同，代表是手動覆寫，保留）
if [[ -n "${_LAB_MODEL:-}" ]]; then
  for _v in $_LAB_PER_MODEL; do
    _prev="_LAB_$_v"; [[ "${!_v:-}" == "${!_prev:-}" ]] && unset "$_v"
  done
  unset _v _prev
fi
case "$MODEL" in
  qwen)
    # 40 層。resolute 實測：-ub 4096 時 38 是下限（37 OOM），40→38 只快約 2%。
    # 128K：混合架構只有部分層有 KV，VRAM 比 64K 多約 1.2GB（共 6.9GB），速度不變
    # （64K 時 Qwen Code 約 32K 就壓縮 context，見 README 的 Qwen Code 注意事項）
    _d=(unsloth/Qwen3.6-35B-A3B-GGUF Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf qwen3.6-35b-a3b "${N_CPU_MOE_QWEN:-38}" harness-lab "${CTX_QWEN:-131072}") ;;
  glm)
    # 47 層（第 0 層不是 MoE）。resolute 實測：-ub 4096 時 38 可用。64K 已用 7.7GB，128K 的 KV 要再多 3.6GB，載入就 OOM
    _d=(unsloth/GLM-4.7-Flash-GGUF GLM-4.7-Flash-UD-Q4_K_XL.gguf glm-4.7-flash "${N_CPU_MOE_GLM:-38}" harness-lab "${CTX_GLM:-65536}") ;;
  ds4)
    # 遠端模型：KK 的 Mac（M5 Max）上的 DeepSeek V4 Flash（284B MoE，Q2），經 Tailscale 連線，按需開機、多人共用。
    # 不在本機下載或啟動，所以沒有檔案、N_CPU_MOE 和 CTX（serve-main.sh 等會擋下）
    _d=("" "" deepseek-v4-flash "" ds4 "") ;;
  *) echo "env.sh：未知的 MODEL=$MODEL（可用 qwen、glm、ds4）" >&2; return 1 2>/dev/null || exit 1 ;;
esac
# 沒有 _LAB_MODEL 紀錄卻已經有 MAIN_FILE：多半是從別處繼承來的舊值（例如先 source 舊版 env.sh 才開 VS Code），提醒一下
if [[ -z "${_LAB_MODEL:-}" && -n "${MAIN_FILE:-}" && "$MAIN_FILE" != "${_d[1]}" ]]; then
  echo "env.sh 警告：MAIN_FILE=$MAIN_FILE 不是 MODEL=$MODEL 的預設檔案，沿用既有值。不是刻意的話執行：unset $_LAB_PER_MODEL" >&2
fi
: "${MAIN_REPO:=${_d[0]}}" "${MAIN_FILE:=${_d[1]}}" "${MAIN_ALIAS:=${_d[2]}}" "${N_CPU_MOE:=${_d[3]}}" "${MAIN_PROVIDER:=${_d[4]}}" "${CTX:=${_d[5]}}"
unset _d
export MAIN_REPO MAIN_FILE MAIN_ALIAS N_CPU_MOE MAIN_PROVIDER CTX
export _LAB_MODEL="$MODEL" _LAB_MAIN_REPO="$MAIN_REPO" _LAB_MAIN_FILE="$MAIN_FILE" _LAB_MAIN_ALIAS="$MAIN_ALIAS" _LAB_N_CPU_MOE="$N_CPU_MOE" _LAB_MAIN_PROVIDER="$MAIN_PROVIDER" _LAB_CTX="$CTX"
export FIM_REPO="${FIM_REPO:-ggml-org/Qwen2.5-Coder-1.5B-Q8_0-GGUF}"
export FIM_FILE="${FIM_FILE:-qwen2.5-coder-1.5b-q8_0.gguf}"

# 伺服器
# 預設只聽本機。要開放給區網時，在 env.local.sh 同時設 HOST=0.0.0.0 和自己的 API_KEY
export HOST="${HOST:-127.0.0.1}"
# 伺服器的 --api-key，各 harness 也都讀它。預設是公開的固定值，不是祕密：只為了讓 key 一定有值
# （Pi、Codex、Qwen Code 讀到空字串會當成缺少憑證），設定就不用分「有 key／沒 key」兩種
LAB_DEFAULT_API_KEY=harness-lab
export API_KEY="${API_KEY:-$LAB_DEFAULT_API_KEY}"
if [[ "$API_KEY" == "$LAB_DEFAULT_API_KEY" && "$HOST" != 127.0.0.1 && "$HOST" != localhost && "$HOST" != ::1 ]]; then
  echo "env.sh 警告：HOST=$HOST 對外開放，但 API_KEY 還是公開的預設值 $LAB_DEFAULT_API_KEY，任何人都能使用這台的模型" >&2
fi
export MAIN_PORT="${MAIN_PORT:-8080}"
export FIM_PORT="${FIM_PORT:-8012}"   # llama.vscode 預設連 8012
# 主模型的 API 位址，給腳本檢查連線用。harness 實際連的位址寫在各自設定的 provider 裡
# （Pi、Codex 的位址欄位不能讀環境變數），改 ds4 的位址時 configs/ 和 .home/ 的設定要一起改
case "$MAIN_PROVIDER" in
  ds4) export MAIN_URL="http://100.82.105.90:8000/v1" ;;
  *)   export MAIN_URL="http://127.0.0.1:$MAIN_PORT/v1" ;;
esac
# ds4 的伺服器不驗證 key，但 harness 需要有值。另用一個變數，免得把這台的 API_KEY 送到別人的伺服器
export DS4_API_KEY="${DS4_API_KEY:-local}"
export FIM_CTX="${FIM_CTX:-8192}"     # 補全不需長 context；0（原生 32K）會和主模型搶 VRAM 而 OOM
export FIM_BATCH="${FIM_BATCH:-512}"

# 效能參數（resolute 用 scripts/bench-moe.sh 實測後選定，總結見 reports/resolute 實測結果.md）
# N_CPU_MOE、CTX 在上面「模型」段，依 MODEL 而定
export BATCH="${BATCH:-4096}"
export UBATCH="${UBATCH:-4096}"   # 實測預填比 2048 快約 22%，生成慢約 4%
export KV_TYPE="${KV_TYPE:-q8_0}"
export LOAD_MODE="${LOAD_MODE:-auto}"   # auto=mmap；none 等同舊版 --no-mmap，但 30GB RAM 下較吃緊
export THREADS="${THREADS:-$(lscpu -p=core,socket | grep -v '^#' | sort -u | wc -l)}"   # 實體核心數

# 各工具的設定與快取導向專案內，不寫進家目錄
export HF_HOME="$LAB_DIR/.cache/huggingface"
export LLAMA_CACHE="$LAB_DIR/.cache/llama.cpp"
export npm_config_cache="$LAB_DIR/.cache/npm"
export PI_CODING_AGENT_DIR="$LAB_DIR/.home/pi"
# Pi 內建 llama.cpp provider（router 模式）在 /login 沒存 key 時讀這個
export LLAMA_API_KEY="$API_KEY"
export CODEX_HOME="$LAB_DIR/.home/codex"
export QWEN_HOME="$LAB_DIR/.home/qwen"
# OpenCode 只認 XDG 目錄：bin/opencode 在執行時導向 .home/opencode，bin/ 排在 PATH 最前面以蓋過 node_modules/.bin

case ":$PATH:" in
  *":$LAB_DIR/bin:"*) ;;
  *) export PATH="$LAB_DIR/bin:$LAB_DIR/.venv/bin:$LAB_DIR/node_modules/.bin:$LLAMA_BIN:$PATH" ;;
esac
export LD_LIBRARY_PATH="$LLAMA_BIN${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
