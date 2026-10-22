---
id: HL-2
title: "llama.cpp and the model weights as Teamind external components: pinned URLs, sha256, CUDA build per host, folder layout"
title_zh: "llama.cpp 與模型權重改成 Teamind 外部元件：固定網址、sha256、各主機的 CUDA 版本、資料夾配置"
status: verified
state: closed
closed_reason: done
closed_by: Project Lead
closed_at: 2026-10-22 17:35
type: feature
area: infra
severity: minor
priority: 
author: Project Lead
owner: Inference Engineer
handed: assigned / Inference Engineer
holder:
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
- [x] The component blocks, with real sha256 values and pinned URLs, sent to the Project Lead (or committed as a fragment it can merge); each sha256's source noted.
- [x] The CUDA choice per host, and its reason, written here.
- [x] The weights layout chosen, with the matching `env.sh` or serve-script change if any; `bash check.sh` passes.
- [x] Nothing downloaded on the HQ (metadata lookups only).

## Findings
(Inference Engineer, 2026-10-22.) The blocks are in `issues/HL-2/components.toml` (976ed10), for the Project Lead to merge into `.teamind/deploy.toml`. Nothing was downloaded on the HQ; every value comes from metadata.

- **sha256 sources:** llama.cpp's two archives from the GitHub API's asset `digest` (`/repos/ggml-org/llama.cpp/releases/tags/b11469`); each weight from its Hugging Face LFS oid (`/api/models/<repo>/tree/<commit>`), at the commit `main` pointed to on 2026-10-22, which is also the component's `version` and is in the `resolve/<commit>/` URL. Sizes are in the file's comments.
- **strip = 1 on both archives:** `.github/workflows/release.yml` at b11469 packs each with one top folder (`llama-b11469/`, `cudart-llama-b11469-bin-ubuntu-cuda-13.4-x64/`), so `llama-server` and the three CUDA libraries (`libcudart.so.13`, `libcublas.so.13`, `libcublasLt.so.13`) land side by side at the component's top, which the binaries find by their `$ORIGIN` rpath. `check = ["./llama-server", "--version"]`, `link = "vendor/llama.cpp/current"` (`env.sh`'s `LLAMA_BIN`).
- **CUDA per host: 13.4 on both, one `linux-x86_64` key, no `entries`.** Both have driver 580.178.04 (CUDA 13.0; `config/hosts.toml`, zephyrus's in its `torch_build` comment). A 13.4 build runs on a 13.0 driver by CUDA's minor-version compatibility, as long as no PTX has to be JIT-compiled, and the b11469 CUDA build ships real device code for both cards: `ggml/src/ggml-cuda/CMakeLists.txt`'s default list has `89-real` (RTX 4060 Laptop) and `120a-real` (RTX 5060 Ti). It is already proven on zephyrus: business-sim runs this exact build there (hosts.toml, BS-8). noble is covered by the same reasoning, first proven by its first real start (`--version` doesn't touch the GPU). 12.8 stays the hand fallback for an older driver. The contract couldn't pick a build by driver: prebuilt keys are distro/os/arch only, and two components can't share one `link`, so a 12.8 host would need its own component and link name.
- **Weights layout: one component per model,** each linked at `models/<file stem>/` (`models/Qwen3.6-35B-A3B-UD-Q4_K_XL/` and so on), recommended over one `models/` component because each repo has its own commit (one `version` couldn't pin three repos), and a new quant of one model re-downloads only it (not ~41 GB). Router mode at b11469 (`common/preset.cpp`, `load_from_models_dir`) scans one level of subfolders and names a model by its folder, so with the folder named as the file's stem the router's names, Pi's `llama.cpp/<name>` and `agent-test.sh` are unchanged, and `--models-dir "$MODELS_DIR"` stays. `env.sh`'s new `lab_model_path` finds a file in its folder or flat (`get-models.sh` by hand still writes flat); `serve-main.sh`, `serve-fim.sh` and `bench-moe.sh` use it. `models/` is git-ignored, so the links replace no tracked path; the lead should confirm Teamind creates `app/models/` as the links' parent.
- **Stop by pid (for HL-1, 6c98b8a):** each serve script writes `logs/serve-<main|fim|router>.pid` before `exec llama-server` (same pid) and refuses a second start; `scripts/stop-server.sh <name>` kills only that pid, after checking it is still this project's `$LLAMA_BIN/llama-server`. README's stop line no longer says `pkill`. Tested on the HQ with a stand-in binary, no model.

## Progress
- 2026-10-22 17:27 Project Lead: split from HL-1 after its script survey. Owner: Inference Engineer; brief at `.teamind/briefs/harness-lab-inference-engineer.md`. **Resume:** the Inference Engineer reads the brief and starts.
- 2026-10-22 17:29 Project Lead: dispatched (`team.sh send`, queued until the coordinator wakes it). **Resume:** its report; then merge the components into HL-1's `deploy.toml`.
- 2026-10-22 17:32 Inference Engineer: components in `issues/HL-2/components.toml` (976ed10), pid-file stop for HL-1 (6c98b8a), Findings written; `bash check.sh` passes. **Resume:** the lead merges the blocks into `deploy.toml`; on the first deploy, check noble's `llama-server` sees CUDA0 at its first start.
- 2026-10-22 17:35 Project Lead: accepted. Reviewed 976ed10 and 6c98b8a: the components went into `.teamind/deploy.toml` unchanged (83af88d), each with `entries` so only the deployments that serve or bench carry the ~41 GB; `lab_server_pid` checks the pid is still this project's llama-server before a stop; `logs/` is `local`, so the pid files survive a swap. The closure from main resolves every entry (43 files). What only a host can prove (a component's first install, noble's CUDA0 at first start, whether Teamind makes `app/models/` as the links' parent) moves to HL-1's first-deployment acceptance. Closed.
- **2026-10-22 17:33 Inference Engineer (harness-lab):** Status fixed (was assigned): components, CUDA choice and layout delivered; the lead merges them into deploy.toml
