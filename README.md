# harness-lab

在 8GB VRAM 的 Linux 筆電上跑本地 LLM，接上各種 agent harness（Pi、Codex、OpenCode、Qwen Code、VS Code 擴充…）測試兼日常使用。

**原則：所有東西都在本目錄內**，包括 llama.cpp 執行檔、模型、Python venv、npm 套件、各 harness 的設定與快取。刪掉這個目錄就清乾淨，不會動到家目錄的 `~/.codex`、`~/.pi`、`~/.qwen`、`~/.config/opencode` 等。

## 組合

| 角色 | 選擇 | 位置 |
|---|---|---|
| 推論引擎 | llama.cpp `llama-server`（預編譯 CUDA 13.4 版，固定 build） | `vendor/llama.cpp/` |
| 主模型 | Qwen3.6-35B-A3B，Unsloth UD-Q4_K_XL（22.4GB），MoE 專家大多放系統 RAM | `models/` |
| Tab 補全 | Qwen2.5-Coder-1.5B Q8_0（FIM） | `models/` |
| Harness | Pi、Codex、OpenCode、Qwen Code（npm 裝在專案內） | `node_modules/` |
| 設定 | Pi：`PI_CODING_AGENT_DIR`；Codex：`CODEX_HOME`；Qwen Code：`QWEN_HOME`；OpenCode：XDG 目錄（由 `bin/opencode` 設定） | `.home/<harness>` |

選型理由見 [reports/](reports/) 的調研報告與 [research_notes/](research_notes/)。

## 在新環境 bootstrap

### 0. 前置需求（系統層級，不在專案內）

| 項目 | 需求 | 檢查 |
|---|---|---|
| NVIDIA 驅動 | 支援 CUDA 13.x（resolute 用 610 版）；太舊的話見步驟 2 | `nvidia-smi` |
| Node.js | 22.19 以上（Pi 的要求） | `node --version` |
| Python | 3.x，含 venv 模組（Ubuntu 可能要 `sudo apt install python3-venv`） | `python3 -m venv --help` |
| 其他 | git、curl、tar | — |
| 磁碟 | 約 25GB（模型 23GB、llama.cpp 約 800MB、npm 套件約 600MB） | `df -h` |

`scripts/setup-tools.sh` 開頭會自動檢查，缺什麼會先列出來。

### 1. Clone 與安裝

```bash
git clone <repo 位址> ~/repos/harness-lab && cd ~/repos/harness-lab
cp env.local.sh.example env.local.sh   # 這台機器自己的設定，不進版控

scripts/setup-tools.sh      # venv（hf）、Pi、Codex、OpenCode、Qwen Code（版本依 package-lock.json），並把 configs/ 範本複製到 .home/
scripts/install-llama.sh    # llama.cpp（固定 build），約 560MB
scripts/get-models.sh       # 主模型與 FIM 模型，約 24GB；設 HF_TOKEN 速率限制較寬鬆
```

### 2. 編輯 `env.local.sh`

- **要讓區網內其它電腦使用時**：同時設 `HOST=0.0.0.0` 和自己的 `API_KEY`，見下方「對外開放與 API key」。預設只聽本機，key 是公開的預設值 `harness-lab`。
- **驅動不支援 CUDA 13**：設 `LLAMA_CUDA=12.8`，再重跑 `scripts/install-llama.sh`。
- 其它可調項目見檔案裡的註解。一律用 `: "${變數:=值}"` 的寫法，命令列上的環境變數才能繼續優先。

### 3. 依硬體調參數

`env.sh` 的預設值是 **resolute**（RTX 4060 Laptop 8GB + 30GB RAM）實測出來的，換了機器要重新量：

```bash
scripts/bench-moe.sh                          # 從 40 往下掃，遇到 OOM 自動停，結果在 logs/bench/
BATCH=4096 UBATCH=4096 scripts/bench-moe.sh   # 也試試大 batch，預填通常較快
```

挑「最小又不 OOM」的 `--n-cpu-moe`，再留一點餘裕（伺服器開 64K context 會比跑分多吃 VRAM），寫進 `env.local.sh`：

```bash
: "${N_CPU_MOE_QWEN:=36}"   # 每個模型各自一個變數，切換 MODEL 時才不會套錯
```

### 4. 啟動與驗證

```bash
scripts/serve-main.sh                          # 終端機 1：主模型
scripts/serve-fim.sh                           # 終端機 2（選用）：Tab 補全

source env.sh                                  # 終端機 3
curl -s -H "Authorization: Bearer $API_KEY" http://127.0.0.1:8080/v1/models
scripts/agent-test.sh pi
scripts/agent-test.sh codex
scripts/agent-test.sh opencode                 # 第一次會下載 ripgrep 到 .home/opencode，多花約 1 分半
scripts/agent-test.sh qwen
scripts/compare-runs.py --latest fix-inventory
```

### 5. 每台機器要重建的狀態

`.home/`（各 harness 的設定、憑證、對話紀錄）和 `logs/` 不進版控，所以不會跟著 clone 過來：

| 項目 | 怎麼做 |
|---|---|
| Pi 走 router | 在 Pi 互動模式執行一次 `/login llama.cpp` 和 `/llama`，模型清單才會存下來 |
| Codex 信任專案 | 第一次在專案裡使用時，Codex 會詢問；同意後它會自己寫回 `.home/codex/config.toml` |
| Codex 走 router | 把 `.home/codex/config.toml` 的 `model` 改成檔名（如 `Qwen3.6-35B-A3B-UD-Q4_K_XL`），或執行時用 `CODEX_MODEL=...` |
| 測試紀錄 | `logs/` 從零開始，各機器互不相通 |

### 設定範本與 `.home/` 的關係

`configs/` 是進版控的**範本**；`.home/` 是 harness **實際讀寫**的設定目錄（`env.sh` 用 `CODEX_HOME`、`PI_CODING_AGENT_DIR` 指過去），裡面還有 harness 自己寫回的狀態，例如 Codex 的信任清單。

`setup-tools.sh` 只在 `.home/` 裡**還沒有**設定檔時才複製範本，之後不會覆蓋。所以範本改了不會自動同步：

| 做法 | 指令 | 影響 |
|---|---|---|
| 整份重設 | `rm .home/codex/config.toml && scripts/setup-tools.sh` | Codex 寫回的狀態會清掉，下次使用時重新詢問 |
| 只改需要的部分 | 直接編輯 `.home/` 裡的檔案 | 保留其他狀態 |
| 不改檔案 | 執行時覆寫，如 `codex -c model='"..."'` | 只對那一次有效 |

Pi 的 `models.json` 不會被 Pi 寫回，整份重設沒有副作用。

| harness | 範本 | 實際設定 |
|---|---|---|
| Pi | `configs/pi/models.json` | `.home/pi/models.json` |
| Codex | `configs/codex/config.toml` | `.home/codex/config.toml` |
| OpenCode | `configs/opencode/opencode.json` | `.home/opencode/config/opencode/opencode.json` |
| Qwen Code | `configs/qwen/settings.json` | `.home/qwen/settings.json` |

OpenCode 沒有 `CODEX_HOME` 那種單一目錄的變數，設定、資料、快取都照 XDG 放。為了不在 `env.sh` 全域改 XDG（會讓 git 等工具讀不到 `~/.config` 下的設定），改由 `bin/opencode` 在執行時把 4 個 XDG 目錄導向 `.home/opencode/`；`env.sh` 把 `bin/` 排在 PATH 最前面。**不要直接執行 `node_modules/.bin/opencode`**，它會寫進家目錄。

Qwen Code 的範本關掉了自動 memory 擷取、memory 整併和工具摘要：這些會在背景另外打模型請求，在本機單一伺服器上會和主任務搶資源（實測關掉後同一題從 32 秒降到 18 秒），也會讓前後幾次測試互相影響。

## 快速開始

裝好之後的日常使用：

```bash
scripts/serve-main.sh       # 啟動主模型，http://127.0.0.1:8080
scripts/serve-fim.sh        # （選用）Tab 補全，http://127.0.0.1:8012
```

### 對外開放與 API key

預設只聽本機（`HOST=127.0.0.1`），`API_KEY` 是 `env.sh` 給的公開預設值 `harness-lab`。它**不是祕密**，只是讓伺服器和各 harness 一律有 key：Pi、Codex、Qwen Code 讀到空字串都會當成缺少憑證（Codex 的 `env_key`、Qwen Code 的 `envKey` 直接報錯；Pi 的自訂 provider 不會把模型標為可用），有了預設值，設定就不用分「有 key／沒 key」兩種。

要讓區網內其它電腦使用時，在 `env.local.sh` **同時**設兩項：

```bash
: "${HOST:=0.0.0.0}"
: "${API_KEY:=你的key}"     # 例如用 openssl rand -hex 16 產生
```

各 harness 的設定**不用改**，都直接讀 `API_KEY`：

| harness | 設定 |
|---|---|
| Pi：`.home/pi/models.json` | `"apiKey": "$API_KEY"` |
| Codex：`.home/codex/config.toml` | `env_key = "API_KEY"` |
| Qwen Code：`.home/qwen/settings.json` | 每個模型的 `"envKey": "API_KEY"` |
| OpenCode：`.home/opencode/config/opencode/opencode.json` | `"apiKey": "{env:API_KEY}"` |

Pi 走 router 時用的 `LLAMA_API_KEY` 也由 `env.sh` 設成同一個值。三支 serve 腳本一律帶 `--api-key "$API_KEY"`。`HOST` 對外開放但 `API_KEY` 還是預設值時，`env.sh` 會發出警告。

以前的版本預設不驗證，舊機器上已經存在的 `.home` 設定（Pi 寫死 `"none"`、Codex 註解掉 `env_key`）會在重跑 `scripts/setup-tools.sh` 時自動改成讀 `API_KEY`。

另開終端機使用 harness：

```bash
source env.sh               # 讓 pi、codex、opencode、qwen、hf、llama-* 指向專案內的版本與設定
pi --model harness-lab/qwen3.6-35b-a3b --thinking off   # 小改動用 off／low 最快；難題再用 medium
codex
opencode                    # 換模型：opencode -m harness-lab/glm-4.7-flash
qwen                        # 換模型：qwen -m glm-4.7-flash
```

OpenCode 和 Qwen Code 都**沒有沙箱**，shell 指令以使用者權限直接執行（Pi 也是）。只有 Codex 有 `workspace-write` 沙箱。

### 切換主模型

`env.sh` 的 `MODEL` 決定主模型：`qwen`（預設，Qwen3.6-35B-A3B）或 `glm`（GLM-4.7-Flash，31B/3B 啟用，UD-Q4_K_XL 17.5GB）。檔名、別名和 `N_CPU_MOE` 都會跟著換：

```bash
MODEL=glm scripts/get-models.sh main
MODEL=glm scripts/serve-main.sh
MODEL=glm pi --model harness-lab/glm-4.7-flash
MODEL=glm scripts/agent-test.sh pi       # 紀錄的標籤會加上 [glm-4.7-flash]
```

整個終端機都要換的話，用 `. env.sh glm`（換回來是 `. env.sh qwen`），之後執行的腳本、`pi`、`codex` 都會跟著用。注意不要打成 `MODEL=glm . env.sh`：bash 會在 source 結束後把 `MODEL` 還原，之後的腳本又會回到 qwen。新增模型時，在 `env.sh` 的 `case` 加一段（`N_CPU_MOE` 照現有寫法讀 `N_CPU_MOE_<名稱>`，讓各機器能在 `env.local.sh` 覆寫），並在 `configs/pi/models.json` 加上取樣參數。

想走 Pi 官方的 router 模式時，改跑 `scripts/serve-router.sh`。router 會依請求的模型名稱（檔名，如 `Qwen3.6-35B-A3B-UD-Q4_K_XL`）自動載入，所以 Codex 等一般用戶端不必先手動載入。Pi 這邊，第一次要在互動模式裡執行 `/login llama.cpp`（key 可留空，會讀 env.sh 匯出的 `LLAMA_API_KEY`，和 `API_KEY` 同值）和 `/llama`，模型清單才會存下來，之後才能用 `pi --model llama.cpp/Qwen3.6-35B-A3B-UD-Q4_K_XL`。resolute 上已經做過這一步。

## 腳本

| 腳本 | 用途 |
|---|---|
| `env.sh` | 所有路徑與參數。優先順序：命令列環境變數（如 `N_CPU_MOE=32 scripts/serve-main.sh`）> `env.local.sh` > 預設值 |
| `env.local.sh.example` | 每台機器設定的範本，複製成 `env.local.sh`（不進版控）後修改 |
| `scripts/serve-main.sh` | 單一模型模式，給 Pi（models.json）、Codex、Cline、Claude Code 等用。提供 OpenAI `/v1/chat/completions`、`/v1/responses` 與 Anthropic `/v1/messages` |
| `scripts/serve-router.sh` | Pi 官方建議的 router 模式（Pi 裡 `/login llama.cpp`、`/llama`、`/model`）。收到請求時自動載入模型，同時最多一個（`--models-max 1`），請求別的模型會把目前的卸載。已驗證 MoE 等參數會傳給 router 載入的模型；模型名稱是檔名 |
| `scripts/serve-fim.sh` | Tab 補全伺服器，port 8012，給 llama.vscode / Continue。context 8K、batch 512 時可以和主模型同時跑（合計 VRAM 7.7GB） |
| `scripts/bench-moe.sh` | `llama-bench` 掃描 `--n-cpu-moe`，結果寫到 `logs/bench/` |
| `scripts/agent-test.sh` | 用 `evals/` 裡的同一題測不同 harness（`pi`、`pi-router`、`codex`、`opencode`、`qwen`），自動驗證並記錄到 `logs/agent-runs.md`，每次的工作目錄與事件紀錄在 `logs/runs/`。`PI_THINKING=off` 可以調 Pi 的思考強度。開始前會檢查 `evals/<題目>` 是否乾淨，結束後若發現 agent 改到原檔就判 FAIL |
| `bin/opencode` | OpenCode 的包裝腳本，把 XDG 目錄導向 `.home/opencode/` |
| `scripts/compare-runs.py` | 比較多次執行的 token、回合數、工具呼叫、程式差異與最終回覆。`--latest fix-inventory` 取每種 harness 最新一次；`--md` 輸出 Markdown |
| `scripts/setup-tools.sh`、`install-llama.sh`、`get-models.sh` | 安裝工具、llama.cpp 與模型，全部放在專案內。`setup-tools.sh` 會先檢查前置需求 |

## 其他 harness 的接法

以下的 `<key>` 都是 `API_KEY` 的值，沒在 `env.local.sh` 改過的話就是 `harness-lab`。從其它電腦連時，把 `127.0.0.1` 換成這台的 IP（伺服器要先對外開放）。

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
| `scripts/`、`bin/`、`configs/`、`evals/` | 腳本、harness 包裝腳本、設定範本、評測題目（每個子目錄一題） | ✅ |
| `reports/`、`research_notes/` | 調研報告、實測總結等人工整理的文件 | ✅ |
| `logs/` | 自動產生的紀錄：跑分輸出、`agent-runs.md`、`runs/`（每次測試的工作目錄）、伺服器 log | ❌ |
| `vendor/`、`models/`、`node_modules/`、`.venv/`、`.cache/`、`.home/` | 工具、模型、快取、各 harness 的設定與憑證 | ❌ |
| `env.local.sh` | 這台機器自己的設定（API key、`N_CPU_MOE` 等） | ❌ |
