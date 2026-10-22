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
holder: Project Lead
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
