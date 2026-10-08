# 測試結果（resolute，2026-10-07）

硬體：ROG Zephyrus G16 GA605WV，RTX 4060 Laptop 8GB（driver 610.57，nvidia-powerd 運作中，功耗上限 105W）、Ryzen AI 9 HX 370（12 核）、30GB RAM + 32GB swap。桌面跑在內顯上，獨顯閒置時只用 12MB。

軟體：llama.cpp b11469（預編譯 CUDA 13.4）、Qwen3.6-35B-A3B UD-Q4_K_XL（22.4GB）、Pi 1.0.4、Codex 0.160.1。

## 1. llama-bench：`--n-cpu-moe` 掃描

預填 8192 token（模擬 agent 的長前綴）、生成 128 token，KV cache q8_0，mmap 載入，`-t 12`。

| `-b`/`-ub` | `--n-cpu-moe` | 預填 tok/s | 生成 tok/s | 備註 |
|---|---|---|---|---|
| 2048 | 40（全部專家在 RAM） | 867 | 42.2 | |
| 2048 | 36 | 925 | 44.1 | |
| 2048 | 35 | 949 | 45.2 | |
| 2048 | 34 | 946 | 45.3 | |
| 2048 | 33 | 954 | 45.3 | |
| 2048 | 32 | — | — | OOM（計算緩衝區要 2GB） |
| **4096** | 40 | 1,161 | 42.8 | |
| **4096** | **38** | **1,167** | **43.4** | **選定的預設值** |
| 4096 | 37 | — | — | OOM |

結論：

- 多放幾層專家到 GPU，效益很小（40 → 33 只快約 10%）。這張卡的瓶頸主要在 RAM 頻寬，不在 VRAM。
- `-ub 4096` 讓預填快約 22%，生成只慢約 4%。agent 的瓶頸是預填，所以選 4096。
- 實測結果遠好於調研報告的推估（生成 20–35 tok/s）：生成實際約 43 tok/s，預填約 1,160 tok/s。

原始輸出在 `logs/bench/`（不進版控）。

## 2. 伺服器實測

- `serve-main.sh`（64K context，`--n-cpu-moe 38`，`-ub 4096`）：VRAM 約 5.7GB，生成約 41–43 tok/s。
- **工具呼叫正常**：`tool_calls` 有被正確解析成結構化資料，在 b11469 上沒有遇到報告提到的 Qwen3.6 解析 bug。
- **快取重用正常**：多回合對話中，每回合只預填新增的 token，沒有整段重算（`--ctx-checkpoints 32 --checkpoint-min-step 0`）。
- **FIM 與主模型可以同時跑**：條件是 FIM 的 context 降到 8K、batch 降到 512。兩者合計 VRAM 7.7GB / 8GB。原本的 `--ctx-size 0`（32K）會 OOM。FIM 補全生成約 116 tok/s。
- **router 模式（`serve-router.sh`）**：`--n-cpu-moe` 等參數確實會傳給子程序，效能和單一模型模式相同。注意 FIM 模型在 router 裡也會套用同一組參數（64K context），不適合在 router 裡跑 FIM。

## 3. Harness 解題

每次都把題目複製到 `logs/runs/` 下的獨立目錄，非互動執行，最後自動跑單元測試驗證，並確認測試檔沒被改動。完整紀錄在 `logs/agent-runs.md`（不進版控），可用 `scripts/compare-runs.py` 比較各次執行。

| harness | 題目 | 秒數 | 結果 | 首回合 prompt | 模型生成量 |
|---|---|---|---|---|---|
| Pi（models.json，thinking=medium） | fix-inventory（修 4 個 bug） | 28 | PASS | 約 1,650 tok | 約 830 tok |
| Codex | fix-inventory | 37 | PASS | 約 6,700 tok | 約 870 tok |
| Pi（models.json，thinking=medium） | implement-duration（依規格實作） | 189 | PASS | 約 1,650 tok | 約 7,000 tok |
| Codex | implement-duration | 105 | PASS | 約 6,700 tok | 約 3,400 tok |
| Pi（router，thinking=medium） | implement-duration | 372 | PASS | | 約 13,000 tok |
| **Pi（router，thinking=off）** | implement-duration | **66** | PASS | | |

觀察：

- **全部通過**，測試檔和 SPEC 都沒被改動。
- **時間幾乎都花在生成**（約 40 tok/s），預填只占幾秒。
  - 兩次 Pi medium 的生成量差了將近一倍（7k 與 13k token），可見單次測試的波動很大。
  - Pi 和 Codex 誰快誰慢，目前樣本太少，還不能下結論。
- **關掉思考最快**，只要 66 秒，但寫出的程式比較冗長：用 float 計算，額外接受了規格沒提到的 `+` 號。日常小改動可以用 `--thinking off`，難題再開 medium（`models.json` 只對應 off 和 medium，`low` 等其他等級不支援）。
- **首回合 prompt**：Pi 約 1.65k token（實測 3.4 秒），Codex 約 6.7k token（實測 8.3 秒）。差距約 5 秒，在這台機器上影響不大。

### 加入 OpenCode 與 Qwen Code（2026-10-08）

版本：OpenCode 1.18.35、Qwen Code 0.25.0（同時 Pi 升到 1.1.0、Codex 升到 0.161.0）。主模型 Qwen3.6-35B-A3B，各 harness 都用預設思考。

| harness | 首回合 prompt | 預設工具數 | fix-inventory | implement-duration |
|---|---|---|---|---|
| Pi | 約 1.65k | 4 | 33s，送出 14k tok | 189s（前一天） |
| Codex | 約 6.7k | — | 34s，送出 40k tok | 105s（前一天） |
| OpenCode | 約 10.9k | — | 59s，送出 63k tok | 628s，生成 19.8k tok |
| Qwen Code | 約 15–16k | 30 | 54s，送出 123k tok | 483s，生成 11.0k tok |

觀察：

- **全部 PASS**，fix-inventory 四者改出的程式完全相同。
- **prompt 越大、每回合重送的量越大**，但快取命中都在 90% 以上，所以 fix-inventory 的時間差距不大。
- implement-duration 的時間主要由**思考量**決定：OpenCode 單一回合就生成 8k token（約 4 分鐘）。每種組合只跑一次，波動很大，還不能比較快慢。
- OpenCode 的調研數字（首回合約 7k）比實測少，可能是版本不同。

## 4. 踩到的坑

- 這版 llama.cpp 移除了 `--no-mmap`，改用 `-lm/--load-mode`。llama-bench 的 `-mmp` 也一樣被移除，`-fa` 改成吃 `on|off|auto`。
- `huggingface_hub` 2.x 沒有 `[cli]` extra 了，`hf` 指令直接內建在主套件裡。
- **Pi 的 router 整合需要先互動一次**：只設 `LLAMA_BASE_URL` 環境變數，`-p` 模式找不到 router 上的模型（Pi 1.0.4）。要先在互動模式執行 `/login llama.cpp` 和 `/llama`，模型清單才會存進 `.home/pi/models-store.json`，之後 `-p` 才能用。我已經在專案內的 `auth.json` 寫入 llama.cpp 憑證，並執行過一次 `/llama`。
- Pi 第一次啟動會自動下載 ripgrep，放在 `.home/pi/bin/`，仍在專案內。OpenCode 也一樣（`.home/opencode/cache/opencode/bin/`），第一次測試因此多花 82 秒。
- **OpenCode 跑出 run 目錄改了題目原檔**：run 目錄在 harness-lab 的 git repo 裡，OpenCode 以 git 根目錄當專案根目錄，模型去讀 `/home/jack/repos/harness-lab/SPEC.md`，找不到後用 glob 找到 `evals/implement-duration/`，就直接在原檔上實作。接著跑的 Qwen Code 複製到已解好的檔案，一開始就 PASS。兩次結果都已標為 INVALID，原檔已還原。修正：OpenCode 的 run 目錄先 `git init`；`agent-test.sh` 開始前檢查 `evals/<題目>` 是否乾淨，結束後再檢查一次。
- **opencode-ai 的 npm 套件需要 postinstall** 把平台執行檔連到 `bin/`，`--ignore-scripts` 時要手動跑；它驗證時會執行一次 `opencode --version`，沒先設 XDG 就會在家目錄建目錄。`setup-tools.sh` 已處理。
- **Qwen Code 預設會在背景另外打模型請求**（自動 memory 擷取、工具摘要），同一題 `result.usage` 比各回合加總多約 6k token、時間多 14 秒。範本已關掉。
- **Qwen Code 的 `envKey` 讀到空值會直接報錯**，不送請求，和 Codex 的 `env_key` 一樣（Pi 的自訂 provider 也不會把模型標為可用）。為了不讓設定分成「有 key／沒 key」兩種，`env.sh` 改成給 `API_KEY` 一個公開的預設值 `harness-lab`，伺服器一律驗證，各 harness 都直接讀 `API_KEY`。

## 5. 還沒測

- noble（RTX 5060 Ti）還沒跑。
- Cline、llama.vscode 等 VS Code 擴充還沒實際在編輯器裡測，只有伺服器端驗證過。
- Codex 的思考強度設定（`model_reasoning_effort`）對 llama-server 是否有效。
- 每個組合各跑多次，取平均。
