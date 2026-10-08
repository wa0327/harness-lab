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
scripts/agent-test.sh fix-inventory pi
scripts/agent-test.sh fix-inventory codex
scripts/agent-test.sh fix-inventory opencode   # 第一次會下載 ripgrep 到 .home/opencode，多花約 1 分半
scripts/agent-test.sh fix-inventory qwen
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

`configs/` 是進版控的**範本**；`.home/` 是 harness **實際讀寫**的設定目錄（`env.sh` 用 `PI_CODING_AGENT_DIR`、`CODEX_HOME`、`QWEN_HOME` 指過去，OpenCode 由 `bin/opencode` 處理），裡面還有 harness 自己寫回的狀態，例如 Codex 的信任清單。

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

另開終端機使用 harness，各自的用法見下方「使用各 harness」：

```bash
source env.sh               # 讓 pi、codex、opencode、qwen、hf、llama-* 指向專案內的版本與設定
cd ~/某個專案
pi --model harness-lab/qwen3.6-35b-a3b --thinking off
```

### 切換主模型

`env.sh` 的 `MODEL` 決定主模型：`qwen`（預設，Qwen3.6-35B-A3B）、`glm`（GLM-4.7-Flash，31B/3B 啟用，UD-Q4_K_XL 17.5GB），或遠端的 `ds4`（見下方）。檔名、別名和 `N_CPU_MOE` 都會跟著換：

```bash
MODEL=glm scripts/get-models.sh main
MODEL=glm scripts/serve-main.sh
MODEL=glm pi --model harness-lab/glm-4.7-flash
MODEL=glm scripts/agent-test.sh fix-inventory pi   # 紀錄的標籤會加上 [glm-4.7-flash]
```

整個終端機都要換的話，用 `. env.sh glm`（換回來是 `. env.sh qwen`），之後執行的腳本、`pi`、`codex` 都會跟著用。注意不要打成 `MODEL=glm . env.sh`：bash 會在 source 結束後把 `MODEL` 還原，之後的腳本又會回到 qwen。新增模型時，在 `env.sh` 的 `case` 加一段（`N_CPU_MOE` 照現有寫法讀 `N_CPU_MOE_<名稱>`，讓各機器能在 `env.local.sh` 覆寫），並在 `configs/pi/models.json` 加上取樣參數。

#### 遠端模型 `ds4`

`MODEL=ds4` 是朋友 KK 的 Mac（M5 Max）上的 DeepSeek V4 Flash（284B MoE，Q2 量化，ds4.c），經 Tailscale 連到 `http://100.82.105.90:8000/v1`。不在本機下載或啟動，`serve-main.sh`、`get-models.sh main`、`bench-moe.sh` 會直接擋下：

```bash
MODEL=ds4 scripts/agent-test.sh review-readme pi   # 紀錄的標籤會加上 [deepseek-v4-flash]
. env.sh ds4                                       # 整個終端機切過去
```

- **前提**：Tailscale 已接受 kkmacbook-pro 的分享，而且 KK 有開機（按需開機）。`agent-test.sh` 開跑前會先檢查連不連得到。
- **各 harness 的設定是另一組 provider `ds4`**：Pi、Codex 的位址欄位不能讀環境變數，所以位址寫死在四份設定裡；要改位址的話，`configs/` 和 `.home/` 都要改，env.sh 的 `MAIN_URL` 也要一起改。
- **key 用 `DS4_API_KEY`**（預設 `local`）：伺服器不驗證，另用一個變數，免得把這台的 `API_KEY` 送到別人的伺服器。
- **思考**：伺服器認 `reasoning_effort`，`none` 是關掉。Pi 的 `--thinking off`／`low`／`medium`／`high` 都有對應；Codex 的 `model_reasoning_effort` 對它有效。
- **評比時要注意**：GPU 是多人共用的，秒數會受別人影響，不能直接和本機模型比；伺服器日誌看得到所有對話內容。

想走 Pi 官方的 router 模式時，改跑 `scripts/serve-router.sh`。router 會依請求的模型名稱（檔名，如 `Qwen3.6-35B-A3B-UD-Q4_K_XL`）自動載入，所以 Codex 等一般用戶端不必先手動載入。Pi 這邊，第一次要在互動模式裡執行 `/login llama.cpp`（key 可留空，會讀 env.sh 匯出的 `LLAMA_API_KEY`，和 `API_KEY` 同值）和 `/llama`，模型清單才會存下來，之後才能用 `pi --model llama.cpp/Qwen3.6-35B-A3B-UD-Q4_K_XL`。resolute 上已經做過這一步。

## 使用各 harness

共同前提：

1. 主模型伺服器在跑（`scripts/serve-main.sh`）。
2. 終端機先 `source env.sh`。VS Code 等從舊環境繼承了 `MODEL` 的終端機，用 `. env.sh qwen` 明確指定，免得和伺服器上的模型對不起來。
3. `cd` 到要讓 agent 工作的專案目錄再啟動。key 由 `env.sh` 自動帶上，不用另外設定。

### 指令對照

| | Pi | Codex | OpenCode | Qwen Code |
|---|---|---|---|---|
| 互動模式 | `pi --model harness-lab/qwen3.6-35b-a3b` | `codex` | `opencode` | `qwen` |
| 單次執行後結束 | `pi -p --model ... "題目"` | `codex exec "題目"` | `opencode run "題目"` | `qwen "題目"` |
| 帶著題目進互動模式 | `pi --model ... "題目"` | `codex "題目"` | `opencode --prompt "題目"` | `qwen -i "題目"` |
| 換成 GLM | `--model harness-lab/glm-4.7-flash` | `-m glm-4.7-flash` | `-m harness-lab/glm-4.7-flash` | `-m glm-4.7-flash` |
| 換成 ds4（遠端） | `--model ds4/deepseek-v4-flash` | `-c model_provider=ds4 -m deepseek-v4-flash` | `-m ds4/deepseek-v4-flash` | `-m deepseek-v4-flash` |
| 調思考 | `--thinking off` 或 `medium` | 見下方說明 | 見下方說明 | 見下方說明 |
| 接續上次對話 | `-c`（最近一次）、`-r`（挑選） | `codex resume --last`、`codex resume` | `-c`、`-s <id>` | `-c`、`-r` |
| 沙箱 | 無 | `-s read-only`／`workspace-write` | 無 | 無（沒設定 docker） |
| 自動核准 | 不詢問，一律執行 | `--approve-for-me`，或 `-s danger-full-access` | `run` 加 `--auto` | `-y`，或 `--approval-mode auto-edit` |
| 機器可讀輸出 | `--mode json` | `--json` | `--format json` | `-o stream-json` |

換模型時，伺服器也要跑那個模型（`MODEL=glm scripts/serve-main.sh`），見上方「切換主模型」。ds4 是遠端模型，不用啟動伺服器。

### Pi

- **要指定 `--model`**：清單裡有好幾個模型（`pi --list-models` 可以看），不指定的話不一定挑到伺服器上的那個。
- **思考只有 `off` 和 `medium` 兩段**：其他等級在 `models.json` 裡沒有對應，模型不支援。小改動用 `off` 最快，難題再開 `medium`。也可以寫成 `--model harness-lab/qwen3.6-35b-a3b:off`。
- **只想讀、不讓它改檔**：`pi --tools read,grep,find,ls`。
- **沒有沙箱，也不會逐一詢問**：`bash` 以你的權限直接執行，所以只在可以承受的目錄裡用。
- **其他**：互動模式裡 Ctrl+P 切換模型。`--no-session` 不留對話紀錄，`--export <檔案>` 把對話匯出成 HTML。

### Codex

- **預設模型寫在 `.home/codex/config.toml`**，一般直接打 `codex` 就好。
- **每次啟動會警告 `Model metadata ... not found`**：Codex 沒有本地模型的資料，改用預設值，可以忽略。
- **沙箱**：指令在沙箱裡執行，需要超出沙箱時（例如寫工作目錄以外的地方）才會詢問。`codex exec` 預設是唯讀，要讓它改檔得加 `-s workspace-write`，只能寫工作目錄。
- **第一次在某個專案使用時，會詢問要不要信任這個目錄**，同意後會寫回 `.home/codex/config.toml`。
- **思考強度** `model_reasoning_effort`（設定檔或 `-c model_reasoning_effort='"low"'`）**對 llama-server 是否有效還沒驗證**。確定有效的作法是伺服器端關掉思考：`scripts/serve-main.sh --reasoning off`，但這樣所有 harness 都不會思考。
- **改檔方式**：實測中 Codex 一律用 `sed` 或 heredoc 改檔，沒用過 `apply_patch`。小修沒問題，大檔案局部修改時要多檢查。
- **其他**：`codex apply` 把 agent 的改動套到 git 工作目錄，`codex review` 做非互動的程式碼審查。

### OpenCode

- **一定要用 `bin/opencode`**：`source env.sh` 之後打 `opencode` 就是它。不要直接執行 `node_modules/.bin/opencode`，否則設定和資料會寫進家目錄。
- **專案根目錄是 git repo 的根目錄，不是目前的目錄**：在 repo 的子目錄裡啟動時，它還是會讀、改子目錄以外的檔案。實測時它就因此跑去改了 `evals/` 的原檔。只想讓它動某個子目錄的話，在那個子目錄裡另外 `git init`，或乾脆換到 repo 外面。
- **第一次用到搜尋工具會下載 ripgrep**（放到 `.home/opencode/`），大約要等一分半，之後就不會了。
- **思考**：`opencode run --thinking` 會把思考內容顯示出來。`--variant`（思考強度）對 llama-server 是否有效還沒驗證。
- **沒有沙箱**：`bash` 以你的權限直接執行。

### Qwen Code

- **直接加題目是單次執行**：`qwen "題目"` 跑完就結束。要帶著題目繼續互動，用 `qwen -i "題目"`。
- **核准模式** `--approval-mode`：
  - `plan`：只分析，不改檔也不執行指令。
  - `default`：改檔和執行指令前都會詢問。
  - `auto-edit`：改檔自動通過，執行指令前仍會詢問。
  - `yolo`（等同 `-y`）：全部自動通過。

  非互動執行時沒人能回答詢問，要用 `-y`。
- **沒有沙箱**：`-s` 需要 docker 或 podman，這裡沒有設定，所以 `-y` 時 shell 指令以你的權限直接執行。
- **背景功能已在範本裡關掉**：自動 memory 擷取、memory 整併、工具摘要都會在背景另外呼叫模型，在單一本地伺服器上會拖慢主任務。要用的話改 `.home/qwen/settings.json`。
- **其他**：`--chat-recording false` 不留對話紀錄。`--max-wall-time 10m` 限制總時間，適合無人看管時用。

## 腳本

| 腳本 | 用途 |
|---|---|
| `env.sh` | 所有路徑與參數。優先順序：命令列環境變數（如 `N_CPU_MOE=32 scripts/serve-main.sh`）> `env.local.sh` > 預設值 |
| `env.local.sh.example` | 每台機器設定的範本，複製成 `env.local.sh`（不進版控）後修改 |
| `scripts/serve-main.sh` | 單一模型模式，給 Pi（models.json）、Codex、Cline、Claude Code 等用。提供 OpenAI `/v1/chat/completions`、`/v1/responses` 與 Anthropic `/v1/messages` |
| `scripts/serve-router.sh` | Pi 官方建議的 router 模式（Pi 裡 `/login llama.cpp`、`/llama`、`/model`）。收到請求時自動載入模型，同時最多一個（`--models-max 1`），請求別的模型會把目前的卸載。已驗證 MoE 等參數會傳給 router 載入的模型；模型名稱是檔名 |
| `scripts/serve-fim.sh` | Tab 補全伺服器，port 8012，給 llama.vscode / Continue。context 8K、batch 512 時可以和主模型同時跑（合計 VRAM 7.7GB） |
| `scripts/bench-moe.sh` | `llama-bench` 掃描 `--n-cpu-moe`，結果寫到 `logs/bench/` |
| `scripts/agent-test.sh` | `scripts/agent-test.sh <題目> <harness>`：用 `evals/` 裡的同一題測不同 harness（`pi`、`pi-router`、`codex`、`opencode`、`qwen`、`claude`），`claude` 是上限標竿：用家目錄裡的 Claude Code 和你的登入，固定 Opus 5.5，不走本地伺服器，會產生 API 費用（`compare-runs.py` 會列出）。自動驗證並記錄到 `logs/agent-runs.md`，每次的工作目錄與事件紀錄在 `logs/runs/<題目>/<harness>/<日期_時間>/`。`PI_THINKING=off` 可以調 Pi 的思考強度。題目目錄有 `SNAPSHOT`（commit）時（如 `review-readme`），agent 改在 harness-lab 那個 commit 的快照裡工作：快照每個 commit 只拉一次，存在 `.cache/snapshots/`，開跑前一律 reset + clean 回到乾淨狀態，產出寫到快照裡的 `output/`（符號連結到 run 目錄的 `output/`），其他改動存成 run 目錄的 `snapshot.diff`。沒有 `test_*.py` 的題目不自動驗證，結果記為「人工」。其他題目從 `evals/<題目>` 複製，開始前會檢查它是否乾淨，結束後若發現 agent 改到原檔就判 FAIL。執行期間 harness-lab 若多了未追蹤的檔案（可能是 agent 用絕對路徑寫到工作目錄外），會發出警告，並把檔案複製到 run 目錄的 `escaped/` |
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
- **解題**：Pi、Codex、OpenCode、Qwen Code 兩道題全部通過。關掉思考的 Pi 解較難的題目只要 66 秒；開思考時各 harness 要 2 到 10 分鐘，主要看模型想了多久。

詳見 [reports/resolute 實測結果.md](<reports/resolute 實測結果.md>)。

## 目錄

| 目錄 | 內容 | 版控 |
|---|---|---|
| `scripts/`、`bin/`、`configs/`、`evals/` | 腳本、harness 包裝腳本、設定範本、評測題目（每個子目錄一題） | ✅ |
| `reports/`、`research_notes/` | 調研報告、實測總結等人工整理的文件 | ✅ |
| `logs/` | 自動產生的紀錄：跑分輸出、`agent-runs.md`、`runs/<題目>/<harness>/<日期_時間>/`（每次測試的工作目錄）、伺服器 log | ❌ |
| `vendor/`、`models/`、`node_modules/`、`.venv/`、`.cache/`、`.home/` | 工具、模型、快取、各 harness 的設定與憑證 | ❌ |
| `env.local.sh` | 這台機器自己的設定（API key、`N_CPU_MOE` 等） | ❌ |
