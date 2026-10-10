# 四家 harness 設計拆解：給 Qwen3.6-35B-A3B 的極簡 harness 參考

整理日期：2026-10-10。對象是 Pi、Qwen Code、Codex、OpenCode 四家 harness 搭本地 Qwen3.6-35B-A3B（llama-server）的情況。目的是找出哪些設計值得放進自製的極簡 harness，以及每一項各自要用哪個實驗驗證。

## 資料來源與限制

- **版本**（`package-lock.json`）：Pi 1.1.0（MIT）、Qwen Code 0.25.0（Apache-2.0）、Codex 0.162.0（Apache-2.0）、OpenCode 1.18.35（MIT）。
- **實際送出的請求**：以 `scripts/logproxy.py` 的錄音為準（`logs/runs/<題目>/<harness>/<時間>/requests/`），原始碼為輔。
  - Pi、Qwen Code 的 bundle 可以直接讀。
  - Codex 對照上游 `openai/codex` tag `rust-v0.162.0`；OpenCode 對照上游 `anomalyco/opencode` tag v1.18.35。
- **token 數**：除另註外，都用 `llama-tokenize`（Qwen3.6 詞表）實算。
- **錄音的時效**：
  - Pi 的錄音早於 max_tokens 改成 65536、CTX 改成 128K 的設定。
  - Codex 的錄音是 0.161.0 錄的。
  - OpenCode 的錄音是手動執行時錄的（`agent-test.sh` 沒有替它掛 logproxy）。
  - 四家都沒有「思考關閉」的錄音，關閉思考時送出的參數是看原始碼推得的。

## 差異表

| 項目 | Pi | Qwen Code | Codex | OpenCode |
|---|---|---|---|---|
| API | Chat Completions | Chat Completions | Responses（已不支援 Chat） | Chat Completions |
| 系統提示 | 681 tok | 4,277 tok | 3,662 tok（fallback 提示，一半在講輸出格式） | 約 2.2K tok（qwen 不在任何專屬分支，拿 default.txt） |
| 工具 schema | 4 個，720 tok | 14 個常駐＋14 個延遲載入，8,125 tok | 約 1.8K tok；子代理等 namespace 工具被 llama-server 丟掉 | 10 個，約 5.4K tok |
| 首回合固定開銷 | 約 1.6K | 約 15.2K（含 2.8K 的 system-reminder） | 約 6.8K | 約 7.4K；帶家目錄 skills 時 11.0K |
| 編輯 | str_replace（edits 陣列）＋write | str_replace＋write | 寫在 shell 裡的 apply_patch；本地 Qwen 實際上從沒用過，都是 heredoc 或 `sed -i` | str_replace＋write；模型 id 含 `gpt-` 時改用 apply_patch |
| 寬鬆比對 | NFKC、行尾空白、引號／破折號 | Unicode 正規化、行尾空白、刪整行時補換行 | 精確 → 去行尾空白 → 去前後空白 → Unicode | 9 種 replacer，含首尾行定位與相似度門檻 0.65；比對範圍過大就拒絕 |
| 比對失敗回饋 | 只說找不到或不唯一，不附候選片段 | 同左，並建議用 read_file 確認 | 列出找不到的行 | 同 Pi |
| 改前必讀 | 無 | 強制；讀過後 mtime 或大小變了也拒絕 | 無 | 說明裡有寫，程式裡找不到這項檢查 |
| 回合上限 | 無 | 預設不限，單次串流 100 | 無 | 無（`steps ?? Infinity`） |
| 重複呼叫偵測 | 無 | 同一呼叫連續 5 次就停 | 無 | 連續 3 次就「詢問」，`--auto` 自動通過，等於沒有作用 |
| 工具輸出截斷 | read 取頭、bash 取尾，各 2000 行或 50KB，全文存檔並給路徑 | 超過 25K 字元或 1000 行就存檔，只回預覽 | 10KB，截中間、保留頭尾，標出原始 token 數與行數 | 2000 行或 50KB，存檔並回預覽 |
| 壓縮門檻 | 視窗 − 16K | min(0.85×視窗, 視窗 − 33K)；64K 時只剩 32.5K | 90% 觸發，95% 強制 | 視窗 − maxOutput |
| 摘要形式 | Goal／Progress／Next Steps 等固定格式 | `<state_snapshot>`，摘要是唯一記憶，只放回最近 5 個檔 | 交接式摘要，保留最近使用者訊息 20K | Objective／Work State／Next Move 等，保留尾段 2–15K |
| 思考參數 | `chat_template_kwargs.enable_thinking` | 預設不送；`reasoning:false` 時送 enable_thinking=false | `reasoning.effort` | 不送；只能用 `reasoningEffort:none` 關掉 |
| 取樣參數 | 送 models.json 的設定（1.0／0.95／20） | 送 settings 的設定（1.0／0.95／20） | 不送，用伺服器預設 | 不送，用伺服器預設 |
| 歷史裡的 reasoning | 回傳 | 回傳 | 回傳 | 回傳 |
| 截斷保護（finish_reason=length） | 不執行這回合的工具呼叫 | 拒絕寫入半截內容，提示先寫骨架 | 無記載 | 無記載 |
| 錯誤回饋 | 例外訊息當工具結果；結束碼附在輸出後 | 工具結果帶 `{error}`；同一錯誤 3 次就附加 RETRY LOOP 警告；未知工具附相近名稱 | 一律回給模型；開頭附結束碼 | 參數錯誤導到隱藏的 `invalid` 工具 |
| checkpoint | 無 | 只在互動模式 | 已移除 | 每步前 git 快照 |
| 寫入後檢查 | 無 | 無 | 無 | 有 LSP 時附診斷（實測沒出現過） |
| 時間感知 | 無 | 無（`--max-wall-time` 到點直接結束） | 無 | 無 |
| 語言規則 | 無 | 有（`output-language.md` 注入系統提示） | 無 | 無 |

## 實測失敗與設計的對應

| 實測現象 | 設計上的原因 |
|---|---|
| Pi 在第 299.7 秒用沒跑過的版本蓋掉能過 1 題的版本 | write 直接覆寫；沒有 checkpoint；不知道剩多少時間；寫完不檢查 |
| Pi 最後一版有 NameError | write／edit 成功只回一行字，沒有語法或執行檢查 |
| Qwen Code 說 evals/、research_notes/ 是空的 | glob 寫死只回檔案（`nodir:true`），也沒有 ls 工具；兩個目錄第一層只有子目錄 |
| Qwen Code 在 64K 視窗下照摘要寫出不存在的內容 | 壓縮門檻 32.5K，扣掉 15K 固定開銷，對話只剩約 17K 可用；摘要是唯一記憶 |
| Pi、OpenCode 淺讀後寫通用清單 | 系統提示要求簡短（Pi「Be concise」，OpenCode「fewer than 4 lines」），沒有要求先探索；OpenCode 還鼓勵「依檔名推斷」 |
| OpenCode 跑 implement-duration 要 628 秒 | 思考全開不設限（三段思考合計約 470 秒）；4 次用 write 整檔重寫 |
| OpenCode 把 trace 寫到 /tmp | bash 工具說明寫明 `/tmp/opencode` 已預先核准 |
| OpenCode 帶進家目錄 skills | 掃描真正的家目錄 `~/.claude/skills`，改 XDG 擋不住；`OPENCODE_DISABLE_CLAUDE_CODE` 可以關 |
| Codex 是本地組唯一能過 1 題 gnc-stub 的 | 可能的原因：首回合精簡、平行讀檔、截斷時標出原始大小、提示寫明「不要猜」並要求主動驗證。gnc-stub 只差 1 題、都只跑一次，這些還不能下結論 |
| 關掉思考後多數 harness 不用繁中 | 只有 Qwen Code 把語言規則放進系統提示 |

## 極簡 harness：基線

以下幾項四家都有，或者是衛生性質的處理，直接放進基線，不另做消融：

- **API**：Chat Completions。
- **工具**：read、bash、edit（str_replace）、write。read 讀到目錄時要列出內容，避免 Qwen Code 那種「目錄是空的」誤判。
- **edit 寬鬆比對**：精確 → 去行尾空白 → 去前後空白 → Unicode 正規化。比對範圍過大就拒絕。
- **工具輸出截斷**：超過門檻時全文存檔，回預覽，並標出原始大小和續讀方式。
- **錯誤處理**：所有錯誤都當工具結果回給模型，bash 輸出附結束碼。參數解析失敗時，把收到的原始參數一併回給模型。
- **截斷保護**：finish_reason=length 時不執行這回合的工具呼叫。
- **系統提示**：只寫一般 harness 都有的身分、環境（工作目錄、平台、日期）、工具清單和工具用法（用相對路徑、改既有檔用 edit），不放探索、查證、語言、執行方式這類引導做事方法的規則，那些一律列為消融元件。
- **思考與取樣**：明確送 `enable_thinking` 和取樣參數，不交給伺服器預設。
- **保險**：步數硬上限，同一呼叫連續重複時直接打斷。

## 極簡 harness：要消融的元件

每一項都要對照基線，用同樣的題目各跑 N 次（N≥3），看分布而不是單次結果。

| 代號 | 元件 | 來源 | 假設 | 主要量測 |
|---|---|---|---|---|
| A1 | 每次工具結果附上已用／剩餘時間 | 四家都沒有 | 減少最後一刻用沒跑過的版本覆寫，提早收尾 | gnc-stub 通過數、最終版本能不能跑 |
| A2 | 寫入後自動做語法檢查，結果附在回應裡 | 參考 OpenCode 的 LSP 回饋 | 抓到 NameError 這類錯誤 | gnc-stub 最終版本能不能跑、迭代次數 |
| A3 | 每次寫入前自動快照，結束時保留最後一個能跑的版本 | OpenCode 的 git 快照 | 避免好版本被蓋掉 | gnc-stub 通過數 |
| A4 | 既有檔案禁止 write，只能用 edit | 四家都沒有 | 省掉 2–4K 的整檔重寫，增加迭代輪數 | 每輪 token 數、時限內輪數、通過數 |
| A5 | edit 失敗時附上最接近的候選片段 | 四家都沒有 | 減少 edit 重試；配合 A4 才不會卡死 | edit 失敗率、改用 write 的比例 |
| A6 | 系統提示加查證規則（不猜；空結果要換方法再查）與探索要求 | Codex「Do NOT guess」 | 減少捏造與淺讀 | review-readme 錯誤條數、關鍵問題覆蓋 |
| A7 | 系統提示加語言規則 | Qwen Code | 關掉思考後仍用繁中 | 各題語言遵守率 |
| A8 | 改前必讀 | Qwen Code | 減少 edit 失敗與憑記憶亂改 | edit 失敗率 |
| A9 | 思考：關閉、low、medium，加上歷史 reasoning 回傳或不回傳 | 各家做法不一；四家都回傳，而且伺服器確實會放進 prompt（見下節） | 找出速度與通過率的平衡點；不回傳可省 context | 各題時間、通過數、總 token |
| A10 | 平行工具呼叫 | Codex | 減少請求次數，讀得更廣 | 請求次數、review-readme 覆蓋 |
| A11 | 系統提示說明執行方式：非互動、沒人能回答、做完為止再簡短總結 | Qwen Code 非互動模式的提醒；Codex「keep going until resolved」 | 減少中途停下來發問或只做一半就結束 | 提早結束的次數、通過數 |

第一波先做 A1–A4、A6、A9，它們直接對應最主要的失敗。

A3 若要「保留通過最多測試的版本」，harness 得知道評分指令，這對其他 harness 不公平。比較時只能用通用信號，例如語法檢查和能不能執行，或者把驗證指令當成任務說明的一部分，讓每家 harness 都拿得到。

## 不採用

- **Responses API、namespace 工具、goal 工具、子代理、背景 PTY session**：llama-server 會丟掉一部分；本地 Qwen 實際用錯過 write_stdin；這些工具只是佔 token。
- **長篇的輸出格式與 CLI 互動規範**：Codex 提示有一半是這些，OpenCode 的「少於 4 行」還跟審查類題目衝突。
- **自動掃描家目錄的 skills 或設定**：不可重現。
- **背景額外打模型的功能**（Qwen Code 的 memory 擷取等）：單一本地伺服器會跟主任務搶資源。
- **固定預留量的壓縮門檻**：64K 視窗下會吃掉一半 context。

壓縮目前不列入消融：各題實測最高約 47.6K，沒有觸發過壓縮。要等出現會用到長 context 的題目再測。

## 歷史裡的思考會進 prompt

llama-server 用的是 GGUF 內建的 chat template（`serve-main.sh` 只開了 `--jinja`，沒有覆寫）。結論是：在同一個任務裡，模型看得到自己之前每一回合的思考。

- **template 的規則**：
  - 只要 assistant 訊息排在最後一則「真正的」使用者訊息之後，就把它的 `reasoning_content` 原樣包在 `<think>` 裡放回 prompt。以 `<tool_response>` 開頭的使用者訊息不算數。
  - `preserve_thinking=true` 只影響那一則訊息之前的舊回合。
  - 所以一般 agent 任務從頭到尾只有開頭一則使用者訊息，每回合的思考都會留著，不需要另外設 `preserve_thinking`。
  - 如果 harness 在任務中途插入一般的使用者訊息，例如提醒，那則訊息之前的思考就會被丟掉。
- **伺服器實際行為**：用 `logs/server-main-*.log` 的 `f_keep` 驗證。
  - `f_keep` 是上一回合留在快取裡的內容（含剛產生的部分）被下一回合原樣沿用的比例。
  - 上一回合產生 200 token 以上的連續請求中，大多數 `f_keep=1.000`，代表產生的思考原樣放回了 prompt。
  - Codex 的錄音每個 reasoning item 都帶明文思考，對應的回合也是 `f_keep=1.000`，所以 Responses API 這條路也一樣。
  - 少數 `f_keep` 低的情況，是中間插進了標題產生之類的副請求，或者重新組出來的文字和模型原本的輸出有細微差異，快取因此對不上，但思考仍然在 prompt 裡。
- **對 A9 的意義**：harness 可以選擇在歷史裡拿掉 `reasoning_content`，template 會放進空的 `<think></think>`。
  - 好處：省下 context。
  - 代價：每回合只需要重算最新那一則 assistant 訊息以後的內容，預填成本很小。
  - 要驗證的是：拿掉之後，模型會不會因為忘了自己之前的推理而表現變差。
- **快取命中**：拿掉思考後，新的 prompt 會在「上一回合思考開始處」和快取分岔，前面照樣命中。
  - 額外重算的只有上一回合的工具呼叫或文字，通常幾十到幾百 token。工具回傳的結果本來就要算，不算在額外成本裡。
  - Qwen3.6 是混合架構，原本擔心快取無法從中段截斷、得整段 prompt 重算。但 `logs/server-main-*.log` 裡 16 筆部分命中的請求，全部都是從分岔點接著算，沒有一筆整段重算。例如上一回合快取 43,420 token，新請求沿用前 21,840 token，只重算 4 token。
  - 前提是一律全部拿掉。「只保留最近 N 回合的思考」這種滑動視窗，會讓分岔點每回合往前退到被移出視窗的那一回合，每回合都得重算 N 回合的內容。

## 未確認

- OpenCode 在 cwd-probe 300 秒逾時、事件紀錄空白的原因：requests/ 是空的，代表它卡在第一次呼叫模型之前，但無法確認卡在哪裡。
- 四家關閉思考時實際送出的參數（都沒有錄音）。
- OpenCode、Codex 不送取樣參數時，llama-server 實際用的預設值。
