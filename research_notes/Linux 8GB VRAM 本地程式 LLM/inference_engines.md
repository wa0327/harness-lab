# Local LLM inference engines on Linux for 8GB-VRAM NVIDIA + ~30GB RAM (as of 2026-10-07)

Target hardware: (A) RTX 4060 Laptop 8GB + Ryzen AI 9 HX 370 + 30GB RAM; (B) RTX 5060 Ti 8GB (Blackwell, sm_120) + Ryzen 9 9950X + 30GB RAM.
Research date: 2026-10-07. Dates of sources are noted inline; anything from 2025 is flagged as possibly outdated.

## 1. Current state of engines (versions, Linux + 8GB suitability)

### Takeaway
For 8GB VRAM + ~30GB RAM, the GGUF/llama.cpp family (mainline llama.cpp `llama-server`, ik_llama.cpp, and front-ends LM Studio/llmster and Ollama) is the practical choice, because it is the only family with mature, per-tensor CPU/GPU split for MoE experts on consumer hardware. vLLM / SGLang / ExLlamaV3 are GPU-resident engines aimed at models that fit in VRAM; KTransformers is CPU/GPU hybrid but targets 24GB+ GPUs and server CPUs.

### Cited Findings
**llama.cpp (mainline, ggml-org)**
- Latest release seen on the releases page: tag `b11465`, dated 7 October (the page fetch reported the year as "2024", which is almost certainly a summarizer error given the build number; treat it as a 2026-10-07 build). Linux CUDA prebuilt binaries are published for CUDA 12.8 and 13.4. — [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases)
- Builds are rolling (a new `bNNNN` tag for each merge). Recent notes cover SYCL GLM MLA prefill speedups, CUDA BF16 XIELU, and Vulkan iGPU fixes. — [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases)
- The server README lists `--fit` (default **on**: "adjust unset arguments to fit in device memory"), `--fit-target` (default 1024 MiB margin per device), `--cpu-moe`, `--n-cpu-moe`, `--override-tensor`, `--jinja` (now **enabled by default**), `--spec-type`, `--model-draft`, `-np/--parallel` (default -1 = auto), `--kv-unified`, `--cache-ram` (default 8192 MiB), `--ctx-checkpoints` (default 32), `--swa-full`, and router mode via `--models-dir`. — [llama-server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- Multi-Token Prediction (MTP) was merged into master on 2026-05-16 (PR #22673). — [cloudmagazin 2026-05-27](https://www.cloudmagazin.com/en/2026/05/27/llama-cpp-mtp-support-27b-modelle-1-7x-schneller-consumer/); [PR #22673](https://github.com/ggml-org/llama.cpp/pull/22673)
- The Anthropic Messages API (`/v1/messages`) was added to llama-server (PR #17570), announced 2026-01-19. — [HF blog: Anthropic Messages API in llama.cpp](https://huggingface.co/blog/ggml-org/anthropic-messages-api-in-llamacpp)

**ik_llama.cpp (ikawrakow fork)**
- A fork with "better CPU and hybrid GPU/CPU performance": fused MoE ops, IQK quant family, Trellis quants (IQ1_KT…IQ4_KT), IQ2_K…IQ6_K, MXFP4, MLA/FlashMLA-3 for DeepSeek, multi-GPU graph split, **MTP decoding, self-speculative decoding**, dynamic tensor offload, and "smart expert reduction". It supports Qwen3, DeepSeek-V4, GLM-5, and others. — [ik_llama.cpp README](https://github.com/ikawrakow/ik_llama.cpp)
- Only the CPU (AVX2+/NEON) and CUDA backends get real attention. CUDA needs Turing or newer, and some features (FlashMLA-3) need Ampere or newer. — [ik_llama.cpp README](https://github.com/ikawrakow/ik_llama.cpp)
- Caveats: do not use `-rtr` (run-time repack) with hybrid CPU/GPU MoE, because it hurts prompt processing badly. Unsloth `_XL` GGUFs that contain f16 tensors may fail. Graph-parallel mode with partial offload can give incoherent output (workaround: `-cuda graphs=0`). — [ik_llama.cpp README](https://github.com/ikawrakow/ik_llama.cpp); [Doctor-Shotgun guide, 2026-01-30](https://huggingface.co/blog/Doctor-Shotgun/llamacpp-moe-offload-guide)
- The optimized CPU kernels require AVX2 + FMA. — [Doctor-Shotgun guide](https://huggingface.co/blog/Doctor-Shotgun/llamacpp-moe-offload-guide)
- The README news list read during this research was mostly 2025 entries (FlashMLA-3 May 2025, tensor overrides Feb 2025, Q8_KV Feb 2025). The 2026 cadence was not confirmed. — [ik_llama.cpp README](https://github.com/ikawrakow/ik_llama.cpp)

**LM Studio / llmster / lms**
- LM Studio now comes in three parts: the desktop app, **llmster** (a headless daemon with no GUI, meant for Linux servers, GPU rigs without displays, and CI), and **lms** (the CLI shipped with both). It serves OpenAI-compatible, Anthropic-compatible, and native REST APIs on `localhost:1234`. — [lmstudio vs llmster vs lms](https://lmstudio.ai/docs/app/basics/lmstudio-vs-llmster-vs-lms)
- Install: `curl -fsSL https://lmstudio.ai/install.sh | bash`, then `lms daemon up` / `lms daemon status`. Docs recommend running it under systemd on Linux servers. — [LM Studio headless llmster docs](https://lmstudio.ai/docs/developer/core/headless_llmster); [LM Studio headless docs](https://lmstudio.ai/docs/developer/core/headless)
- One third-party source says headless llmster launched in January 2026. — [kunalganglani.com](https://www.kunalganglani.com/blog/lm-studio-vs-ollama)
- The changelog page currently shows a release labelled "Bionic 1.1.7" dated 2026-10-01, which ships "llama.cpp 2.48.0 extension packs". v1.1.3 lists "MTP speculative decoding for more compatible models" and v1.1.4 lists "tool-call argument streaming". (The version naming looks like a 2026 scheme change from 0.3.x/0.4.x. It was not verified beyond this one fetch.) — [LM Studio changelog](https://lmstudio.ai/changelog)

**Ollama**
- The latest release seen is v0.40.0 (2026-09-25). Its highlights are MLX-by-default on Apple Silicon and "decision models" (v0.35.0). The release notes reviewed say nothing about MoE expert offload, KV-cache quantization, or MTP. — [Ollama releases](https://github.com/ollama/ollama/releases)
- The new Ollama engine (2025-09-23) measures memory exactly instead of estimating it. A PR adding `num_moe_offload` (MoE experts to CPU) was **not merged**. Maintainers want to "configure this automatically rather than making the user configure it", and the old llama engine gets no new features. — [summary of Ollama issue/PR discussion](https://github.com/ollama/ollama/issues/11005) (via search snippet; the specific PR text was not fetched)

**vLLM / SGLang**
- Prebuilt vLLM PyPI wheels and Docker images have failed on RTX 50-series (SM120/121) with "no kernel image" errors. The recommended fix is to build from source with CUDA 12.8+ and `TORCH_CUDA_ARCH_LIST` including 12.0. — [vLLM issue #35432](https://github.com/vllm-project/vllm/issues/35432); [vLLM forum: RTX5090 torch 2.9.0 cu128](https://discuss.vllm.ai/t/vllm-on-rtx5090-working-gpu-setup-with-torch-2-9-0-cu128/1492)
- Field report: AWQ models run on an RTX 5060 Ti (SM_120) with `awq_marlin` quantization + `TRITON_ATTN` backend (WSL2). — [vLLM forum field report](https://discuss.vllm.ai/t/field-report-awq-on-rtx-5060-ti-sm-120-blackwell-awq-marlin-triton-attn-working/2463)

**ExLlamaV3 / TabbyAPI**
- ExLlamaV2 is archived and development continues in ExLlamaV3 (EXL3 format, based on QTIP). EXL3 supports tensor/expert parallelism, continuous batching, speculative decoding, cache quantization, multimodal, and LoRA. TabbyAPI serves it with an OpenAI-compatible endpoint and only runs EXL2/EXL3 weights. — [ai-tldr: exllamav3](https://ai-tldr.dev/tools/exllamav3/); [bestllmfor: install TabbyAPI](https://bestllmfor.com/how-to/install-tabbyapi-self-host/)

**KTransformers**
- Latest version is v0.7.0 (2026-08-17), which adds AVX512 x86 support (no AMX needed) for LoRA fine-tuning and native RAWINT4 experts. News items run through 2026-09-13 (Kimi K2.5/K2.6 LoRA). Supported models include DeepSeek-V4-Flash, Kimi K2.5/2.6, GLM-5.3-flash, MiniMax-M3, Qwen3-30B-A3B, and LLaMA 4. Its kernels target AMX/AVX512/AVX2. — [KTransformers GitHub](https://github.com/kvcache-ai/ktransformers)
- Integrated into SGLang in Oct 2025 (GPU tensor parallelism + CPU/GPU hybrid expert parallelism). — [LMSYS blog 2025-10-22](https://www.lmsys.org/blog/2025-10-22-KTransformers)
- Single-GPU reference configs use 24GB VRAM. — [KTransformers GitHub](https://github.com/kvcache-ai/ktransformers)
- A third-party blog claims a "v0.6.3 (July 2026)" lets Kimi K3/GLM-5.2 run on an RTX 3060 12GB. This was **not corroborated** by the repo and the source looks low quality. — [dailyaiworld](https://www.dailyaiworld.com/blogs/ktransformers-cpu-gpu-inference-guide-2026)

### Inferences
- With 8GB VRAM and 30GB RAM, the realistic upper bound is a ~30–35B-total / ~3B-active MoE at Q4 (≈18–21GB of weights), with experts in RAM and attention + KV on the GPU. Bigger MoEs (80B+) will not fit in 30GB RAM at usable quants. KTransformers' server-scale design (AMX, 24GB+ GPU, very large RAM) gives this hardware no advantage over llama.cpp.
- vLLM, SGLang, and ExLlamaV3 only make sense here for small dense models (≤8B at 4-bit) that fit fully in 8GB. Even then, llama.cpp is simpler and competitive for single-user use. Their strengths (batching, throughput) matter little for one developer.
- Ollama is the easiest to use but the weakest for MoE-larger-than-VRAM: there is no user-facing per-layer expert offload, so it falls back to whole-layer offload.

### Gaps
- I did not find an official ExLlamaV3/TabbyAPI 2026 release number or any 8GB-specific MoE guidance.
- SGLang standalone version and sm_120 status as of Oct 2026 were not verified.
- No newer engine built specifically for 8GB consumer MoE offload (beyond the llama.cpp forks) turned up in the searches.
- The LM Studio "Bionic 1.1.x" naming and Ollama v0.40.0 "decision models" each come from a single fetch of the changelog/release page. Please re-check before quoting.

## 2. MoE expert offloading to CPU: flags, engines, concrete commands

### Takeaway
Keep all layers on the GPU (`-ngl 999`/`all`) and push only the routed-expert FFN tensors to CPU. Use `--cpu-moe` (all experts), `--n-cpu-moe N` (experts of the first N layers), or `-ot` regex for fine control. Then lower N until VRAM is just about full. On 8GB this lets a 35B-A3B model run at roughly 15–45 tok/s depending on the model and RAM.

### Cited Findings
- Flag semantics: `--cpu-moe` keeps all MoE weights on CPU. `--n-cpu-moe N` keeps the MoE weights of the **first N layers** on CPU. `--override-tensor`/`-ot` takes `pattern=buffer_type`. — [llama-server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- Equivalent forms: `-ot "exps=CPU"` ≡ `--cpu-moe`. Fine-grained example: `-ot "blk\.([0-9]|[1-2][0-9]|30)\.=CUDA0,exps=CPU"`. Recommended batches for MoE offload are `-b 4096 -ub 4096`, because larger ubatch amortizes the transfer of CPU-resident experts to the GPU during prompt processing. The default threshold for GPU-offloaded prompt processing is 32 tokens (env `GGML_OP_OFFLOAD_MIN_BATCH`). Other flags used: `--no-mmap`, `-t 16`, `-fa on`, `--jinja`. — [Doctor-Shotgun MoE offload guide, 2026-01-30](https://huggingface.co/blog/Doctor-Shotgun/llamacpp-moe-offload-guide)
- The same guide recommends disabling auto-fit while tuning, so OOM is visible instead of silently adjusted. — [Doctor-Shotgun guide](https://huggingface.co/blog/Doctor-Shotgun/llamacpp-moe-offload-guide)
- ik_llama.cpp-only extras: `--merge-qkv`, `-gr` (graph reuse), `-sm graph`, `-mla 3 -amb 512` (DeepSeek), and the `llama-sweep-bench` tool. — [Doctor-Shotgun guide](https://huggingface.co/blog/Doctor-Shotgun/llamacpp-moe-offload-guide)
- Tuning procedure: set `-c` to the real workload, start `--n-cpu-moe` high, step it down while measuring tok/s, stop when speed collapses (silent VRAM spill), then back off one step. Sweep example: `for n in 32 28 24 20 16 12; do llama-bench -m ./qwen3.6-35b-a3b-IQ4_NL.gguf -ngl 999 --n-cpu-moe $n; done`. — [openclawdc --n-cpu-moe guide (2026)](https://openclawdc.com/blog/llama-cpp-moe-offload-flags-explained/)
- 12GB example: `llama-server -m ./qwen3.6-35b-a3b-IQ4_NL.gguf -ngl all --n-cpu-moe 25 --flash-attn on -lm none -c 65536 --host 127.0.0.1 --port 8080` gives 51–53 tok/s on an RTX 3060 12GB + 32GB DDR5 at 64K context. `-lm none` (no mmap) cut system RAM use from 98% to 71% for one user. RTX 5090 sweep: 54 t/s at n=20, 64.5 at 16, 69.4 at 12, then a collapse to 27.5 below 12 (VRAM spill). — [openclawdc guide](https://openclawdc.com/blog/llama-cpp-moe-offload-flags-explained/)
- The same source says MoE offload is "most beneficial for 12–24GB" cards and gives no explicit 8GB recipe. — [openclawdc guide](https://openclawdc.com/blog/llama-cpp-moe-offload-flags-explained/)
- 8GB data points:
  - LFM2.5-8B-A1B with `--cpu-moe` on an 8GB GPU: 45 tok/s, against 27 tok/s CPU-only. — [search summary of localllm.in 8GB benchmarks / related guides](https://localllm.in/blog/best-local-llms-8gb-vram-2025)
  - Qwen3.6-35B-A3B on an RTX 4060 8GB + 12-core CPU + 64GB DDR4 with llama.cpp: 15–18 tok/s. Qwen3.8-27B (dense) on the same machine: 5–6 tok/s ("practically unusable"). — [r/LocalLLaMA snapshot 2026-09-04](https://reddit.sentinel-team.org/posts/1w6y128/snapshots/2026-09-04T21%3A20%3A12.3645Z)
- Raising `--n-cpu-moe` from 8 to 30 on 12GB doubled Qwen3 35B-A3B decode from 17 to 34 tok/s. The source attributes this to relieving VRAM contention; the likely real reason is avoiding spill. — [aiweekly](https://aiweekly.co/alerts/qwen3-moe-cpu-expert-offload-doubles-decode-speed-on-12gb-vram)
- **LM Studio**: 0.3.23 (2025-08-12) added the advanced load setting "Force Model Expert Weights onto CPU", built on the same mechanism as llama.cpp `--n-cpu-moe`. It suits low-VRAM machines, and the docs advise leaving it off if the whole model fits. — [LM Studio 0.3.23 blog](https://www.lmstudio.ai/blog/lmstudio-v0.3.23). In 0.3.23 it was an all-or-nothing toggle. The workaround is "GPU offload = max + Force experts onto CPU". — [lmstudio-bug-tracker #900 (2025-08-14)](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/900)
- **Ollama**: no `num_moe_offload` or equivalent was merged; maintainers prefer automatic placement. — [Ollama issue #11005 / PR discussion](https://github.com/ollama/ollama/issues/11005)
- **Jan** added a `--n-cpu-moe` input to its llama.cpp extension's Model Settings UI. — [Jan commit mirror](https://git.biohazardvfx.com/Nicholai/jan/src/commit/706dad268794018fd0600849c0abbbe4a182a7ab)

### Inferences
- Suggested 8GB starting command (adapted from the cited 12GB recipe; **not a measured config**):
  `llama-server -m Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf -ngl 999 --n-cpu-moe 36 -fa on -c 32768 -ctk q8_0 -ctv q8_0 -b 2048 -ub 2048 -t <physical cores> --no-mmap --jinja --host 127.0.0.1 --port 8080`
  Then sweep `--n-cpu-moe` down until VRAM is ~7.3–7.6GB. Qwen3-35B-A3B-class models have ~40 layers. Note `--fit` is on by default and may adjust unset params; for deterministic tuning pass `--fit off`.
- RAM budget: a 35B-A3B Q4 GGUF is ~20GB. With 30GB system RAM, `--no-mmap`/`-lm none` avoids page-cache double counting and leaves roughly 8–10GB for the OS, IDE, and browser. Q5 or larger quants of 35B, or any 80B MoE, will not fit.
- Machine B (9950X, DDR5 dual-channel, PCIe 5.0 x8 on the 5060 Ti) should beat machine A on both decode (more RAM bandwidth for experts in RAM) and prompt processing (more PCIe bandwidth for expert upload at large ubatch). Machine A's HX 370 laptop uses LPDDR5X/DDR5 with a laptop PCIe link and power-shared CPU/GPU.
- Use the physical core count for `-t` (16 on the 9950X). The HX 370 mixes Zen5 and Zen5c cores (12 cores total), so test `-t 8` against `-t 12`.

### Gaps
- No direct published benchmark for the exact target hardware (HX 370 + 4060 Laptop, or 9950X + 5060 Ti 8GB) with `--n-cpu-moe`.
- No 2026 head-to-head ik_llama.cpp vs mainline numbers for 8GB + Qwen3.6-35B-A3B were found. Sources only say ik is "specifically optimized for MoE hybrid".
- I could not confirm whether current LM Studio (2026) has a per-layer count slider instead of the 2025 on/off toggle.

## 3. KV cache quantization, flash attention, context vs VRAM, speculative decoding / MTP

### Takeaway
Flash attention defaults to `auto` in llama.cpp. KV-cache quantization (`q8_0`) is a memory feature, not a speed feature: use it only when f16 KV would push expert layers off the GPU or limit context. MTP has been in mainline llama.cpp since 2026-05-16 (`--spec-type draft-mtp`) and gives up to ~1.7–2x decode on supported models (Qwen3.6). It is also in ik_llama.cpp and LM Studio.

### Cited Findings
- `--cache-type-k/v` options: f32, f16 (default), bf16, q8_0, q4_0, q4_1, iq4_nl, q5_0, q5_1. `--flash-attn` takes on/off/auto (default **auto**). — [llama-server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- "f16 KV cache is faster than q8_0 when it fits": quantization adds per-token conversion overhead. Flash attention reduces KV VRAM and speeds up attention. Smaller `-b/-ub` frees VRAM (e.g. `-b 1024 -ub 256` on 16GB). — [openclawdc guide](https://openclawdc.com/blog/llama-cpp-moe-offload-flags-explained/)
- ik_llama.cpp adds a `Q8_KV` 8-bit KV-cache type (Feb 2025). — [ik_llama.cpp README](https://github.com/ikawrakow/ik_llama.cpp)
- MTP in llama.cpp: merged 2026-05-16 (PR #22673). The MTP heads ship inside the same GGUF and use an extra MTP context (<~10% extra memory). Enable with `--spec-type draft-mtp`. Reported gains are ~2x in favourable setups; Qwen3.6-27B on an RTX 3090 went from 38 to 65 tok/s (1.7x). — [cloudmagazin](https://www.cloudmagazin.com/en/2026/05/27/llama-cpp-mtp-support-27b-modelle-1-7x-schneller-consumer/); [mer.vin, 2026-05](https://mer.vin/2026/05/run-qwen-3-6-mtp-in-llama-cpp-faster-local-inference-with-built-in-speculative-decoding/); [Unsloth MTP docs](https://unsloth.ai/docs/models/mtp)
- Classic draft-model speculative decoding is still available via `--model-draft`, with `--spec-type` as a comma-separated list. — [llama-server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- LM Studio v1.1.3 added "MTP speculative decoding for more compatible models". — [LM Studio changelog](https://lmstudio.ai/changelog)
- Prompt/context reuse in llama-server: `--cache-ram` (default 8192 MiB host-RAM prompt cache) and `--ctx-checkpoints` (default 32 per slot). These matter for agent harnesses that resend long prefixes, and for hybrid/SWA models where KV cannot be truncated. `--swa-full` is off by default. — [llama-server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)

### Inferences
- On 8GB with experts on CPU, each GiB freed by q8_0 KV can move about one more layer's experts to the GPU. The trade is roughly slightly slower attention for faster expert compute. Test both. For 64K+ context on a 35B-A3B (hybrid attention models like Qwen3.6 have small KV), f16 KV may already fit.
- MTP gains on MoE with CPU-resident experts are probably smaller than the dense-GPU numbers above, since verification batches still touch CPU experts. This needs measuring. `--cache-ram 8192` competes with the 30GB RAM budget; lower it (e.g. 2048–4096) if RAM is tight.
- Keep `-np 1` (single slot) for one-user agentic coding on 8GB. Auto-parallel slots split the context/KV budget.

### Gaps
- No 8GB-specific measurements of MTP speedup with `--n-cpu-moe` were found.
- Whether MTP works with CPU-offloaded experts without regressions in mainline was not confirmed.

## 4. API compatibility: OpenAI, Anthropic /v1/messages, tool calling / Jinja

### Takeaway
All three easy paths now expose an Anthropic-compatible `/v1/messages` usable with Claude Code-style harnesses: llama-server (since ~Jan 2026), LM Studio (since 0.4.1), and Ollama. llama-server has the most complete implementation (count_tokens, tool_use, thinking, vision). OpenAI `/v1/chat/completions` and `/v1/responses` are universal.

### Cited Findings
- **llama-server**: `POST /v1/messages` (streaming), `POST /v1/messages/count_tokens`, tool_use/tool_result, vision (base64 + URL), and extended thinking. Requests are converted internally to the OpenAI format. Claude Code example: `llama-server -hf unsloth/Qwen3-Next-80B-A3B-Instruct-GGUF:Q4_K_M` then `ANTHROPIC_BASE_URL=http://127.0.0.1:8080 claude`. Announced 2026-01-19, PR #17570. — [HF blog](https://huggingface.co/blog/ggml-org/anthropic-messages-api-in-llamacpp); [PR #17570](https://github.com/ggml-org/llama.cpp/pull/17570)
- The llama-server README documents the OpenAI `/v1/responses` endpoint. `--jinja` is enabled by default, and `--reasoning-format` (none/deepseek/deepseek-legacy) controls whether thoughts go into `reasoning_content`. — [llama-server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- **LM Studio**: Anthropic-compatible `/v1/messages` since 0.4.1. Claude Code setup: `export ANTHROPIC_BASE_URL=http://localhost:1234; export ANTHROPIC_AUTH_TOKEN=lmstudio; claude --model openai/gpt-oss-20b`. It streams the SSE events message_start/content_block_delta/message_stop. — [LM Studio blog: Claude Code](https://lmstudio.ai/blog/claudecode); [LM Studio Anthropic compat docs](https://lmstudio.ai/docs/developer/anthropic-compat)
- LM Studio added tool-call argument streaming in v1.1.4. — [LM Studio changelog](https://lmstudio.ai/changelog)
- **Ollama**: supports `/v1/messages` with streaming, tool calling, basic extended thinking, and base64 vision, and has a Claude Code integration. Limitations: no `tool_choice` forcing, no count_tokens endpoint, no prompt caching, approximate token counts, no URL images. — [Ollama Anthropic compatibility docs](https://docs.ollama.com/api/anthropic-compatibility)
- **TabbyAPI**: OpenAI-compatible endpoint. — [bestllmfor TabbyAPI](https://bestllmfor.com/how-to/install-tabbyapi-self-host/)
- **KTransformers**: the repo docs do not mention OpenAI/Anthropic API (serving goes through SGLang). — [KTransformers GitHub](https://github.com/kvcache-ai/ktransformers)

### Inferences
- For Claude Code / agent harnesses that call `count_tokens` or need `tool_choice`, llama-server is the most compatible local backend. Ollama's missing count_tokens and tool_choice may break some harness features.
- Tool-call reliability depends on the GGUF's embedded Jinja template. Use recent GGUFs (Unsloth/ggml-org) or pass `--chat-template-file` when a template is broken. That flag was not verified in this fetch; flagged as an inference.

### Gaps
- Whether ik_llama.cpp has ported `/v1/messages` was not confirmed. The README mentions none.
- LM Studio's Anthropic endpoint support for count_tokens and thinking blocks was not verified.

## 5. Blackwell (RTX 50xx, sm_120) and laptop concerns

### Takeaway
sm_120 needs CUDA ≥ 12.8 and driver ≥ 570. llama.cpp ships Linux CUDA 12.8 and 13.4 prebuilts, and source builds should set `-DCMAKE_CUDA_ARCHITECTURES=120`. vLLM historically needed source builds for sm_120. On the 4060 Laptop, the main risk is the Linux default power limit (as low as 60W versus a 140W spec) unless `nvidia-powerd` (Dynamic Boost) is running.

### Cited Findings
- llama.cpp on sm_120 needs CUDA Toolkit 12.8 or newer (the first with native sm_120), an NVIDIA driver from the 570 series or newer, and the build flags `-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120`. Check with `nvidia-smi --query-gpu=compute_cap --format=csv` (expect 12.0). Pitfalls: "no kernel image is available" means a rebuild is needed; "Unsupported gpu architecture" means nvcc is older than 12.8; a missing `GGML_CUDA` causes silent CPU fallback; a stale CMake cache should be removed. (Guide updated Sept 2026.) — [bestllmfor sm120 build guide](https://bestllmfor.com/guides/llama-cpp-cuda-blackwell-sm120-build/)
- llama.cpp Linux CUDA prebuilts exist for 12.8 and 13.4. — [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases)
- PyTorch has supported Blackwell since 2.7.0 + CUDA 12.8 (April 2025). vLLM prebuilt wheels/Docker have crashed on SM120/121, and building from source with arch 12.0 is the fix. — [vLLM issue #35432](https://github.com/vllm-project/vllm/issues/35432); [vLLM forum: RTX 5090 setup](https://discuss.vllm.ai/t/vllm-on-rtx5090-working-gpu-setup-with-torch-2-9-0-cu128/1492)
- RTX 5060 Ti + vLLM: AWQ works with `awq_marlin` + `TRITON_ATTN`. — [vLLM forum field report](https://discuss.vllm.ai/t/field-report-awq-on-rtx-5060-ti-sm-120-blackwell-awq-marlin-triton-attn-working/2463)
- Laptop power: on a Legion 5 with an RTX 4060 Laptop, the Linux power limit sat at 60W against a 140W spec. `nvidia-powerd` (Dynamic Boost) controls the allocation; enable it with `sudo systemctl enable --now nvidia-powerd.service`. Results vary by driver. — [NVIDIA forum](https://forums.developer.nvidia.com/t/the-default-power-limit-of-my-4060-laptop-halves-its-performance/294699); [NVIDIA driver README: Dynamic Boost on Linux](https://download.nvidia.com/XFree86/Linux-x86_64/580.126.18/README/dynamicboost.html)
- Ubuntu 25.04 enables NVIDIA Dynamic Boost by default. — [search summary citing Yahoo Tech / windowsreport](https://windowsreport.com/nvidia-limiting-gpu-power-linux-laptops/)

### Inferences
- For hybrid MoE, decode is often limited by CPU/RAM bandwidth rather than the GPU, so a laptop power cap hurts prompt processing more than decode. CPU power sharing on the HX 370 (Dynamic Boost moves watts between CPU and GPU) can still cut decode speed when experts run on CPU.
- Hybrid graphics: run the server headless on the dGPU. The iGPU drives the display, so all 8GB of VRAM is available to the model. Check with `nvidia-smi` that no Xorg/gnome-shell process holds dGPU memory. This is common practice but not sourced here.
- Ollama/LM Studio bundle their own CUDA runtimes, so Blackwell support depends on their bundled llama.cpp build. Recent versions (2026) should include sm_120, but this was not explicitly verified.

### Gaps
- Whether `nvidia-powerd`/Dynamic Boost works on AMD-CPU laptops (HX 370) was not confirmed. NVIDIA's README lists platform requirements that were not read in full.
- No source confirmed sm_120 status in the bundled runtimes of the current Ollama v0.40 or LM Studio.
- PCIe link width of the RTX 5060 Ti (x8) and its effect on expert-offload prompt processing was not sourced.

## 6. Ease of use vs performance ranking (for 8GB + MoE offload, Linux)

### Takeaway
On performance per GB, ik_llama.cpp ≥ llama.cpp > LM Studio (llmster) > Ollama, with vLLM/SGLang/ExLlamaV3 only relevant for models that fit in VRAM. On ease of use, Ollama > LM Studio/llmster > llama.cpp > ik_llama.cpp > vLLM/SGLang/ExLlamaV3 > KTransformers. LM Studio/llmster is the best balance: it is llama.cpp-based, has expert-to-CPU offload, Anthropic + OpenAI APIs, MTP, and a headless daemon.

### Cited Findings
- ik_llama.cpp is described as the recommended choice when MoE CPU offload is the priority (fused MoE, IQK kernels). — [Doctor-Shotgun guide](https://huggingface.co/blog/Doctor-Shotgun/llamacpp-moe-offload-guide); [towardsai GPU-poor guide 2026](https://pub.towardsai.net/a-gpu-poors-guide-to-local-llm-inference-in-2026-48d59cafd215)
- llama.cpp exposes every relevant knob: `--n-cpu-moe`, `-ot`, `--fit`, KV types, MTP, and the Anthropic API. — [llama-server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- LM Studio offers a GUI/daemon with a forced-experts-to-CPU option, OpenAI + Anthropic APIs, and MTP. — [LM Studio 0.3.23](https://www.lmstudio.ai/blog/lmstudio-v0.3.23); [LM Studio changelog](https://lmstudio.ai/changelog); [LM Studio Claude Code blog](https://lmstudio.ai/blog/claudecode)
- Ollama is the simplest and has the Anthropic API, but no user-controlled expert offload. — [Ollama Anthropic docs](https://docs.ollama.com/api/anthropic-compatibility); [Ollama issue #11005](https://github.com/ollama/ollama/issues/11005)
- vLLM needs source builds on sm_120 and does not do llama.cpp-style per-expert CPU placement. — [vLLM issue #35432](https://github.com/vllm-project/vllm/issues/35432)
- KTransformers targets AMX/AVX512 server CPUs and 24GB+ GPUs. — [KTransformers GitHub](https://github.com/kvcache-ai/ktransformers)

### Inferences
- Recommended stack for the user's two machines: mainline `llama-server` (prebuilt CUDA 12.8/13.4 Linux binary, or a source build with `CMAKE_CUDA_ARCHITECTURES=89;120` to cover both GPUs) with `--n-cpu-moe` tuning, MTP where the GGUF has heads, and `/v1/messages` for Claude Code. Try ik_llama.cpp as a performance A/B (beware Unsloth `_XL` f16 tensor issues and `-rtr`). Use LM Studio/llmster as the convenient fallback, and avoid Ollama for models larger than VRAM.

### Gaps
- No single 2026 benchmark compares all of these engines on the same 8GB hardware. The ranking is a synthesis, not a measurement.
