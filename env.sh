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
# 主模型用 MODEL 切換（qwen｜glm），各值仍可個別覆寫，例：MODEL=glm scripts/serve-main.sh
# 互動 shell 可直接帶參數：. env.sh glm（腳本 source 時 $1 是腳本自己的參數，所以只認直接 source 的）
# N_CPU_MOE 和模型的層數有關，所以跟著模型走；各機器的值寫在 env.local.sh 的 N_CPU_MOE_<模型>
_LAB_PER_MODEL="MAIN_REPO MAIN_FILE MAIN_ALIAS N_CPU_MOE"
if [[ ${#BASH_SOURCE[@]} -eq 1 && -n "${1:-}" ]]; then
  # 明確指定模型（. env.sh glm）：一律用該模型的值，不沿用 shell 裡既有的
  MODEL="$1"
  unset $_LAB_PER_MODEL
fi
export MODEL="${MODEL:-qwen}"
# 在已 source 過的 shell 裡換 MODEL 時，清掉上一個模型帶進來的值（和上次算出的值不同，代表是手動覆寫，保留）
if [[ -n "${_LAB_MODEL:-}" && "$_LAB_MODEL" != "$MODEL" ]]; then
  for _v in $_LAB_PER_MODEL; do
    _prev="_LAB_$_v"; [[ "${!_v:-}" == "${!_prev:-}" ]] && unset "$_v"
  done
  unset _v _prev
fi
case "$MODEL" in
  qwen)
    _d=(unsloth/Qwen3.6-35B-A3B-GGUF Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf qwen3.6-35b-a3b "${N_CPU_MOE_QWEN:-38}") ;;   # 40 層。resolute 實測：-ub 4096 時 38 是下限（37 OOM），40→38 只快約 2%
  glm)
    _d=(unsloth/GLM-4.7-Flash-GGUF GLM-4.7-Flash-UD-Q4_K_XL.gguf glm-4.7-flash "${N_CPU_MOE_GLM:-38}") ;;   # 47 層（第 0 層不是 MoE）。resolute 實測：-ub 4096 時 38 可用
  *) echo "env.sh：未知的 MODEL=$MODEL（可用 qwen、glm）" >&2; return 1 2>/dev/null || exit 1 ;;
esac
# 沒有 _LAB_MODEL 紀錄卻已經有 MAIN_FILE：多半是從別處繼承來的舊值（例如先 source 舊版 env.sh 才開 VS Code），提醒一下
if [[ -z "${_LAB_MODEL:-}" && -n "${MAIN_FILE:-}" && "$MAIN_FILE" != "${_d[1]}" ]]; then
  echo "env.sh 警告：MAIN_FILE=$MAIN_FILE 不是 MODEL=$MODEL 的預設檔案，沿用既有值。不是刻意的話執行：unset $_LAB_PER_MODEL" >&2
fi
: "${MAIN_REPO:=${_d[0]}}" "${MAIN_FILE:=${_d[1]}}" "${MAIN_ALIAS:=${_d[2]}}" "${N_CPU_MOE:=${_d[3]}}"
unset _d
export MAIN_REPO MAIN_FILE MAIN_ALIAS N_CPU_MOE
export _LAB_MODEL="$MODEL" _LAB_MAIN_REPO="$MAIN_REPO" _LAB_MAIN_FILE="$MAIN_FILE" _LAB_MAIN_ALIAS="$MAIN_ALIAS" _LAB_N_CPU_MOE="$N_CPU_MOE"
export FIM_REPO="${FIM_REPO:-ggml-org/Qwen2.5-Coder-1.5B-Q8_0-GGUF}"
export FIM_FILE="${FIM_FILE:-qwen2.5-coder-1.5b-q8_0.gguf}"

# 伺服器
# 預設只聽本機、不驗證。要開放給區網時，在 env.local.sh 同時設 HOST=0.0.0.0 和 API_KEY
export HOST="${HOST:-127.0.0.1}"
export API_KEY="${API_KEY-}"   # 伺服器的 --api-key；空值 = 不驗證
# 設了 API_KEY 時，.home 裡 Pi、Codex 的設定也要改成讀它（見 README「對外開放與 API key」）
if [[ -z "$API_KEY" && "$HOST" != 127.0.0.1 && "$HOST" != localhost && "$HOST" != ::1 ]]; then
  echo "env.sh 警告：HOST=$HOST 對外開放但沒有設 API_KEY，任何人都能使用這台的模型" >&2
fi
export MAIN_PORT="${MAIN_PORT:-8080}"
export FIM_PORT="${FIM_PORT:-8012}"   # llama.vscode 預設連 8012
export FIM_CTX="${FIM_CTX:-8192}"     # 補全不需長 context；0（原生 32K）會和主模型搶 VRAM 而 OOM
export FIM_BATCH="${FIM_BATCH:-512}"

# 效能參數（resolute 用 scripts/bench-moe.sh 實測後選定，總結見 reports/resolute 實測結果.md）
# N_CPU_MOE 在上面「模型」段，依 MODEL 而定
export CTX="${CTX:-65536}"
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
# Pi 內建 llama.cpp provider（router 模式）在 /login 沒存 key 時讀這個；沒設的話 Pi 自己送佔位值
if [[ -n "$API_KEY" ]]; then export LLAMA_API_KEY="$API_KEY"; else unset LLAMA_API_KEY; fi
export CODEX_HOME="$LAB_DIR/.home/codex"

case ":$PATH:" in
  *":$LAB_DIR/.venv/bin:"*) ;;
  *) export PATH="$LAB_DIR/.venv/bin:$LAB_DIR/node_modules/.bin:$LLAMA_BIN:$PATH" ;;
esac
export LD_LIBRARY_PATH="$LLAMA_BIN${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
