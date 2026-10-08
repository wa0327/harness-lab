# harness-lab 共用環境：所有工具、模型、設定、快取都在本目錄內。
# 互動使用：source env.sh 之後，pi、codex、hf、llama-* 都會指向專案內的版本。
# 任何變數都可以先用環境變數覆寫，例如：N_CPU_MOE=32 scripts/serve-main.sh

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export LAB_DIR
export LOG_DIR="${LOG_DIR:-$LAB_DIR/logs}"   # 自動產生的紀錄，不進版控

# llama.cpp 預編譯版本（固定 build，避免追新版踩到工具呼叫解析的回歸）
export LLAMA_BUILD="${LLAMA_BUILD:-b11469}"
export LLAMA_CUDA="${LLAMA_CUDA:-13.4}"
export LLAMA_BIN="${LLAMA_BIN:-$LAB_DIR/vendor/llama.cpp/current}"

# 模型
export MODELS_DIR="${MODELS_DIR:-$LAB_DIR/models}"
export MAIN_REPO="${MAIN_REPO:-unsloth/Qwen3.6-35B-A3B-GGUF}"
export MAIN_FILE="${MAIN_FILE:-Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf}"
export MAIN_ALIAS="${MAIN_ALIAS:-qwen3.6-35b-a3b}"
export FIM_REPO="${FIM_REPO:-ggml-org/Qwen2.5-Coder-1.5B-Q8_0-GGUF}"
export FIM_FILE="${FIM_FILE:-qwen2.5-coder-1.5b-q8_0.gguf}"

# 伺服器
export HOST="${HOST:-0.0.0.0}"
export API_KEY="${API_KEY-llama-cpp@jack}"   # Pi、Codex 從這個變數讀；API_KEY= 可關閉驗證
export MAIN_PORT="${MAIN_PORT:-8080}"
export FIM_PORT="${FIM_PORT:-8012}"   # llama.vscode 預設連 8012
export FIM_CTX="${FIM_CTX:-8192}"     # 補全不需長 context；0（原生 32K）會和主模型搶 VRAM 而 OOM
export FIM_BATCH="${FIM_BATCH:-512}"

# 效能參數（resolute 用 scripts/bench-moe.sh 實測後選定，總結見 reports/resolute 實測結果.md）
export N_CPU_MOE="${N_CPU_MOE:-38}"   # resolute 實測：-ub 4096 時 38 是下限（37 OOM），40→38 只快約 2%
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
export CODEX_HOME="$LAB_DIR/.home/codex"

case ":$PATH:" in
  *":$LAB_DIR/.venv/bin:"*) ;;
  *) export PATH="$LAB_DIR/.venv/bin:$LAB_DIR/node_modules/.bin:$LLAMA_BIN:$PATH" ;;
esac
export LD_LIBRARY_PATH="$LLAMA_BIN${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
