# Claude Code 規則

## 語言

回覆一律用繁體中文；程式碼、指令、檔名照原樣。

## 上下文管理

**預期會產生大量雜訊、而本 session 只需要結論的動作，交給 subagent 做。** 動手前先估：
這一步會不會灌進一堆用完即丟的輸出——翻多個檔案找某段程式、追一個問題的根因、讀長 log、
掃跑分結果、查文件或上網搜尋、反覆試錯直到某個指令跑通。如果本 session 之後只會用到
「答案是什麼、在哪裡、要改哪行」，就開 subagent（`Explore` 找東西、`general-purpose`
查問題或多步驟試驗），在 prompt 裡講清楚要回報什麼、回報多詳細，讓過程留在它那邊。

判準是**之後還會不會用到過程本身**：

- 只要結論 → subagent。例：「這個 harness 為什麼在 X 題失敗」「llama 哪個參數控制 Y」
  「logs/ 裡最新一次跑分各題分數多少」。
- 本 session 接著要依內容動手改 → 自己讀。例：馬上要 Edit 的檔案、要逐行比對的 diff。
- 已知檔案與位置的單點查詢（讀一個檔、grep 一個名字）→ 直接做，開 subagent 反而更貴。

## Git 規則

**禁止自作主張 commit。** 所有 git commit 必須由使用者明確指示才能執行。不可在完成
任務後自動簽入、不可在背景訓練結束後自動簽入、不可「順便」簽入。等使用者說「簽入」才簽。

**使用者說「簽入」時，先載入 `commit` skill 再動手**——完整流程（粒度判準、涵蓋性
檢查、怎麼產生只含本 session 改動的 patch、兩條不碰主暫存區的執行路線與腳本、多 session
同時簽入）在那裡。以下四條是即使沒載入也絕不能違反的底線：

1. **只簽本 session 動過的**。判準＝本 session 由 Edit/Write 實際動過的行；同一個檔案
   常混著其他 session 並行做的改動，那些一律不碰。雙向成立——不得混入別人的行，也不得
   漏掉自己的（孤兒改動會被下一個 session 判定為「別人的」而永遠沒人簽）。
2. **不碰主暫存區**。使用者常自己先 `git add` 過東西，而 `git commit` 會把暫存區全部
   一起簽進去。用 `git commit -- <paths>` 或臨時 index（skill 附的 `build-tree.sh` /
   `land.sh`），不用 `git add` 湊。
3. **禁止任何會改動其他 session 工作區或暫存區的手段**——`git stash`、
   `git reset --hard`、`git checkout <path>`、`git restore`、對別人 staged 內容下
   `git restore --staged` 或 `git reset -- <paths>`（簽完想讓主 index 對齊新 HEAD 時
   最容易誤用）。那會讓正在編輯的 session 讀到被換掉的檔案而毫不知情。
   真的判斷需要動到，**先問使用者**。
4. **建 commit 前核對將簽入的內容**（`git commit --dry-run -- <paths>`，或
   `build-tree.sh` 印出的兩份差異）。恰好是本 session 的全部改動、沒混到別人的，就直接
   簽，簽完回報；任何一項對不上或界線拿不準，先給使用者複核，等說簽入才動 HEAD。

**記憶檔與筆記也是 repo 內容**：repo 有追蹤的記憶檔（`.claude/memory/`；
`git ls-files .claude/memory` 有輸出就是）與筆記（例如 `wiki/notes/`），本 session
寫過的要進涵蓋性檢查、和當次主題一起簽，不另開 commit。
