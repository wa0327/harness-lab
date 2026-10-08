# Claude Code 規則

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
4. **建 commit 前把將簽入的內容給使用者複核**（`git commit --dry-run -- <paths>`，
   或 `build-tree.sh` 印出的 BASE→TREE），等說簽入才動 HEAD。

**記憶檔與筆記也是 repo 內容**：repo 有追蹤的記憶檔（`.claude/memory/`；
`git ls-files .claude/memory` 有輸出就是）與筆記（例如 `wiki/notes/`），本 session
寫過的要進涵蓋性檢查、和當次主題一起簽，不另開 commit。
