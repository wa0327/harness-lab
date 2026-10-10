# harness-lab

在 8GB VRAM 的 Linux 筆電上跑本地 LLM，接上各種 agent harness（Pi、Codex、OpenCode、Qwen Code、VS Code 擴充…）測試兼日常使用。

**原則：所有東西都在本目錄內**，包括 llama.cpp 執行檔、模型、Python venv、npm 套件、各 harness 的設定與快取。刪掉這個目錄就清乾淨，不會動到家目錄的 `~/.codex`、`~/.pi`、`~/.qwen`、`~/.config/opencode` 等。例外：沒有先 `source env.sh` 就執行時，會用到全域安裝的版本和家目錄的設定（例如另外裝了 `codex`，或直接在這裡跑 `npm` 會用 `~/.npm` 快取）；Claude Code、Cline、llama.vscode 這些不在本專案裡的工具，設定也一樣在家目錄（包括 `agent-test.sh` 的 `claude` 考生）。`agent-test.sh` 的題目快照放在 `/tmp/agent-snapshots/`，但那只是從 git 解壓出來的快取，被清掉會自動重建。

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
| NVIDIA 驅動 | 支援 CUDA 13.x：`nvidia-smi` 右上角的 `CUDA Version` 是 13.0 以上（resolute 用 610 版）；太舊的話見步驟 2 | `nvidia-smi` |
| RAM | 32GB 左右：主模型 22.4GB，MoE 專家大多放在系統 RAM（resolute 是 30GB + 32GB swap）。不夠的話改用 GLM（17.5GB） | `free -g` |
| Shell | bash：`env.sh` 用了 bash 專屬的語法，zsh、fish 不能 `source` | — |
| Node.js | 22.19 以上（Pi 的要求） | `node --version` |
| Python | 3.x，含 venv 模組（Ubuntu 可能要 `sudo apt install python3-venv`） | `python3 -m venv --help` |
| 其他 | git、curl、tar、`lscpu`（算實體核心數） | — |
| 磁碟 | 約 30GB（主模型加 FIM 24GB、llama.cpp 解壓後約 800MB、npm 套件約 1.5GB、npm 快取約 1GB）；要試 GLM 再加 18GB | `df -h` |

`scripts/setup-tools.sh` 開頭會自動檢查，缺什麼會先列出來。

### 1. Clone

```bash
git clone <repo 位址> ~/repos/harness-lab && cd ~/repos/harness-lab
cp env.local.sh.example env.local.sh   # 這台機器自己的設定，不進版控；下一步編輯
```

### 2. 編輯 `env.local.sh`（在安裝之前）

- **驅動不支援 CUDA 13**：設 `LLAMA_CUDA=12.8`。要在下一步裝 llama.cpp 之前設；已經裝了 13.4 版的話，設好後重跑 `scripts/install-llama.sh` 會改裝 12.8 版。
- **要讓區網內其它電腦使用時**：同時設 `HOST=0.0.0.0` 和自己的 `API_KEY`，見下方「對外開放與 API key」。預設只聽本機，key 是公開的預設值 `harness-lab`。
- **下載模型想放寬 Hugging Face 的速率限制**：加一行 `export HF_TOKEN=...`，或之後執行 `source env.sh && hf auth login`（`HF_HOME` 指向專案內，token 也存在 `.cache/huggingface/`）。
- 一律用 `: "${變數:=值}"` 的寫法，命令列上的環境變數才能繼續優先。其它可調的變數（`CTX_<模型>`、`BATCH`、`UBATCH`、`KV_TYPE`、`LOAD_MODE`、`THREADS`、`MAIN_PORT`…）的預設值和說明在 `env.sh`。
- **改 `MAIN_PORT` 時**：4 份 harness 設定裡的位址寫死 `http://127.0.0.1:8080/v1`，`configs/` 和 `.home/` 都要一起改，否則 harness 連不上。

### 3. 安裝

```bash
scripts/setup-tools.sh      # venv（hf、rich）、Pi、Codex、OpenCode、Qwen Code（版本依 package-lock.json），並把 configs/ 範本複製到 .home/
scripts/install-llama.sh    # llama.cpp（固定 build），下載約 560MB，解壓後約 800MB
scripts/get-models.sh       # 主模型與 FIM 模型，約 24GB（參數 main、fim 只下載其中一個，預設 all）
```

### 4. 依硬體調參數

`env.sh` 的預設值是 **resolute**（RTX 4060 Laptop 8GB + 30GB RAM）實測出來的，換了機器要重新量：

```bash
scripts/bench-moe.sh                          # 預設掃 40 38 36…，遇到 OOM 自動停，結果在 logs/bench/
scripts/bench-moe.sh 39 38 37                 # 找到大概範圍後細掃：參數就是要測的值
BATCH=2048 UBATCH=2048 scripts/bench-moe.sh   # 預設 4096 一開始就 OOM 時改試 2048（預填較慢，但省 VRAM）
MODEL=glm scripts/bench-moe.sh                # 每個模型要各自量
```

`PP`、`TG` 可以調整跑分時預填與生成的長度（預設 8192、128）。挑「最小又不 OOM」的 `--n-cpu-moe`，再留一點餘裕（伺服器的 context 會比跑分多吃 VRAM：Qwen 預設 128K、GLM 64K，可用 `CTX_<模型>` 調整），寫進 `env.local.sh`：

```bash
: "${N_CPU_MOE_QWEN:=38}"   # 填自己量出來的值。每個模型各自一個變數（N_CPU_MOE_GLM…），切換 MODEL 時才不會套錯
```

resolute 的 `-ub 4096` 下限是 38（37 就 OOM），低於這個值的範例照抄會 OOM。

### 5. 啟動與驗證

```bash
scripts/serve-main.sh                          # 終端機 1：主模型，Ctrl+C 停止
scripts/serve-fim.sh                           # 終端機 2（選用）：Tab 補全

source env.sh                                  # 終端機 3
until curl -sf -H "Authorization: Bearer $API_KEY" http://127.0.0.1:8080/health >/dev/null; do sleep 2; done   # 等模型載入完
curl -s -H "Authorization: Bearer $API_KEY" http://127.0.0.1:8080/v1/models
scripts/agent-test.sh fix-inventory pi
scripts/agent-test.sh fix-inventory codex
scripts/agent-test.sh fix-inventory opencode   # 第一次會下載 ripgrep 到 .home/opencode，多花約 1 分半
scripts/agent-test.sh fix-inventory qwen
scripts/compare-runs.py --latest fix-inventory
```

serve 腳本只輸出到終端機，不會自己寫 log。要留紀錄或放背景跑時自己重導向，例如 `scripts/serve-main.sh > logs/server-main.log 2>&1 &`，停止時 `pkill -f llama-server`。

### 6. 每台機器要重建的狀態

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

對外開放時還要注意：

- **流量是明文 HTTP**，key 在區網上可能被側錄，只在信任的網路使用。只有自己的其他電腦要連的話，用 SSH tunnel 更安全，也不用開 `HOST=0.0.0.0`：`ssh -L 8080:127.0.0.1:8080 resolute`。
- 有開防火牆（例如 ufw）的話，要放行 8080（FIM 是 8012）。`HOST` 對三支 serve 腳本都有效，FIM 也會一起開放。
- 其它電腦上的 Pi、Codex、OpenCode、Qwen Code 要把設定裡寫死的 `127.0.0.1` 換成這台的 IP。

以前的版本預設不驗證，舊機器上已經存在的 `.home` 設定（Pi 寫死 `"none"`、Codex 註解掉 `env_key`）會在重跑 `scripts/setup-tools.sh` 時自動改成讀 `API_KEY`。

另開終端機使用 harness，各自的用法見下方「使用各 harness」：

```bash
source env.sh               # 讓 pi、codex、opencode、qwen、hf、llama-* 指向專案內的版本與設定
cd ~/某個專案
pi --model harness-lab/qwen3.6-35b-a3b --thinking off
```

### 切換主模型

`env.sh` 的 `MODEL` 決定主模型：`qwen`（預設，Qwen3.6-35B-A3B）、`glm`（GLM-4.7-Flash，31B/3B 啟用，UD-Q4_K_XL 17.5GB），或遠端的 `ds4`（見下方）。檔名、別名、`N_CPU_MOE` 和 `CTX` 都會跟著換：

```bash
MODEL=glm scripts/get-models.sh main
MODEL=glm scripts/serve-main.sh
pi --model harness-lab/glm-4.7-flash                # harness 不讀 MODEL，要自己指定模型
MODEL=glm scripts/agent-test.sh fix-inventory pi   # 紀錄的標籤會加上 [glm-4.7-flash]
```

整個終端機都要換的話，用 `. env.sh glm`（換回來是 `. env.sh qwen`），之後執行的腳本（`serve-*.sh`、`get-models.sh`、`bench-moe.sh`、`agent-test.sh`）都會跟著用。**`pi`、`codex` 等 harness 本身不讀 `MODEL`**：模型名稱寫在各自的設定裡（預設都是 qwen），要照下方「指令對照」的「換成 GLM」那一列另外指定。只換伺服器、沒換 harness 的話，Pi 會把 Qwen 的取樣參數送給 GLM。注意不要打成 `MODEL=glm . env.sh`：bash 會在 source 結束後把 `MODEL` 還原，之後的腳本又會回到 qwen。

新增模型時：

1. `env.sh` 的 `case` 加一段。`N_CPU_MOE`、`CTX` 照現有寫法讀 `N_CPU_MOE_<名稱>`、`CTX_<名稱>`，讓各機器能在 `env.local.sh` 覆寫。
2. 設定範本加上模型：`configs/pi/models.json`（含取樣參數）、`configs/opencode/opencode.json`、`configs/qwen/settings.json`。Codex 執行時用 `-m` 指定就好。已經存在的 `.home/` 設定不會被覆蓋，要一起改（見「設定範本與 `.home/` 的關係」）。
3. `MODEL=<名稱> scripts/get-models.sh main`、`MODEL=<名稱> scripts/bench-moe.sh`，把量出來的 `N_CPU_MOE_<名稱>` 寫進 `env.local.sh`。

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

#### 雲端模型 `luna`

OpenAI 的 GPT-6 Luna（`gpt-6-luna`）**只給 Codex 用**：走 Codex 內建的 `openai` provider，用 ChatGPT 帳號的額度，不用 API key。`luna` 只有 `agent-test.sh` 認得，env.sh 沒有這個 `MODEL`（`. env.sh luna` 會報錯）；互動使用時照下方「指令對照」自己指定。

```bash
. env.sh && codex login                              # 第一次：登入資料存在 .home/codex，不碰 ~/.codex
scripts/agent-test.sh --model luna review-readme codex   # 紀錄的標籤會加上 [gpt-6-luna]；MODEL=luna 也可以
```

- `agent-test.sh` 開跑前改查 `codex login status`，沒用 ChatGPT 登入就不跑；codex 以外的 harness 要 API key，直接擋下。
- `--thinking off` 送的是 `reasoning.effort=none`，Luna 支援。
- 設定裡的 `model_context_window = 131072` 是給 qwen 的，對 Luna 也一樣有效：Codex 會在 128K 就壓縮 context。

想走 Pi 官方的 router 模式時，改跑 `scripts/serve-router.sh`。router 會依請求的模型名稱（檔名，如 `Qwen3.6-35B-A3B-UD-Q4_K_XL`）自動載入，所以 Codex 等一般用戶端不必先手動載入。Pi 這邊，第一次要在互動模式裡執行 `/login llama.cpp`（key 可留空，會讀 env.sh 匯出的 `LLAMA_API_KEY`，和 `API_KEY` 同值）和 `/llama`，模型清單才會存下來，之後才能用 `pi --model llama.cpp/Qwen3.6-35B-A3B-UD-Q4_K_XL`。執行這兩個指令時 `serve-router.sh` 要在跑。resolute 上已經做過這一步。

- `models/` 裡的檔案都會出現在 `/llama` 的清單裡，包括 FIM 模型，**不要選它**：它會用主模型的參數載入，而且因為 `--models-max 1`，會把主模型卸載。
- router 用同一組參數載入任何模型，所以 context 固定 64K（GLM 開 128K 會 OOM），可以用 `ROUTER_CTX` 改。

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
| 換成 GLM | `--model harness-lab/glm-4.7-flash` | `-m glm-4.7-flash -c model_context_window=65536` | `-m harness-lab/glm-4.7-flash` | `-m glm-4.7-flash` |
| 換成 ds4（遠端） | `--model ds4/deepseek-v4-flash` | `-c model_provider=ds4 -m deepseek-v4-flash` | `-m ds4/deepseek-v4-flash` | `-m deepseek-v4-flash` |
| 換成 luna（雲端） | 不支援 | `-c model_provider=openai -m gpt-6-luna` | 不支援 | 不支援 |
| 調思考 | `--thinking off` 或 `medium` | 見下方說明 | 見下方說明 | 見下方說明 |
| 接續上次對話 | `-c`（最近一次）、`-r`（挑選） | `codex resume --last`、`codex resume` | `-c`、`-s <id>` | `-c`、`-r` |
| 沙箱 | 無 | `-s read-only`／`workspace-write` | 無 | 無（沒設定 docker） |
| 自動核准 | 不詢問，一律執行 | `--approve-for-me`（交給自動審查，不是全部放行）；全部放行是 `--dangerously-bypass-approvals-and-sandbox` | `run` 加 `--auto` | `-y`，或 `--approval-mode auto-edit` |
| 機器可讀輸出 | `--mode json` | `--json` | `--format json` | `-o stream-json` |

換模型時，伺服器也要跑那個模型（`MODEL=glm scripts/serve-main.sh`），見上方「切換主模型」。ds4 是遠端模型，不用啟動伺服器。

### Pi

- **要指定 `--model`**：清單裡有好幾個模型（`pi --list-models` 可以看），不指定的話不一定挑到伺服器上的那個。
- **思考只有 `off` 和 `medium` 兩段**：其他等級在 `models.json` 裡沒有對應，模型不支援。小改動用 `off` 最快，難題再開 `medium`。也可以寫成 `--model harness-lab/qwen3.6-35b-a3b:off`。
- **只想讀、不讓它改檔**：`pi --tools read,grep,find,ls`。
- **沒有沙箱，也不會逐一詢問**：`bash` 以你的權限直接執行，所以只在可以承受的目錄裡用。
- **第一次啟動會下載 ripgrep**（放到 `.home/pi/bin/`），之後就不會了。
- **其他**：互動模式裡 Ctrl+P 切換模型。`--no-session` 不留對話紀錄，`--export <檔案>` 把對話匯出成 HTML。

### Codex

- **預設模型寫在 `.home/codex/config.toml`**，一般直接打 `codex` 就好。
- **每次啟動會警告 `Model metadata ... not found`**：Codex 沒有本地模型的資料，改用預設值，可以忽略。
- **沙箱**：指令在沙箱裡執行，需要超出沙箱時（例如寫工作目錄以外的地方）才會詢問。`codex exec` 預設是唯讀，要讓它改檔得加 `-s workspace-write`，只能寫工作目錄。
- **第一次在某個專案使用時，會詢問要不要信任這個目錄**，同意後會寫回 `.home/codex/config.toml`。
- **思考強度** `model_reasoning_effort`（設定檔或 `-c model_reasoning_effort='"none"'`）：實測 llama-server（Qwen）只認 `none`＝不思考，`minimal`、`low`、`medium` 都照樣思考。伺服器端的 `scripts/serve-main.sh --reasoning off` 只改預設值，請求裡自己帶開關的用戶端照樣會思考（Pi 每個請求都帶 `enable_thinking`）。
- **改檔方式**：實測中 Codex 一律用 `sed` 或 heredoc 改檔，沒用過 `apply_patch`。小修沒問題，大檔案局部修改時要多檢查。
- **其他**：`codex apply` 把 agent 的改動套到 git 工作目錄，`codex review` 做非互動的程式碼審查。

### OpenCode

- **一定要用 `bin/opencode`**：`source env.sh` 之後打 `opencode` 就是它。不要直接執行 `node_modules/.bin/opencode`，否則設定和資料會寫進家目錄。
- **專案根目錄是 git repo 的根目錄，不是目前的目錄**：在 repo 的子目錄裡啟動時，它還是會讀、改子目錄以外的檔案。實測時它就因此跑去改了 `evals/` 的原檔。只想讓它動某個子目錄的話，在那個子目錄裡另外 `git init`，或乾脆換到 repo 外面。
- **第一次用到搜尋工具會下載 ripgrep**（放到 `.home/opencode/`），大約要等一分半，之後就不會了。
- **思考**：`opencode run --thinking` 只是把思考內容顯示出來，不是開關。內建的 `--variant none` 對這裡的自訂模型沒有作用（請求裡什麼都不送）；要關掉思考，在模型的 `options` 加 `"reasoningEffort": "none"`，可以另寫一份疊加設定、用 `OPENCODE_CONFIG` 指過去（`agent-test.sh --thinking off` 就是這樣做）。
- **沒有沙箱**：`bash` 以你的權限直接執行。

### Qwen Code

- **直接加題目是單次執行**：`qwen "題目"` 跑完就結束。要帶著題目繼續互動，用 `qwen -i "題目"`。
- **核准模式** `--approval-mode`：
  - `plan`：只分析，不改檔也不執行指令。
  - `default`：改檔和執行指令前都會詢問。
  - `auto-edit`：改檔自動通過，執行指令前仍會詢問。
  - `auto`：由模型判斷哪些動作安全、可以自動通過。判斷時會另外打模型請求，和下面關掉背景功能的理由一樣，在本機上會拖慢主任務。
  - `yolo`（等同 `-y`）：全部自動通過。

  非互動執行時沒人能回答詢問，要用 `-y`。
- **沒有沙箱**：`-s` 需要 docker 或 podman，這裡沒有設定，所以 `-y` 時 shell 指令以你的權限直接執行。
- **思考**：沒有對應的旗標。要關掉的話，在 `.home/qwen/settings.json` 每個模型的 `generationConfig` 加 `"reasoning": false`（送 `enable_thinking=false`），或另給一份系統設定、用 `QWEN_CODE_SYSTEM_SETTINGS_PATH` 指過去（`agent-test.sh --thinking off` 就是這樣做）。
- **背景功能已在範本裡關掉**：自動 memory 擷取、memory 整併、工具摘要都會在背景另外呼叫模型，在單一本地伺服器上會拖慢主任務。要用的話改 `.home/qwen/settings.json`。
- **context 用到「視窗 − 33K」就會自動壓縮**：它固定保留 20K 給摘要輸出、13K 緩衝，`context.autoCompactThreshold` 只能調低、不能調高。視窗 64K 時約 32K 就壓縮，壓縮後只會放回最近碰過的 5 個檔案，其他內容只剩摘要。review-readme 實測時，模型就照著摘要寫出 README 裡不存在的引用，這是 Qwen 預設 `CTX` 改成 128K（約 98K 才壓縮）的原因。stream-json 裡不會出現壓縮事件。
- **其他**：`--chat-recording false` 不留對話紀錄。`--max-wall-time 10m` 限制總時間，適合無人看管時用。

### harness（自製）

`harness/` 模組是為本機 Qwen 寫的極簡 harness，用來逐項驗證哪些 harness 設計對本地模型有用（設計依據見 `research_notes/harness-design/四家 harness 設計拆解.md`）。目前只接本機的 Qwen：`agent-test.sh` 在 `MODEL` 不是 `qwen` 時直接擋下。

- **用法**：`scripts/agent-test.sh <題目> harness`。也可以在題目目錄直接跑：`python3 <harness-lab>/harness "題目"`（程式在 `harness/__main__.py`），伺服器位址和模型從 `env.sh` 的 `MAIN_URL`、`MAIN_ALIAS` 讀，API key 從環境變數 `HARNESS_API_KEY`（沒有就用 `API_KEY`）讀。
- **組成**：只用 Python 標準函式庫。工具只有 `read`（讀到目錄時列出內容）、`bash`、`edit`（精確比對失敗時依序忽略行尾空白、前後空白、Unicode 標點再比）、`write`。系統提示約 200 token。
- **送出的參數**：每個請求都明確送 `chat_template_kwargs.enable_thinking` 和取樣參數，值和 `configs/pi/models.json` 相同。歷史裡保留 `reasoning_content`，`parallel_tool_calls` 關閉。
- **保護**：
  - 工具輸出超過 2000 行或 50KB 時，全文存到 `/tmp/harness-output.*`，回給模型的內容標出原始大小和檔案路徑。
  - 回應撞到輸出上限時，不執行它的工具呼叫。
  - 同一個工具呼叫連續第 5 次時不執行。
  - 請求上限 300 次。
  - 被 `timeout` 結束時，連同執行中的 bash 指令一起收掉。
- **紀錄**：`agent.jsonl` 用 Pi 的事件格式，`compare-runs.py`、`watch-agent.py` 直接沿用；另外多一個 `session` 事件，記錄實際用的設定、系統提示與工具定義。
- **思考**：`--thinking off` 送 `enable_thinking=false`。歷史裡的思考預設照 chat template 的規則：最後一則使用者訊息之後的都保留，更早的丟掉（單次執行只有一則使用者訊息，所以全部保留）。加 `--preserve-thinking` 送 `preserve_thinking=true`，連更早的也保留：多一則使用者訊息時不必重算前面的內容，但 context 用得比較多。

## 腳本

| 腳本 | 用途 |
|---|---|
| `env.sh` | 所有路徑與參數。優先順序：命令列環境變數（如 `N_CPU_MOE=32 scripts/serve-main.sh`）> `env.local.sh` > 預設值 |
| `env.local.sh.example` | 每台機器設定的範本，複製成 `env.local.sh`（不進版控）後修改 |
| `scripts/serve-main.sh` | 單一模型模式，給 Pi（models.json）、Codex、Cline、Claude Code 等用。提供 OpenAI `/v1/chat/completions`、`/v1/responses` 與 Anthropic `/v1/messages` |
| `scripts/serve-router.sh` | Pi 官方建議的 router 模式（Pi 裡 `/login llama.cpp`、`/llama`、`/model`）。收到請求時自動載入模型，同時最多一個（`--models-max 1`），請求別的模型會把目前的卸載。已驗證 MoE 等參數會傳給 router 載入的模型；模型名稱是檔名；context 固定 64K（`ROUTER_CTX`） |
| `scripts/test-codex-router.sh` | 檢查 Codex 設定的 provider、base URL、key（401 會提示），並用設定裡的模型（或 `CODEX_MODEL`）實際發一次 chat completion。接 router 時用來確認模型名稱對不對 |
| `scripts/serve-fim.sh` | Tab 補全伺服器，port 8012，給 llama.vscode / Continue。context 8K、batch 512 時可以和主模型同時跑（合計 VRAM 7.7GB） |
| `scripts/bench-moe.sh` | `llama-bench` 掃描 `--n-cpu-moe`，結果寫到 `logs/bench/`。參數是要測的值（預設 40 38 36…），`PP`、`TG` 調整預填與生成長度 |
| `scripts/agent-test.sh` | `scripts/agent-test.sh <題目> <harness>`：用 `evals/` 裡的同一題測不同 harness（`pi`、`pi-router`、`codex`、`opencode`、`qwen`、`harness`、`claude`），`claude` 是上限標竿：用家目錄裡的 Claude Code 和你的登入，固定 Opus 5.5，不走本地伺服器，會產生 API 費用（`compare-runs.py` 會列出）。自動驗證並記錄到 `logs/agent-runs.md`，結束時印出結果與通過幾個測試（例如 `FAIL，通過 20/24`）。每次的工作目錄與事件紀錄在 `logs/runs/<題目>/<harness>/<日期_時間>/`。`PI_THINKING=off` 可以調 Pi 的思考強度。題目目錄有 `SNAPSHOT`（commit）時（如 `review-readme`），agent 改在 harness-lab 那個 commit 的快照裡工作：快照每個 commit 只拉一次，存在 `/tmp/agent-snapshots/`，開跑前一律 reset + clean 回到乾淨狀態，產出寫到快照裡的 `output/`，跑完複製到 run 目錄的 `output/`，其他改動存成 run 目錄的 `snapshot.diff`。快照刻意放在 harness-lab 外面：放在底下時，agent 會從工作目錄的路徑推出上層才是真正的專案，實測 Qwen Code 因此跑去審查工作區。沒有 `test_*.py` 的題目不自動驗證，結果記為「人工」。題目目錄有 `ISOLATE` 或 `ACCEPT` 時（如 `gnc-stub`），agent 改在 `/tmp` 的工作目錄作答，評分一律用原檔（見下方「評測題目」）。加 `--thinking off` 關掉模型思考，各 harness 用實測有效的方法：Pi `--thinking off`、Codex `model_reasoning_effort="none"`、OpenCode 疊加設定送 `reasoningEffort: none`、Qwen Code 另給系統設定在每個模型加 `reasoning: false`；Claude 關不掉，直接報錯。紀錄的標籤會加上 `(thinking=off)`。加 `--monitor` 會先顯示實際送出的題目，再即時顯示 agent 的思考、回覆、工具呼叫與結果（`scripts/watch-agent.py`，也能單獨用來看某一次 run）。中途按 Ctrl+C 會結束 harness，照常評分記錄，摘要註明被中斷。其他題目從 `evals/<題目>` 複製，開跑前另存一份原檔，結束時比對，發現 agent 改到原檔就判 FAIL（差異存成 `escaped.diff`）；題目不需要先提交。執行期間 harness-lab 若多了未追蹤的檔案（可能是 agent 用絕對路徑寫到工作目錄外），會發出警告，並把檔案複製到 run 目錄的 `escaped/` |
| `bin/opencode` | OpenCode 的包裝腳本，把 XDG 目錄導向 `.home/opencode/` |
| `scripts/compare-runs.py` | 比較多次執行的 token、回合數、工具呼叫、程式差異與最終回覆。`--latest fix-inventory` 取每種 harness 最新一次；`--md` 輸出 Markdown |
| `scripts/setup-tools.sh`、`install-llama.sh`、`get-models.sh` | 安裝工具、llama.cpp 與模型，全部放在專案內。`setup-tools.sh` 會先檢查前置需求 |

### 評測題目（`evals/`）

目前有 `hi`、`fix-inventory`、`implement-duration`（較難）、`gnc-stub`（最難）、`big-file-fix`、`review-readme`、`cwd-probe` 七題。`big-file-fix` 是用來比 harness 而不是比模型的：`unitlib.py`（單位換算與數量解析庫，約 3,200 行、128KB）裡有 10 個彼此獨立的小 bug，每個看測試的失敗訊息就知道錯在哪；難處在檔案超過一次讀取的上限、整檔重寫在限時 15 分鐘內幾乎寫不完、測試失敗的輸出有 32KB，考驗分段讀取、局部修改和工具輸出的處理。25 個測試裡 20 個各對應一個 bug（每個 bug 2 個），另外 5 個在有 bug 的版本就會通過，用來抓整檔重寫或亂改造成的退化。答案不放在 repo 裡。`gnc-stub` 是寫多旋翼的視覺運動規劃（`gnc.py`）：從相機的目標框和飛控回報的姿態、位置與速度算出速度命令，接近並接觸目標。運動學模擬器（`sim.py`）和測試都給 agent，24 個情境各是一個測試，`agent-test.sh` 結束時印的通過數就是過了幾個情境。限時 5 分鐘（`TIMEOUT` 檔 300 秒）。`hi` 是冒煙測試：只要回答 hi，幾秒就跑完，用來確認 harness、伺服器、模型整條路都通，例如 `scripts/agent-test.sh hi opencode`。`cwd-probe` 不考能力，是檢查隔離：請 agent 列出工作目錄、照抄環境資訊裡的路徑，用來確認 harness 有沒有把快照以外的東西帶進 context。新增題目時，在 `evals/<名稱>/` 放：

- `PROMPT.md`：送給 agent 的題目，必要。
- `test_*.py`：有的話就用 `python3 -m unittest -q` 自動驗證，執行前後比對測試檔的 sha256，被 agent 改過就判 FAIL。沒有的話結果記為「人工」。
- `SNAPSHOT`：放一個 commit，agent 改在 harness-lab 那個 commit 的快照裡工作（題目就是審查本專案時用）。
- `ISOLATE`：agent 改在 `/tmp/agent-work.*` 作答，題目檔（`PROMPT.md` 以外）複製進去並設成唯讀。內容是作答檔清單，一行一個檔名，沒有作答檔時放空檔案即可：作答檔是題目附上、要 agent 修改的檔案（例如 `big-file-fix` 有 bug 的模組），複製進去時保持可寫，評分時也不蓋回原檔。跑完把工作目錄複製到 run 目錄的 `output/`，用原檔蓋回題目檔，再在那裡跑測試：agent 改了自己那份影響不到成績，但會被判 FAIL。紀錄裡出現 harness-lab 的 `logs/runs` 或 `evals` 路徑（agent 跑出去看評分檔或別人的答案）也判 FAIL。不在 run 目錄作答，是因為 agent 會從路徑推到 harness-lab。
- `TIMEOUT`：放限時秒數（例如 `3600`），取代預設的 1800 秒；命令列有給 `TIMEOUT` 時以命令列為準。有這個檔時，題目最後會自動加一句「本題限時 N 分鐘…」告訴 agent（不是整分鐘時寫成「N 分 M 秒」）。
- `ACCEPT`：放驗收次數上限，用法同 `ISOLATE`，但題目檔不放進工作目錄，agent 只能用 `./accept` 送出驗收：它只在佇列目錄 `/tmp/agent-accept.*` 放請求單，由 `agent-test.sh` 在 agent 的程序之外評分、寫回結果，次數也由這邊計算。用完就結束 harness，成績是最後一次驗收的那份。每次驗收的作答與輸出存在 run 目錄的 `accept/`。

`agent-test.sh` 的環境變數：`TIMEOUT`（每次執行的上限，預設是題目目錄 `TIMEOUT` 檔的值，沒有的話 1800 秒）、`PI_THINKING`、`CODEX_MODEL`（接 router 時填檔名）。每次執行在 run 目錄留下 `prompt.md`（實際送出的題目，含自動加上的限時；Claude Code、Codex 的紀錄裡沒有題目）、`agent.jsonl`（事件，給 `compare-runs.py`）、`agent.stderr`、`final.md`（最終回覆）、`meta.json`，有測試時還有 `verify.log`。harness 派了子 agent 時，子 agent 的紀錄另外存到 `subagents/`（`scripts/collect-subagents.py`；Claude Code 的子 agent 訊息本來就在 `agent.jsonl` 裡）。

### 升級與版本

測過的版本：Pi 1.1.0、Codex 0.161.0、OpenCode 1.18.35、Qwen Code 0.25.0（`package-lock.json`），llama.cpp b11469（`env.sh` 的 `LLAMA_BUILD`）。

- **升級 harness**：`source env.sh && npm install <套件>@latest --ignore-scripts`，再重跑 `scripts/setup-tools.sh`（OpenCode 的 postinstall 由它處理），跑一輪 `agent-test.sh` 確認沒問題後提交 `package-lock.json`。`package.json` 都寫 `latest`，版本靠 lockfile 固定；`setup-tools.sh` 用的是 `npm install` 而不是 `npm ci`，嚴格來說不保證完全照 lockfile 裝。
- **試新的 llama.cpp**：在 `env.local.sh` 設 `LLAMA_BUILD`，再跑 `scripts/install-llama.sh`，`current` 會切到新版。不要只用 `scripts/install-llama.sh <build>`：那樣 `LLAMA_BUILD` 沒變，`bench-moe.sh` 的紀錄會標錯版本。改回原本的值再重跑就能退回。
- **`hf`**：`setup-tools.sh` 每次都 `pip install -U huggingface_hub rich`，沒有固定版本，所以「整份重設」時也會順便升級它。

## 其他 harness 的接法

以下的 `<key>` 都是 `API_KEY` 的值，沒在 `env.local.sh` 改過的話就是 `harness-lab`。從其它電腦連時，把 `127.0.0.1` 換成這台的 IP（伺服器要先對外開放）。

- **Cline（VS Code）**：Provider 選 OpenAI Compatible，Base URL `http://127.0.0.1:8080/v1`，API Key 填 `<key>`，Model `qwen3.6-35b-a3b`，開啟 Compact Prompt。
- **llama.vscode（Tab 補全）**：先跑 `scripts/serve-fim.sh`，擴充預設就連 `http://127.0.0.1:8012`，要在擴充設定的 API key 欄位填 `<key>`。
- **Claude Code**：`ANTHROPIC_BASE_URL=http://127.0.0.1:8080 ANTHROPIC_AUTH_TOKEN=<key>`。系統提示約 33k token，以實測約 1,000 tok/s 的預填速度推估，第一回合要等 30 秒以上。尚未實測。

## 疑難排解

| 症狀 | 原因與處理 |
|---|---|
| 伺服器啟動或長對話時 OOM | 調高 `N_CPU_MOE_<模型>`，或降低 `CTX_<模型>` |
| harness 收到 401 | 伺服器和 harness 的 `API_KEY` 不同，例如伺服器啟動後才改 `env.local.sh`，或這個 shell 沒有重新 `source env.sh`。`scripts/test-codex-router.sh` 可以檢查 |
| `curl` 一開始連不上 | 模型還在載入，等 `/health` 回 200（見步驟 5） |
| `env.sh 警告：MAIN_FILE=...` | 從舊環境繼承了變數，照警告 `unset`，或用 `. env.sh qwen` |
| `agent-test.sh`：`另一個 run 正在用` | 同一個快照同時只能有一個 run，等前一個結束 |
| OpenCode 的設定跑到家目錄 | 執行到的是 `node_modules/.bin/opencode`，先 `source env.sh` |
| Codex 警告 `Model metadata ... not found` | 可以忽略 |
| Qwen Code 長任務的後半段開始答非所問 | context 被自動壓縮了，見「Qwen Code」 |

## 注意事項

- llama.cpp 這版已移除 `--no-mmap`，改用 `-lm/--load-mode`。預設用 `auto`（mmap）：RAM 只有 30GB，`none` 會把約 20GB 專家權重全讀進記憶體，比較吃緊。
- 調研時查到 Qwen3.6 在 llama.cpp 上的工具呼叫解析有問題，但在 b11469 上實測正常。`LLAMA_BUILD` 已固定在這版，不要隨意追新版。
- `--ctx-checkpoints 32 --checkpoint-min-step 0` 是為了讓 Qwen3.6 這類混合架構模型能重用快取的 prompt，避免長對話每回合整段重算。實測有效。

## 測試結果（resolute）

- **速度**：預填約 1,160 tok/s、生成約 43 tok/s（`--n-cpu-moe 38`、`-ub 4096`）。
- **解題**：Pi、Codex、OpenCode、Qwen Code 兩道題全部通過。關掉思考的 Pi 解較難的 `implement-duration` 只要 66 秒；開思考時各 harness 要 2 到 10 分鐘，主要看模型想了多久。

詳見 [reports/resolute 實測結果.md](<reports/resolute 實測結果.md>)。

## 目錄

| 目錄 | 內容 | 版控 |
|---|---|---|
| `scripts/`、`bin/`、`configs/`、`evals/` | 腳本、harness 包裝腳本、設定範本、評測題目（每個子目錄一題） | ✅ |
| `harness/` | 自製的極簡 harness（執行 `python3 harness/`，程式在 `__main__.py`） | ✅ |
| `reports/`、`research_notes/` | 調研報告、實測總結等人工整理的文件 | ✅ |
| `logs/` | 自動產生的紀錄：跑分輸出、`agent-runs.md`、`runs/<題目>/<harness>/<日期_時間>/`（每次測試的工作目錄）、伺服器 log（serve 腳本不會自己寫，見步驟 5） | ❌ |
| `vendor/`、`models/`、`node_modules/`、`.venv/`、`.cache/`、`.home/` | 工具、模型、快取、各 harness 的設定與憑證 | ❌ |
| `env.local.sh` | 這台機器自己的設定（API key、`N_CPU_MOE`、`CTX` 等） | ❌ |
