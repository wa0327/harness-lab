# 議題

harness-lab 的議題，由 Teamind（`.teamind/root`）服務。一個 id 一個資料夾，`issues/HL-<n>/ISSUE.md`，
格式照 Teamind 的：[`.teamind/root/issues/README.md`](../.teamind/root/issues/README.md)（欄位、狀態、連結、
`## Request`／`## Progress`／`## Fix`／`## Verification`／`## Comments` 本文）。每個議題都帶 `project: harness-lab`
與設定檔裡的一個 milestone（`harness`、`models`、`evals`、`deploy`、`team`）。

- **新 id：** `python3 .teamind/root/tools/next_id.py harness-lab`，再 `mkdir issues/HL-<n>`；資料夾已存在
  就是別人先拿了，重新要一個。
- **使用者的要求**由 Teamind 寫進 `data/issues_inbox.jsonl`，專案經理把它開成議題。收件匣是執行期資料，
  永不簽入（TM-263）。
- **附件**（`issues/<ID>/attachments/`）只有使用者自己上傳的（`user-*`）進 git，其餘只留本機。
- **結案與重開只用工具**（TM-403）：`python3 .teamind/root/tools/progress.py --project harness-lab --close <ID> <done|wontfix|duplicate> --by "<role>"`
  與 `--reopen <ID> --by "<role>"`，不手改 `state`、`status`（已結議題的 status 不是終態，Teamind 的 lint 會紅）。
- **使用者留言會重開已完成或已結的議題**（TM-382、TM-403；照 Teamind issues/README「The user's comment reopens a done or closed issue」）：
  收件匣的留言帶 `"reopen": true` 時，專案經理記下留言時跑 `--reopen`，Progress 寫一行「Reopened by the user's comment (<時間>)」。
  留言不需要做事（例如道謝），就用工具結回去或改回，Progress 寫一行原因。只選選項不帶這個旗標。
- **ds4 與 claude 考生的跑分**（使用者 2026-10-22 14:56，TM-430 §8）：不必每批先問，但只在主機跑；每一批的執行與
  claude 的費用（`scripts/compare-runs.py` 會列）記在該批的議題上。
- 議題裡的每個時間戳都取自 `date`。
