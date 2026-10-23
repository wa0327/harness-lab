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
**例外：Teamind 名冊裡的 session**（`.teamind/roster.toml`）照下面〈Teamind〉的簽入節奏，一件事做完、驗過就
自己簽（全域規則所說「專案 CLAUDE.md 另有規定」的情形，TM-430）。使用者自己開的視窗照本段。

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

## Teamind（團隊與議題）

本專案由 Teamind（`.teamind/root`，指向這台的 Teamind，每台機器各自的連結，不進 git；TM-430、TM-392）服務。
這一節加上團隊的規則，給名冊裡的 session；和上面不同的地方，對它們以這一節為準。以上各節（上下文管理、Git 規則
的四條底線）照舊。

- **The team:** `.teamind/roster.toml`, seven roles, each its own Claude session `harness-lab-<role>`. The
  **Project Lead (專案經理)**, `harness-lab-leader`, is the front door: the only session Teamind messages, and the one
  that dispatches, reviews and accepts, commits its own work and pushes. Members report to it with SendMessage;
  questions for the user go through it, on an issue, never as a blocking question in the CLI.
  - **Who talks to the user** (TM-354): Teamind's Chief of Staff and each project's lead, each in its own tab of
    Teamind's 對話. The lead replies to the user in Traditional Chinese (語言 above), in chat, on issues and over
    LINE.
  - **The user may also write to any member** in its tab of 對話 (TM-518). That member answers in the user's
    language, as every session that replies to the user does (Chinese in, Traditional Chinese out), does what's asked
    within its own scope (otherwise says whose it is), and tells the lead in one line anything that changes its work.
    A chat is never an approval: those live on issues.
- **Issues:** every problem and request gets one, `issues/HL-<n>/ISSUE.md`, in Teamind's format
  (`.teamind/root/issues/README.md`; the local pointer is `issues/README.md`), with `project: harness-lab` and a
  milestone from `.teamind/project.toml`. Get the id from `python3 .teamind/root/tools/next_id.py harness-lab`. Every
  timestamp comes from `date`.
- **Teamind's contract:** Teamind reads this repo's manifest and roster, its issues, wiki, `git log` and its check
  (`bash check.sh`); it writes only `data/issues_inbox.jsonl` (lines from the user's web; the inbox is runtime data
  and never committed) and the user's own comments, picks and attachment links on the issues. The lead commits
  those, and records in its issues only what the inbox brings that isn't written there yet (a new issue, a
  priority, a mention). It never writes the user's words, picks or attachment links a second time (TM-458). No
  role writes a line authored User. It never commits here or edits this code. A problem
  Teamind finds here is filed through the lead.
- **Heavy runs never on the HQ** (TM-430 §3, the user's pick 2026-10-22 14:56): Teamind's machine has no GPU. Every
  model or agent run (`serve-*.sh`, `bench-moe.sh`, `agent-test.sh`, `ds4` and `claude` runs included) runs on
  zephyrus or noble, as a deployment and the user's ticks on the 主機 page. `agent-test.sh` never runs on the HQ by
  hand: the harnesses run shell commands with the user's rights. On a host shared with business-sim, check first
  (read only, `nvidia-smi`, `ss`) and stop nothing you didn't start; never `pkill -f llama-server`.
- **Outside services** (the user's pick, TM-430 §8, this project only): runs against `MODEL=ds4` (a friend's Mac,
  which sees every prompt) and the `claude` contestant (the user's login, with API cost) need no ask per batch, still
  only on hosts. Each batch's runs and the `claude` cost go on its issue.
- **What goes to the Chief of Staff** (TM-230): only a cross-project matter (accounts, the pool, hosts, another
  project), a clearance (a restart, a spend), or what the user asked the Chief of Staff in chat. A project's progress,
  plans and timings stay on its issues. 開工 and 收工 come from the coordinator and get no reply, unless you're
  blocked on something only the Chief of Staff can clear.
- **Teamind's name in Chinese** (TM-185, TM-236): to the user write 「Teamind」, or 「Teamind 這台」 or 「總部」 for the
  machine, never 「辦公室」.
- **Security:** Teamind's rules hold here (`.teamind/root/wiki/design/security.md`).
  - Secrets live in `data/secrets/` (git-ignored, 700, files 600) and nowhere else in the repo. Members never read a secret or a login (`~/.git-credentials`, `~/.ssh`, `~/.gnupg`, the Claude logins) by any tool or command, sudo included.
  - `check_secrets.py` (`.teamind/root/tools/check_secrets.py`) runs in the pre-commit and pre-push hooks and in the check command; never `--no-verify`.
  - `.claude/settings.json` holds no allow or deny lines; the user-level settings carry them.
  - This project's own logins (Teamind's registry `logins`): each harness's home folder (`.home/`), the tool caches
    holding the Hugging Face login (`.cache/`) and this machine's tuning file until the user has moved its two
    secrets out. Never read or name them; harness settings change only in the tracked templates in `configs/`.
    Search with `git grep` or `rg`, never `grep -r` from the top.
- **Pushing:** the Project Lead pushes this repo by Teamind's rules (security.md "Pushing"): at 收工, and during the
  day at 20 commits or 2 hours ahead; `check_secrets.py --history` first; a red check doesn't block (say so on the
  issue); never a force. Members never push. Teamind's 推送 button is the user's own push.
- **Blocked by a permission:** don't ask the user to do it by hand and don't work around it. The lead asks Teamind's
  Chief of Staff for a temporary session (TM-266), which opens it, briefs it with the blocked steps, and closes it
  when done; the user approves each step in its pane.
- **Commits** (Teamind's cadence, TM-303): commit your own lines only, without waiting for 「簽入」. Each verified
  change is its own commit, at once; your issue notes go in one commit at the end of your turn (`Notes: <ids>`; a
  note in the same turn as a change rides with it). Never go idle, take 收工 or stop on purpose with your own lines
  uncommitted. Every message ends with a `Role: <role>` trailer, which the `commit-msg` hook in
  `.teamind/root/tools/githooks` checks（與 `Co-Authored-By` 同一段、中間不空行；名冊以外的視窗寫 `Role: User`）。
  Load the `commit` skill; Git 規則的四條底線照舊. Never commit the user's own uncommitted work unless an issue says to.
- **Briefs and knowledge** (TM-324): a role's own working instructions are in `.teamind/briefs/<session>.md`, which
  `team.sh` loads at launch; a session started another way reads its brief first. This file holds only what every
  session follows. Harness design specs and code are this project's own files (the lead decides the layout).
- **Be ready to stop at any moment:** commit after every finished step, and keep one resume line in the Progress of
  each issue you hold (what is done, what is next, any half-done change, pids of background jobs).
- **Language:** messages between sessions, briefs, issues' English sections and commit messages are English, except
  that this project's README, reports, research notes and the rules above stay in Chinese. Replies to the user,
  `title_zh` and the 團隊 page's status line are Traditional Chinese (語言 above).
- **Teamind 的工具一律經 `.teamind/root/tools/` 用**（TM-392）：`check_secrets.py`、`githooks/`（`core.hooksPath` 指向
  `.teamind/root/tools/githooks`）、`next_id.py`、`progress.py`。harness-lab 不留副本，被追蹤的檔案也不寫 Teamind 的實際路徑。
- **Status:** keep your one line on the user's 團隊 page with `python3 .teamind/root/tools/team_status.py <your session name> "<一行中文>"`.
