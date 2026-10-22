---
id: HL-2
title: "llama.cpp and the model weights as Teamind external components: pinned URLs, sha256, CUDA build per host, folder layout"
title_zh: "llama.cpp 與模型權重改成 Teamind 外部元件：固定網址、sha256、各主機的 CUDA 版本、資料夾配置"
status: assigned
state: open
type: feature
area: infra
severity: minor
priority: 
author: Project Lead
owner: Inference Engineer
handed: assigned / Inference Engineer
holder: Inference Engineer
blocked_by: 
parent: HL-1
related: TM-404, TM-430
milestone: deploy
project: harness-lab
found: 2026-10-22
updated: 2026-10-22
---
## Request
(Project Lead.) Part of HL-1. On a host, llama.cpp and the weights are external components, downloaded there with their sha256 and never through the HQ (Teamind `wiki/design/projects.md`, "External components", TM-404: weights are a component with `prebuilt = { any = [...] }`, a prebuilt may list several files `{url, sha256, strip?, unpack?, inner?}`). Today nothing is checksummed: `scripts/install-llama.sh` fetches two GitHub release archives with no sha256, and `scripts/get-models.sh` runs `hf download` with no revision or sha256.

Write the `[[component]]` blocks for `.teamind/deploy.toml` (the Project Lead writes the rest of the file in HL-1 and merges yours):
- **llama.cpp b11469**, `linux-x86_64`: the llama and cudart archives with their sha256 (the GitHub API's asset `digest`), the right `strip` (`install-llama.sh:31` notes the folder depth varies), `check`, and `link = "vendor/llama.cpp/current"` so `env.sh`'s `LLAMA_BIN` default holds.
- **The CUDA build per host:** the scripts pin CUDA 13.4 (`LLAMA_CUDA`, per host 12.8 is allowed). noble's driver is CUDA 13.0 (Teamind `config/hosts.toml`); zephyrus's isn't recorded. Say which build each host gets and how a component expresses it (one component per CUDA version and `entries`, or another way the contract allows). Ask the lead if the contract can't express it.
- **The weights:** Qwen3.6-35B-A3B UD-Q4_K_XL, GLM-4.7-Flash UD-Q4_K_XL, the FIM Qwen2.5-Coder-1.5B Q8_0. URLs pinned to a Hugging Face commit, not `main`; sha256 from the LFS metadata. Choose the layout: one component linked at `models/` (a version bump re-downloads ~41 GB) or one per model (then `env.sh`'s `MODELS_DIR` and `serve-router.sh`'s `--models-dir` must follow; check whether router mode scans subfolders). Recommend one, with why.
- `scripts/install-llama.sh` and `scripts/get-models.sh` stay for hand use on the user's own machine; note in each that a host gets them as components.

## Acceptance
- [ ] The component blocks, with real sha256 values and pinned URLs, sent to the Project Lead (or committed as a fragment it can merge); each sha256's source noted.
- [ ] The CUDA choice per host, and its reason, written here.
- [ ] The weights layout chosen, with the matching `env.sh` or serve-script change if any; `bash check.sh` passes.
- [ ] Nothing downloaded on the HQ (metadata lookups only).

## Progress
- 2026-10-22 17:27 Project Lead: split from HL-1 after its script survey. Owner: Inference Engineer; brief at `.teamind/briefs/harness-lab-inference-engineer.md`. **Resume:** the Inference Engineer reads the brief and starts.
