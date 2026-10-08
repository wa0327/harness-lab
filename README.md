# harness-lab

在 8GB VRAM 的 Linux 筆電上跑本地 LLM，接上各種 agent harness（Pi、Codex、VS Code 擴充…）測試兼日常使用。

**原則：所有東西都在本目錄內**，包括 llama.cpp 執行檔、模型、Python venv、npm 套件、各 harness 的設定與快取。刪掉這個目錄就清乾淨，不會動到家目錄的 `~/.codex`、`~/.pi` 等。

## 組合

| 角色 | 選擇 | 位置 |
|---|---|---|
| 推論引擎 | llama.cpp `llama-server`（預編譯 CUDA 13.4 版，固定 build） | `vendor/llama.cpp/` |
| 主模型 | Qwen3.6-35B-A3B，Unsloth UD-Q4_K_XL（22.4GB），MoE 專家大多放系統 RAM | `models/` |
| Tab 補全 | Qwen2.5-Coder-1.5B Q8_0（FIM） | `models/` |
| Harness | Pi、Codex（npm 裝在專案內） | `node_modules/` |
| 設定 | Pi：`PI_CODING_AGENT_DIR`；Codex：`CODEX_HOME` | `.home/pi`、`.home/codex` |

選型理由見 [reports/](reports/) 的調研報告與 [research_notes/](research_notes/)。

## 快速開始

```bash
scripts/setup-tools.sh      # venv（hf CLI）、Pi、Codex，並放好設定檔
scripts/install-llama.sh    # 下載 llama.cpp（約 560MB）
scripts/get-models.sh       # 下載主模型與 FIM 模型（約 24GB）

scripts/bench-moe.sh        # 掃描 --n-cpu-moe（resolute 已跑過，結果已寫進 env.sh）
scripts/serve-main.sh       # 啟動主模型，http://<本機 IP>:8080
scripts/serve-fim.sh        # （選用）Tab 補全，http://<本機 IP>:8012
```

伺服器預設聽 `0.0.0.0`，區網內其它電腦也連得到，所以加了 API key：`env.sh` 的 `API_KEY`（預設 `llama-cpp@jack`），三支 serve 腳本都會帶上 `--api-key`，Pi 和 Codex 的設定也從這個變數讀。其它用戶端送 `Authorization: Bearer <key>` 即可。只在本機用、不想驗證的話，可以改用 `HOST=127.0.0.1 API_KEY= scripts/serve-main.sh` 啟動。

另開終端機使用 harness：

```bash
source env.sh               # 讓 pi、codex、hf、llama-* 指向專案內的版本與設定
pi --model harness-lab/qwen3.6-35b-a3b --thinking off   # 小改動用 off／low 最快；難題再用 medium
codex
```

想走 Pi 官方的 router 模式時，改跑 `scripts/serve-router.sh`。router 會依請求的模型名稱（檔名，如 `Qwen3.6-35B-A3B-UD-Q4_K_XL`）自動載入，所以 Codex 等一般用戶端不必先手動載入。Pi 這邊，第一次要在互動模式裡執行 `/login llama.cpp`（key 填 `API_KEY` 的值）和 `/llama`，模型清單才會存下來，之後才能用 `pi --model llama.cpp/Qwen3.6-35B-A3B-UD-Q4_K_XL`。resolute 上已經做過這一步。

## 腳本

| 腳本 | 用途 |
|---|---|
| `env.sh` | 所有路徑與參數；每個值都可用環境變數覆寫，如 `N_CPU_MOE=32 scripts/serve-main.sh` |
| `scripts/serve-main.sh` | 單一模型模式，給 Pi（models.json）、Codex、Cline、Claude Code 等用。提供 OpenAI `/v1/chat/completions`、`/v1/responses` 與 Anthropic `/v1/messages` |
| `scripts/serve-router.sh` | Pi 官方建議的 router 模式（Pi 裡 `/login llama.cpp`、`/llama`、`/model`）。收到請求時自動載入模型，同時最多一個（`--models-max 1`），請求別的模型會把目前的卸載。已驗證 MoE 等參數會傳給 router 載入的模型；模型名稱是檔名 |
| `scripts/serve-fim.sh` | Tab 補全伺服器，port 8012，給 llama.vscode / Continue。context 8K、batch 512 時可以和主模型同時跑（合計 VRAM 7.7GB） |
| `scripts/bench-moe.sh` | `llama-bench` 掃描 `--n-cpu-moe`，結果寫到 `logs/bench/` |
| `scripts/agent-test.sh` | 用 `evals/` 裡的同一題測不同 harness（`pi`、`pi-router`、`codex`），自動驗證並記錄到 `logs/agent-runs.md`，每次的工作目錄與事件紀錄在 `logs/runs/`。`PI_THINKING=off` 可以調 Pi 的思考強度 |
| `scripts/compare-runs.py` | 比較多次執行的 token、回合數、工具呼叫、程式差異與最終回覆。`--latest fix-inventory` 取每種 harness 最新一次；`--md` 輸出 Markdown |
| `scripts/setup-tools.sh`、`install-llama.sh`、`get-models.sh` | 安裝工具、llama.cpp 與模型，全部放在專案內 |

## 其他 harness 的接法

以下的 `<key>` 都是 `API_KEY` 的值；從其它電腦連時，把 `127.0.0.1` 換成這台的 IP。

- **Cline（VS Code）**：Provider 選 OpenAI Compatible，Base URL `http://127.0.0.1:8080/v1`，API Key 填 `<key>`，Model `qwen3.6-35b-a3b`，開啟 Compact Prompt。
- **llama.vscode（Tab 補全）**：先跑 `scripts/serve-fim.sh`，擴充預設就連 `http://127.0.0.1:8012`，要在擴充設定的 API key 欄位填 `<key>`。
- **Claude Code**：`ANTHROPIC_BASE_URL=http://127.0.0.1:8080 ANTHROPIC_AUTH_TOKEN=<key>`。系統提示約 33k token，以實測約 1,000 tok/s 的預填速度推估，第一回合要等 30 秒以上。尚未實測。

## 注意事項

- llama.cpp 這版已移除 `--no-mmap`，改用 `-lm/--load-mode`。預設用 `auto`（mmap）：RAM 只有 30GB，`none` 會把約 20GB 專家權重全讀進記憶體，比較吃緊。
- 調研時查到 Qwen3.6 在 llama.cpp 上的工具呼叫解析有問題，但在 b11469 上實測正常。`LLAMA_BUILD` 已固定在這版，不要隨意追新版。
- `--ctx-checkpoints 32 --checkpoint-min-step 0` 是為了讓 Qwen3.6 這類混合架構模型能重用快取的 prompt，避免長對話每回合整段重算。實測有效。

## 測試結果（resolute）

- **速度**：預填約 1,160 tok/s、生成約 43 tok/s（`--n-cpu-moe 38`、`-ub 4096`）。
- **解題**：Pi 和 Codex 兩道題全部通過。關掉思考的 Pi 解較難的題目只要 66 秒；開 medium 思考要 3 到 6 分鐘。

詳見 [reports/resolute 實測結果.md](<reports/resolute 實測結果.md>)。

## 目錄

| 目錄 | 內容 | 版控 |
|---|---|---|
| `scripts/`、`configs/`、`evals/` | 腳本、設定範本、評測題目（每個子目錄一題） | ✅ |
| `reports/`、`research_notes/` | 調研報告、實測總結等人工整理的文件 | ✅ |
| `logs/` | 自動產生的紀錄：跑分輸出、`agent-runs.md`、`runs/`（每次測試的工作目錄）、伺服器 log | ❌ |
| `vendor/`、`models/`、`node_modules/`、`.venv/`、`.cache/`、`.home/` | 工具、模型、快取、各 harness 的設定與憑證 | ❌ |
