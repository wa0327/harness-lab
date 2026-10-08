---
name: commit
description: 執行 git 簽入的完整流程。使用者說「簽入」「commit」「簽進去」時使用。涵蓋 by-hunk 粒度判準、涵蓋性檢查、怎麼產生只含本 session 改動的 patch、兩條不碰主暫存區的執行路線（pathspec 與臨時 index 腳本）、簽入後保留別人 staged 內容的主 index 同步、多 session 同時簽入，以及禁止使用的破壞性手段。CLAUDE.md 的 Git 規則只留最小防線，細節在這裡。
argument-hint: [整檔簽入|全部簽入]
---

# 簽入流程

前提（CLAUDE.md 已載入的最小防線，這裡不重複論證）：使用者明確說了才簽；
只簽本 session 動過的；不碰主暫存區；禁止 stash / reset --hard / checkout /
restore。以下是怎麼做到。

本 skill 目錄附兩支腳本，在 repo 根目錄執行：

| 腳本 | 做什麼 |
|---|---|
| `.claude/skills/commit/build-tree.sh` | 在臨時 index 組出要簽的 tree，印出複核用的兩份差異；什麼都不改 |
| `.claude/skills/commit/land.sh` | 把複核過的 tree 簽成 commit、讓主 index 跟上，保留別人 staged 的內容 |

## 一、粒度判準

**只 stage 本 session 動過的 hunk，其餘改動留在工作區。** 這是預設，使用者說
「簽入」就是這個意思。

- **粒度**＝`git add -p` 的 hunk 級挑選，**不是**把改動拆成多個 commit 依序簽入。
- **判準**＝本 session 由 Edit/Write 實際動過的行。同一個檔案常混著其他 session
  並行做的改動，那些一律不碰；完全沒碰過的檔案不 stage。
- 整檔改動都出自本 session 時，hunk 挑選等同整檔 `git add`，結果一致。
- **判準雙向成立**：commit 不得混入其他 session 的行（過度包含），也不得漏掉本
  session 動過的行（遺漏）。兩種錯都要防——遺漏會讓 commit 不完整、不能獨立成立
  （改了介面卻漏簽呼叫端），而殘留工作區的孤兒改動會被下一個 session 依同一條規則
  判定為「別人的」而不碰，於是永遠沒人簽。

**理由**：使用者常開多個 session 並行改同一批檔。整檔 `git add` 會把別的 session
尚未完成的改動一起簽進去，污染 commit 且難以回溯。

## 二、涵蓋性檢查（建 commit 前必做）

列出本 session 所有 Edit/Write 動過的檔案，逐一對照即將進 commit 的路徑，
**差集必須為空**。有缺項就要能說出理由：

- 已在本次更早的 commit 裡
- 後來被自己改回原狀
- 被其他 session 覆寫掉、已不存在
- 刻意留待下一步（這項須明確告知使用者）

說不出理由就是漏簽。

### 記憶檔也是 repo 內容，同一次一起簽

先判定這個專案的記憶目錄有沒有綁進 repo：

```
git ls-files .claude/memory
```

- **有輸出**：`~/.claude/projects/<專案>/memory/` 與 repo 的 `.claude/memory/` 是同一份
  檔案且進 git。本 session 寫過的記憶檔（新建的 `<slug>.md` 與 `MEMORY.md` 索引那一行）
  算本 session 動過的檔，必須進涵蓋性檢查、和當次主題一起簽入，不另外開 commit。
  Write 記憶時看到的是 `~/.claude/...` 路徑，容易誤以為在 repo 外——**不是**，
  對照時一律換算成 `.claude/memory/<檔名>`。
- **沒輸出**：記憶不在 repo 裡，不進涵蓋性檢查。

repo 內的筆記目錄（例如 `wiki/notes/`）照一般檔案處理。新記憶檔是 untracked，走路線 2；
`MEMORY.md` 是既有追蹤檔、且常被別的 session 同時加行，混了就用 patch 挑自己那一行。

## 三、選路線

逐檔看，**任何一個檔案**符合右欄就整次走路線 2：

| 檢查 | 路線 2 的條件 |
|---|---|
| 改動是否整檔出自本 session（`git diff HEAD -- <path>`） | 混著別的 session 的 hunk |
| 是否已被追蹤（`git ls-files -- <path>`） | 新檔（`git commit -- <新檔>` 會回 pathspec 不匹配） |
| 主 index 有沒有和工作區不同的 staged 內容（`git diff --cached` 與 `git diff` 對這個路徑都有輸出） | 有——路線 1 會用工作區內容蓋掉那個 index entry |

都不符合才走路線 1。

## 四、路線 1：已追蹤、整檔都是自己的 → pathspec

```
git commit --dry-run -- <paths>     # 先給使用者複核
git commit -- <paths>
```

只簽這些路徑的工作區內容，其他 staged 改動保持 staged 且不進 commit。
pathspec 是**整檔粒度**，混了別人 hunk 的檔案不能用這條。

## 五、路線 2：臨時 index

主 index、工作區全程不動。四步：

### 1. 產生 patch（只有混著別人 hunk 的檔案需要）

```
git diff HEAD -- <混合的檔案> > <scratchpad>/my.patch
```

用預設的 3 行上下文，**不要 `-U0`**：零上下文的 patch 沒有內容可以定位純插入，主 index
裡別人 staged 的內容讓行號位移時，`git apply` 會回報成功、卻把行插在錯的位置。

照 `git add -p` 手動編輯 hunk 的規則改，只留本 session 的改動（誰的改動，以本 session
Edit/Write 的 old_string → new_string 為準）：

- 整個 hunk 都是別人的 → 整個刪掉
- 混合 hunk 裡別人的 `+` 行 → 刪掉
- 混合 hunk 裡別人的 `-` 行 → 開頭的 `-` 改成空白（變成上下文：BASE 上這行還在）
- hunk 的 `@@` 行數不用自己算，腳本用 `--recount`

★ **轉成上下文的行要放回它在 BASE 上的位置。** diff 把一段改動寫成「全部 `-` 在前、全部
`+` 在後」，所以原地改字首會排錯。例：BASE 的 L25（自己改）、L26（別人改）相鄰——

```
原 hunk            原地改字首（錯）     正確
-L25               -L25                -L25
-L26                L26                +L25-mine
+L25-mine          +L25-mine            L26
+L26-other
```

錯的那個會簽出 `L26, L25-mine` 的順序。規則：自己的 `+` 行緊接在它取代的那幾行 `-`
之後，別人的行（已轉上下文）按 BASE 的順序排在前後。

### 2. 組 tree 並自查

```
.claude/skills/commit/build-tree.sh -p <scratchpad>/my.patch -- <整檔都是自己的路徑...>
```

沒有混合檔就不帶 `-p`；新檔、刪檔都放進整檔路徑。它印出 `BASE=`、`TREE=` 和兩份差異：

- **BASE→TREE**：將簽入的內容，必須**只有**本 session 的改動、而且**全部**都在
- **TREE→工作區**：這些路徑上留著不簽的，每一個 `-`／`+` 都必須是別的 session 的
  改動**原樣**

TREE→工作區出現本 session 的行＝漏簽；別人的 `-X` 和 `+X'` 中間夾著不相干的行
（例如 `-L26`、` L25-mine`、`+L26-other`）＝第 1 步的順序排錯。改 patch 重跑即可，
這一步什麼都沒動。

### 3. 給使用者複核

把 BASE→TREE 給使用者看，等說簽入。

### 4. 簽入

commit message 寫進 `<scratchpad>/msg`，然後：

```
.claude/skills/commit/land.sh <BASE> <TREE> <scratchpad>/msg
```

BASE、TREE 照抄第 2 步的輸出。結果：

- **`HEAD 已不是 BASE`**：別的 session 剛簽入，這次**什麼都沒簽**。從第 1 步重做
  （BASE 變了，別人可能簽了同一個檔，patch 要重新產生）並重新複核。
- **`主 index 合併`**：那個檔案裡別人 staged 的部分保留住了，正常。
- **`主 index 不動`**：別人 staged 的內容和本次簽入重疊，腳本不碰它；`git status` 會
  把本次的改動顯示成 staged 的反向改動。告訴使用者是哪幾個檔，**不要自己 reset**。
- **`主 index 同步中斷`**：多半是別的 git 指令正拿著 `index.lock`。commit 已經簽了，
  稍等後跑 `land.sh --sync <BASE> <TREE>` 補同步；**不要刪 lock 檔**，也不要重跑完整的
  land.sh（會再簽一次）。

### 為什麼這樣做

**用腳本，因為 Bash 工具每次呼叫是新的 shell。** 在一次呼叫裡 `export GIT_INDEX_FILE`，
下一次呼叫就沒了，那次的 `git add` 會直接寫進主 index。腳本把臨時 index 的生命週期關在
一次呼叫裡；跨呼叫傳的只有 BASE、TREE 兩個雜湊。真要手動做，每一行 git 指令都要在
同一次呼叫裡帶 `GIT_INDEX_FILE=<路徑>` 前綴。

**`commit-tree -p $BASE` 與 `update-ref HEAD $C $BASE` 是正確性的必要步驟，不是防禦。**
臨時 index 各 session 一份，只隔開「組內容」；HEAD 全部 session 共用一個，同時簽入靠的是
`update-ref` 鎖住 ref、比對仍是 `$BASE` 才換——兩個 session 從同一顆 BASE 出發，只有先
拿到鎖的成功，後到的失敗。拿掉其中任一個，兩邊都會「成功」但結果錯：

- `update-ref HEAD $C` 不帶 `$BASE` → 後到的直接蓋掉 HEAD，前一顆 commit 從分支上消失
- `-p HEAD` → 新 commit 接在別人的後面、tree 卻是從舊 BASE 建的——等於靜默還原它簽的
  所有檔案（曾發生過：一次臨時 index commit 把前一顆 commit 的三個 yaml 整個還原）

**主 index 逐檔三方合併，不用 `git reset -- <paths>`。** reset 會把那些路徑上別人 staged
的內容一起清掉。land.sh 的做法：主 index 的 entry 等於 BASE（沒人 staged）就直接換成
TREE；不等於就拿（主 index, BASE, TREE）做 `git merge-file`，乾淨才寫入——結果對新 HEAD
的差異恰好只剩別人 staged 的部分。也不用 `git apply --cached --3way`：它衝突時會把
未合併的 stage 留在主 index 裡。

**路線 2 不跑 git hooks。** `commit-tree` 不會觸發 pre-commit / commit-msg。repo 有設
hook（`git config core.hooksPath` 有值，或 `.git/hooks/` 裡有非 `.sample` 的檔）就在
land.sh 之前手動跑對應的檢查。路線 1 照常跑 hook。

## 六、不確定時退化成一檔一 commit

多檔一起簽會讓混入風險升高、或本 session 的界線判斷沒把握時，不要勉強湊成單一
commit——對每個「整檔改動都出自本 session」的已追蹤檔案各發一次 `git commit -- <單檔>`，
逐檔乾淨（新檔各自走一次路線 2）。

粒度損失（同一個主題散成數個 commit、中間 commit 可能無法獨立運作）可以接受，
混入別的 session 或漏簽自己則不可接受。

**唯一例外**：改動彼此耦合、拆開會讓中間 commit 壞掉（改了介面與其呼叫端）→ 走
路線 2 一次涵蓋多檔多 hunk，那條本來就支援。

## 七、為什麼禁止 stash 繞道

「先 stash 掉別人的改動 → commit → pop 回來」看似乾淨，實際上是破壞性的：

- stash 會把其他 session 正在編輯的內容從工作區整個抽走，而那些 session 對此毫不
  知情——它們接下來的 Edit 會基於被換掉的檔案內容、正在跑的測試或程式會讀到舊版
- pop 又可能衝突，且衝突落在別人的改動上，本 session 沒有脈絡解
- 中途任何一步出錯就把工作區留在半 stash 狀態

上面兩條路線都不需要動工作區，所以永遠沒有 stash 的必要。

同理禁止其他會改動別人工作區或暫存區狀態的手段：`git reset --hard`、
`git checkout <path>`、`git restore`、對別人 staged 內容下 `git restore --staged`
或 `git reset -- <paths>`。若真的判斷需要動到，**先問使用者**，不自行決定。

## 八、其餘細則

- **界線還原不確定時**（context 被壓縮、跨 session 續接）→ 不硬猜，先列出判定屬於
  本 session 的 hunk 清單請使用者確認再 stage。
- commit message 只描述實際簽入的改動，不涵蓋留在工作區的部分。
- 專案 CLAUDE.md 規定 commit message 要列明的事項（例如修 bug 連帶要 rebuild 的東西）
  照辦。
- **覆寫預設**：使用者說「整檔簽入」「全部簽入」「工作區全簽」才把整個檔案、整個
  工作區當成本次內容（仍走上面的路線，不用 `git add` 湊主暫存區）。
