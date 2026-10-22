---
id: HL-1
title: "Deploy harness-lab to zephyrus and noble (deploy.toml, llama.cpp and models as components, task kinds, stop by pid)"
title_zh: "把 harness-lab 部署到 zephyrus、noble（deploy.toml、llama.cpp 與模型當外部元件、工作種類、改用 pid 停止）"
status: fixing
state: open
type: feature
area: infra
severity: minor
priority: 
author: Project Lead
owner: Project Lead
handed: fixing / Project Lead
holder: User
blocked_by: 
parent: 
related: TM-430, TM-319, TM-404, TM-245
milestone: deploy
project: harness-lab
found: 2026-10-22
updated: 2026-10-22
---
## Request
(Project Lead.) harness-lab's first piece of work after 啟用 (TM-430 §3). Teamind's HQ has no GPU, so every model or agent run (`serve-*.sh`, `bench-moe.sh`, `agent-test.sh`, `ds4` and `claude` runs included) goes to zephyrus (RTX 4060 Laptop 8 GB) or noble, as a deployment and a kind the user ticks on 主機. The contract is Teamind's `wiki/design/projects.md`, "A deployment, not a clone"; business-sim's and isaaclab-uav's `.teamind/deploy.toml` are worked examples.

Scope:
- `.teamind/deploy.toml` with an `[[entry]]` per thing a kind runs: serving (`scripts/serve-main.sh`, `serve-fim.sh`, `serve-router.sh`), `scripts/bench-moe.sh`, `scripts/agent-test.sh` (with `evals/`, `configs/` and `bin/` in `extra`), `scripts/compare-runs.py`, and the tools' install (`scripts/setup-tools.sh`, `scripts/get-models.sh`). `extra` covers what the closure can't see (files sourced through variables, `env.sh`).
- **External components** (TM-404): llama.cpp b11469 as a `linux-x86_64` prebuilt with its sha256; the model weights (Qwen3.6-35B-A3B, GLM-4.7-Flash, the FIM model) as `any`, downloaded on the host with their sha256, never copied from the HQ.
- `[env.harnesses]`: a node env from `package-lock.json`; a Python env only if a kind needs packages beyond the standard library.
- `local`: the harness homes, the machine's tuning file and `logs/`, kept across deploys. The secrets file under `data/` is the user's to place on each host.
- `config/tasks.toml`: kinds named for their use (for example `serve`, `bench`, `agent-test`, `llmfit`), each with `deploy = [...]`, run only on the hosts the user ticks.
- On a host shared with business-sim: a job checks first (read only, `nvidia-smi`, `ss`) and stops only what it started. The scripts' and README's `pkill -f llama-server` change to stopping by pid.
- Not in scope: the sandbox for agents under test (the Sandbox Engineer's, its own issue).

## Acceptance
- [ ] `.teamind/deploy.toml` exists; Teamind's closure (`tools/deploy_closure.py`, or `host_deploy --dry-run`) lists each entry's files with nothing unresolved, and nothing under `data/`, `issues/`, `.claude/`, the harness homes, the caches or a secrets-looking path.
- [ ] `config/tasks.toml` names `deploy` per kind; Teamind's task-host check exits 0.
- [ ] No tracked script or README line runs `pkill -f llama-server`; stopping goes by the pid the script started.
- [ ] A first deployment on zephyrus (`app/DEPLOY.json` present) installs llama.cpp and one model by their sha256, and a `serve` job answers `/health` from `app/`; its log is attached here.
- [ ] One `agent-test` run of the `hi` eval on zephyrus passes from the deployment.
- [ ] `bash check.sh` passes.

## Progress
- 2026-10-22 17:21 Project Lead: filed after 啟用 (the coordinator, 16:09), per TM-430 §3 and §8. Owner: Project Lead (the roster gives it the deployments). **Resume:** read the scripts for what each runs and sources, draft `.teamind/deploy.toml`, run the closure dry run.
- 2026-10-22 17:22 Project Lead: backlog pass (TM-432): the issue is mine and moving, so status `fixing`. A read-only survey of the scripts (what each runs, sources, reads, writes and downloads; every `pkill`; a draft deploy.toml and tasks.toml) is running in a background subagent of this session. Nothing is half-edited. **Resume:** take the survey's result, write `.teamind/deploy.toml` and `config/tasks.toml`, run Teamind's closure dry run.
- 2026-10-22 17:28 Project Lead: the survey is in. What blocks a deployment, and who takes it:
  - **`agent-test.sh` asks the repo's git** (`lab_untracked`, `git -C "$LAB_DIR" ls-files`, :83, called at :228, under `set -e`); a host has no `.git` (projects.md: `DEPLOY.json`'s `commit` instead). The two SNAPSHOT evals (`cwd-probe`, `review-readme`) need `git archive` of history and can't run from a deployment. Mine: make the untracked-file check work without `.git`, and leave SNAPSHOT evals to hand runs.
  - **The serve scripts `exec` llama-server in the foreground** and record no pid; the only `pkill -f llama-server` is README.md:94. Mine: a pid file per server and a stop by that pid, and the README line.
  - **`setup-tools.sh` isn't deploy-safe** (`npm install` into the linked node env, a `.venv` inside `app/`, `sed` on the harness homes). Mine: a small deploy step that copies `configs/` templates into the homes only when absent.
  - **Agent-test's paths:** `agent-test.sh` starts `harness/`, `watch-agent.py`, `collect-subagents.py` and `compare-runs.py` through `$LAB_DIR`, so they go in `extra`.
  - **The components** (llama.cpp with no sha256 today, CUDA 13.4 vs noble's CUDA 13.0 driver, ~41 GB of weights with no revision or sha256): split to HL-2, Inference Engineer.
  - **For Teamind (asked the Chief of Staff):** where the user's secrets file lives on a host, since a deployment's `app/data` is Teamind's data link; and that Teamind's `npm ci` runs install scripts (opencode-ai's postinstall writes opencode folders into the host user's home).
  - Python: standard library only on every job path (`hf` only in `get-models.sh`), so no Python env. Node: `package-lock.json` (four harnesses), no `.node-version`.
  **Resume:** the three script changes above (agent-test without git, pid stop, deploy-safe setup), then `deploy.toml` and `tasks.toml` with HL-2's components, then the closure dry run.
- 2026-10-22 17:29 Project Lead: the Chief of Staff filed both Teamind questions as TM-450 (for its System Architect) and cleared the interim plan: on a host the user places the two secrets by hand in `secrets.local.sh` at the deploy's root, listed in `local`; nothing ships it and no member reads it. `env.sh` now sources it when present (after the `data/secrets/` file), and `.gitignore` ignores it. Asked the Chief of Staff to add it to the registry's `logins`. **Resume:** as above; TM-450's answer may move the file.
- 2026-10-22 17:30 Project Lead: TM-450 answered (the System Architect's Proposal, fee6fb17; relayed by the Chief of Staff): (1) a project's secrets on a host go in `<deploy root>/data/secrets/` (700/600), reached from `app/` as `app/data/secrets`, placed by the user by hand, never copied by Teamind; `env.sh` already sources `$LAB_DIR/data/secrets/env.sh`, so once that build lands the `secrets.local.sh` line, its `.gitignore` line and the `logins` request go. (2) every node env's `npm ci` runs with HOME and XDG inside the env folder, and a project may set `ignore_scripts` plus a post script; both apply at the node env's next build. So `deploy.toml`'s node env can rely on (2), and opencode's postinstall stays inside the env. Teamind's lead adds: `deploy.toml` declares the host secrets by name (`secrets = ["env.sh"]`), and the dry run shows 已放 or 缺少. **Resume:** the three script changes; when Teamind says TM-450's build is in, drop `secrets.local.sh`.
- 2026-10-22 17:32 Project Lead: the Inference Engineer is in env.sh, the serve scripts and bench-moe.sh for HL-2, so the pid file and stop by pid (and README.md:94) moved to it, under HL-2, to keep us off the same lines. `agent-test.sh` now works without the repo's `.git`: `lab_is_repo` compares git's top level with `LAB_DIR` (a deployment inside another repo counts as not a repo); `lab_untracked` lists plain files with `find`, skipping `__pycache__` and `logs/` (on a host the homes, caches and logs are links into `local/`, which find doesn't follow); a SNAPSHOT eval stops with a clear message off a clone. Tested in the scratchpad (a deployment-like folder, a clone, a folder inside another repo): each caught only the file written outside; `bash -n` passes; agent-test itself isn't run on the HQ. **Resume:** the deploy-safe setup step, then `deploy.toml` and `tasks.toml`.
- 2026-10-22 17:33 Project Lead: the deploy-safe setup step is `scripts/place-configs.sh`, split out of `setup-tools.sh` (which now calls it, so the user's own machine behaves as before): copy each `configs/` template into its harness home only when absent, then rewrite old key forms to read `API_KEY`. A host runs only this; its npm packages come from Teamind's node env, and TM-450 keeps opencode's postinstall inside the env folder, so no post script is needed. Tested in a scratch copy (HEAD's env.sh and configs/): empty homes get the templates byte for byte, a second run keeps a harness's own edit, and old key forms are rewritten. **Resume:** `deploy.toml` and `tasks.toml`, with HL-2's components when they come, then the closure dry run.
- 2026-10-22 17:35 Project Lead: `.teamind/deploy.toml` is in, with eight entries (serve-main, serve-fim, serve-router, stop-server, bench, agent-test, compare-runs, place-configs), `[env.node]` Node 24, `local` (the harness homes, the caches, `logs/` so the pid files survive a swap, the tuning file, the interim secrets file) and HL-2's four components (llama.cpp b11469 CUDA 13.4, one per model at `models/<file stem>/`), each component carried only by the entries that use it. `config/tasks.toml` has five kinds (serve, bench, agent-test, compare-runs, setup) with `hosts = []` for the user to tick on 主機; the GPU kinds are `exclusive` with `min_free_gpu_mb = 6000`. `config/platform.toml` is new, and the manifest's `[pool]` is on. Checks: Teamind's `check_project.py` and `check_task_hosts.py` pass. The closure (with `--entries`, before the commit) lists the eight entries' 41 files; its unresolved items are the three host-placed files `env.sh` sources when present (TM-450's `secrets` key will name the data one), the `$LAB_DIR` launches already in agent-test's `extra`, and `[env.node]`, which `--entries` reads from main. The dry run lists these and doesn't stop on them (host_deploy.py:817). **Resume:** re-run the closure from main after this commit; then the user ticks zephyrus for `serve` and `agent-test`, and the first deployment proves llama.cpp, a model, `/health` and the `hi` eval (and on noble, CUDA0 at first start, per HL-2).
- 2026-10-22 17:36 Project Lead: the closure from main resolves all eight entries (43 files); the only unresolved items are the expected ones (host-placed files `env.sh` sources when present, and `$LAB_DIR` launches already in `extra`). HL-2 accepted and closed. Asked the user (below) to tick zephyrus for `serve` and `agent-test` on 主機 and press 部署. **Resume:** the user's tick and 部署; then a `serve` job on zephyrus (`/health` from `app/`), the `hi` eval by `agent-test`, logs attached here; then noble.
- 2026-10-22 17:44 Project Lead: Teamind's lead says TM-450's interim is in (468e5d57): `secrets.local.sh` is in our `logins` with its security.md row, and the guard closes our logins inside every deployment folder too. TM-450's full Proposal (host `data/secrets/`, `npm ci` with HOME and XDG inside the env folder) is still queued with Teamind's Systems Engineer. Until it's served, a deployment that builds the node env (the `agent-test` kind) would let opencode-ai's postinstall write folders into zephyrus's home. So the ask is now two steps: tick zephyrus for `serve` only and deploy (no node env), and tick `agent-test` once Teamind says the npm change is in. **Resume:** the user's `serve` tick and 部署 → a `serve` job (`/health` from `app/`); Teamind's word on TM-450's npm change → the user ticks `agent-test` → the `hi` eval; then noble.

## Comments
- **2026-10-22 17:36 專案經理:** **關注重點**：harness-lab 的部署設定好了，要你在 Teamind 的「主機」頁做兩件事：
  1. 在 harness-lab 的工作表把 **zephyrus** 勾給「本地模型伺服器」和「Harness 解題測試」（noble 等 zephyrus 跑通再勾）。
  2. 對 zephyrus 按 **部署**。第一次會在 zephyrus 上下載 llama.cpp（約 560 MB）和三個模型（共約 41 GB），每個都核對 sha256，總部不經手。
  祕密檔目前不需要：模型都是公開下載，伺服器也只聽本機。之後要開放給區網時，再把自己的 API_KEY 放到主機上（位置到時候告訴你）。
- **2026-10-22 17:44 專案經理:** **關注重點**：更正上一則，分兩步勾。現在只把 zephyrus 勾給「本地模型伺服器」，然後按部署；「Harness 解題測試」先別勾。原因是 Teamind 讓 npm 安裝只寫在自己資料夾內的修改還沒上線（TM-450），這時建 harness 的 node 環境，opencode 的安裝腳本會在 zephyrus 的家目錄留下資料夾。只跑伺服器不需要 node 環境，所以沒有這個問題。等 Teamind 改好，我再通知你勾「Harness 解題測試」。
