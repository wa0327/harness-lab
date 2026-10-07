# Measured performance of local coding LLMs on 8GB-VRAM NVIDIA GPUs + ~32GB RAM (2025 – Oct 2026)

Research date: 2026-10-07. Source-quality caveat up front: **many top search results for "X on RTX 4060" are auto-generated calculator/SEO pages** (willitrunai.com, modelfit.io, llmconfigurator.com, hardwarepedia, specpicks, localaimaster calculators). These pages give *estimates*, not measurements, and they badly contradict real measurements. For example, willitrunai lists Qwen3-Coder-30B-A3B on an RTX 4060 8GB as "Too big" at ~4.5 tok/s, while a real user measured ~30 tok/s generation on an 8GB card with `--n-cpu-moe` ([willitrunai](https://willitrunai.com/models/qwen-3-coder-30b-a3b) vs [dev.to](https://dev.to/upayanghosh/from-oom-to-262k-context-running-qwen3-coder-30b-locally-on-8gb-vram-1ej1)). I excluded those estimates from the findings below. Measured data from real 8GB cards is sparse, and almost all of it comes from desktops.

## 1. Measured tok/s for MoE coding models (Qwen3-Coder-30B-A3B, gpt-oss-20b/120b, GLM Flash, Qwen3.5/3.6-35B-A3B) on 8GB cards with CPU expert offload

### Takeaway
On an 8GB desktop card with 32GB RAM, the 30B-A3B-class MoE models (Qwen3-Coder-30B-A3B, Qwen3.5/3.6-35B-A3B) generate at about **15–32 tok/s** with llama.cpp `--n-cpu-moe`. The best measured 8GB result is ~32 tok/s generation and only ~40–52 tok/s prompt eval (Qwen3-Coder-30B-A3B Q4_K_XL, RTX 3060 Ti). gpt-oss-120b does not fit in 32GB of RAM. For gpt-oss-20b on 8GB cards there are official flag recipes but no published measured tok/s.

### Cited Findings
**Qwen3-Coder-30B-A3B (desktop, RTX 3060 Ti 8GB, i5-14600KF, ~32GB RAM, Windows; Q4_K_XL GGUF ~17.6GB; article undated, the page shows "May 5, 2024", which cannot be right because Qwen3-Coder shipped in July 2025 and TurboQuant is a 2026 fork):**
- Stock llama.cpp `--cpu-moe` (all experts on CPU), ctx 32768: 4,388 MB VRAM, **2.78 tok/s prompt eval, 13.38 tok/s generation** — [dev.to / upayanghosh](https://dev.to/upayanghosh/from-oom-to-262k-context-running-qwen3-coder-30b-locally-on-8gb-vram-1ej1)
- `--n-cpu-moe 40`, ctx 32768: 7,265 MB VRAM (760 MiB free), **51.63 tok/s prompt eval, 32.49 tok/s generation**. The author called this the "practical optimal" setting — [dev.to](https://dev.to/upayanghosh/from-oom-to-262k-context-running-qwen3-coder-30b-locally-on-8gb-vram-1ej1)
- `--n-cpu-moe 42`: 44.49 tok/s prompt eval, 30.26 tok/s generation (same article, per search snippet) — [dev.to](https://dev.to/upayanghosh/from-oom-to-262k-context-running-qwen3-coder-30b-locally-on-8gb-vram-1ej1)
- TurboQuant fork, **262,144 ctx**, `--cache-type-k turbo4 --cache-type-v turbo3 --flash-attn on --batch-size 256 --ubatch-size 64 --no-mmap --mlock`: 7,525 MB VRAM, **40.87 tok/s prompt eval, 29.13 tok/s generation** — [dev.to](https://dev.to/upayanghosh/from-oom-to-262k-context-running-qwen3-coder-30b-locally-on-8gb-vram-1ej1)
- Note: these "prompt eval" numbers come from short prompts with small ubatch (64–256). They do not show the pp throughput you would get on long prompts with a large ubatch (see section 2).

**Qwen3.5-35B-A3B (laptop, RTX 2060 6GB, i7-9750H, 32GB RAM, Windows 11), 2026-03-29:**
- Q4_K_M, `-ngl 99 --n-cpu-moe 99` (all experts on CPU), mmproj on CPU to save ~600MB VRAM: **350–400 tok/s prefill, ~15 tok/s generation at 102K context** — [llama.cpp Discussion #21112 (Dampfinchen)](https://github.com/ggml-org/llama.cpp/discussions/21112)
- The high prefill despite all experts on CPU is consistent with llama.cpp's "GPU offload prompt processing" path, which streams the expert weights over PCIe for large batches (section 2).

**Qwen3.5-35B-A3B (desktop, RTX 3070 8GB, 16GB DDR4, PCIe 3.0 NVMe), 2026:**
- Best result in a custom offload project: **10.20 tok/s** with n_gpu=10, n_batch=32, q8_0 KV, flash_attn, Q4_K_M (~15.6GB). The 16GB of RAM forced partial mmap/flash streaming, so this is a RAM-starved worst case — [AlexChen31337/gemma4-moe-offload](https://github.com/AlexChen31337/gemma4-moe-offload)
- The same repo's Gemma 4 26B-A4B test on the RTX 3070 8GB had no final measurements published — [GitHub](https://github.com/AlexChen31337/gemma4-moe-offload)

**Qwen3.6-35B-A3B on RTX 3070 8GB:** A knightli.com deployment note (2026-05-22) appeared in search ("Running Qwen3.6-35B Locally on an RTX 3070 8GB … `--n-cpu-moe 999`, `--flash-attn on`, quantized cache") but returned 404 when fetched. The search snippet quoted "134.44 tokens/second in prompt processing (7.44 ms/token)" for an 8GB `--n-cpu-moe` setup with 64–96GB RAM. That figure is unverified — [knightli.com (404)](https://knightli.com/en/2026/05/22/rtx-3070-8gb-qwen36-35b-llama-cpp-local-deployment/)

**gpt-oss-20b on 8GB:**
- The official llama.cpp gpt-oss guide gives recipes for an **RTX 2060 8GB**: full context `llama-server -hf ggml-org/gpt-oss-20b-GGUF --ctx-size 0 --jinja -ub 2048 -b 2048 --n-cpu-moe 22`, and 32k context `... --ctx-size 32768 ... --n-cpu-moe 16`. No tok/s numbers are published for the 8GB case — [llama.cpp Discussion #15396](https://github.com/ggml-org/llama.cpp/discussions/15396); [aliteq](https://aliteq.com/gpt-oss-20b-8gb-12gb-gpu-moe-offload-2026) confirms the guide "doesn't publish a tokens-per-second figure for its 8GB example"
- Closest measured neighbour: an **RTX 3060 12GB** (Sept 2025) gave ~64 tok/s generation at 16k ctx with `-ncmoe 2`, ~56 tok/s at 32k with `-ncmoe 3` (near OOM), and 67 tok/s with selective tensor offload — [Discussion #15396](https://github.com/ggml-org/llama.cpp/discussions/15396)
- RTX 3060 pp for gpt-oss-20b MXFP4: pp2048 ≈ 2,230 tok/s, pp8192 ≈ 2,109, pp16384 ≈ 1,960 (per search snippet; context not fully verified) — [Discussion #15396](https://github.com/ggml-org/llama.cpp/discussions/15396)
- Model size: the gpt-oss-20b MXFP4 GGUF needs ~14.9GB at 8K ctx and ~15.5GB at 32K. Of its weights, 19.1B params are experts and ~1.8B are always-on, so most of the model must live in RAM on an 8GB card — [aliteq](https://aliteq.com/gpt-oss-20b-8gb-12gb-gpu-moe-offload-2026). The author explicitly did not benchmark this.

**gpt-oss-120b:**
- The official guide lists an 8GB recipe for 120b: `--ctx-size 32768 --jinja -ub 2048 -b 2048 --n-cpu-moe 35` — [Discussion #15396](https://github.com/ggml-org/llama.cpp/discussions/15396)
- Reported reference (RTX 3090 24GB + 64GB DDR4, `--n-cpu-moe 24`): ~50 t/s pp and ~15 t/s tg (aggregated via bookmark site) — [scuttle.klotz.me](https://scuttle.klotz.me/tags/gpt-oss+120b)

**GLM-4.7-Flash (30B-A3B MoE, early 2026):** I found no measured 8GB results. The pages I found (clore.ai docs, aiagentskit) give VRAM requirement claims only — [clore.ai](https://docs.clore.ai/guides/language-models/glm-47-flash)

### Inferences
- With 32GB RAM, the practical ceiling is a ~30–35B-total / ~3B-active MoE at Q4 (17–21GB of weights), which leaves ~10GB for the OS, IDE and agent harness. gpt-oss-120b (~60+GB MXFP4) is not feasible with 32GB.
- Tuning `--n-cpu-moe` so VRAM is nearly full is worth ~2.4x on generation (13→32 tok/s) compared with plain `--cpu-moe`, measured on the same 8GB card.
- The models have similar active-parameter counts, so gpt-oss-20b (3.6B active) on an 8GB card should land in a similar 20–35 tok/s generation band. That is an inference, not a measurement.

### Gaps
- No measured gpt-oss-20b tok/s on any 8GB card. No GLM-4.7-Flash or Devstral Small 8GB measurements found.
- No r/LocalLLaMA thread content retrieved directly (Reddit was not reachable via the search tool).
- No RTX 5060 / 5060 Ti 8GB MoE-offload data found.

## 2. Prompt processing (prefill) for long agent prompts: offload, -b/-ub, flash attention

### Takeaway
Prefill is the real bottleneck for agent harnesses on 8GB cards. With experts in system RAM, llama.cpp copies the CPU-resident expert weights over PCIe to the GPU for each big batch. Large `-ub` (2048–4096) is therefore critical: measured small-ubatch prefill on 8GB is only ~40–50 tok/s, while a well-configured 6GB laptop reached ~350–400 tok/s. A 20k-token agent prompt therefore takes roughly **1 minute at ~350 tok/s, or 7+ minutes at ~50 tok/s**.

### Cited Findings
- Mechanism: "If you have enough tokens to process together, llama.cpp will perform GPU offload prompt processing … copying all of the CPU-assigned weights over to the GPU to process the prompt tokens as a single batch." The default threshold is 32 tokens. PCIe bandwidth is the limit (e.g. 300GB of CPU weights over PCIe 4.0 x16 takes ≥10 s per batch) — [HF blog, Doctor-Shotgun, 2026-01-30](https://huggingface.co/blog/Doctor-Shotgun/llamacpp-moe-offload-guide)
- Recommended MoE hybrid flags: `-ngl 999 -ot "exps=CPU"` (or `--cpu-moe` / `--n-cpu-moe N`), `-b 4096 -ub 4096`, `-fa on`, `--no-mmap`. "The physical (micro) batch size … is the determinant of VRAM usage" — [HF blog](https://huggingface.co/blog/Doctor-Shotgun/llamacpp-moe-offload-guide)
- The official gpt-oss guide uses `-ub 2048 -b 2048` even for 8GB cards and recommends flash attention — [Discussion #15396](https://github.com/ggml-org/llama.cpp/discussions/15396)
- Measured contrast on 8GB: ubatch 64–256 configs gave **40–52 tok/s** prompt eval (Qwen3-Coder-30B-A3B, RTX 3060 Ti) — [dev.to](https://dev.to/upayanghosh/from-oom-to-262k-context-running-qwen3-coder-30b-locally-on-8gb-vram-1ej1). A 6GB laptop with all experts on CPU reached **350–400 tok/s** prefill (Qwen3.5-35B-A3B) — [Discussion #21112](https://github.com/ggml-org/llama.cpp/discussions/21112)
- Counterpoint: one user found smaller batches (b=128, ub=512) left room for more context than the defaults (b=4096, ub=1024) on a multi-GPU setup. The batch/VRAM trade-off is hardware-dependent — [Discussion #21112 (iridium87, 2026-05)](https://github.com/ggml-org/llama.cpp/discussions/21112)
- Dense model that fits fully on an 8GB RTX 3070 (llama.cpp CUDA 13.1, Q4_K_M, Apr 2026): Qwen3.5-9B prefill **1,932 tok/s**, GLM-4.6V-Flash (9B) **2,376 tok/s** at 4K. Nemotron 12B v2 with layers spilled to CPU at 32K: only **169 tok/s** prefill — [localllm.in](https://localllm.in/blog/best-local-llms-8gb-vram-2025)
- An explainer argues the PCIe round trip, not CPU compute, is the main cost of offloaded experts in decode — [dev.to/someoddcodeguy](https://dev.to/someoddcodeguy/understanding-moe-offloading-5co6) (via search snippet)

### Inferences
- For a 10k–30k-token agent loop on 8GB + MoE offload, use `-ub 2048` or higher and `-fa on`, and give up some `--n-cpu-moe` VRAM to make room for the larger compute buffer. Prefill rates of a few hundred tok/s are plausible. Dense 8–9B models that fit fully in VRAM prefill ~5x faster (~2k tok/s).
- Laptop PCIe links (often x8 on RTX 4060 Laptop) would halve weight-streaming bandwidth compared with desktop x16, which hurts offloaded prefill. This is inferred and not measured in the sources.
- KV-cache reuse in llama-server (`--cache-reuse`, prompt caching) matters a lot for agents because it avoids re-prefilling the stable prefix. It was mentioned in Discussion #21112 configs (`--cache-reuse 256`) — [Discussion #21112](https://github.com/ggml-org/llama.cpp/discussions/21112)

### Gaps
- I found no direct A/B of `-ub 512` vs `-ub 2048` vs `-ub 4096` prefill on an 8GB card with MoE offload, and no PCIe x8 vs x16 measurement.

## 3. How much context fits (32k/64k/128k, q8_0 KV) on 8GB alongside model layers

### Takeaway
With MoE offload, KV cache competes only with the experts you choose to keep on the GPU, so large contexts are achievable on 8GB. Measured examples: 32K at ~7.3GB used (Qwen3-Coder-30B, n-cpu-moe 40), 102K on a 6GB laptop (Qwen3.5-35B-A3B, all experts on CPU), and 262K with an experimental TurboQuant KV fork. For dense models, a 9B fits 32K fully in VRAM, but 12B+ dense spills and collapses to 2–7 tok/s.

### Cited Findings
- Qwen3-Coder-30B-A3B, 32K ctx, `--n-cpu-moe 40`: 7,265 MB VRAM; with `--cpu-moe`: 4,388 MB — [dev.to](https://dev.to/upayanghosh/from-oom-to-262k-context-running-qwen3-coder-30b-locally-on-8gb-vram-1ej1)
- Qwen3-Coder-30B-A3B, **262K ctx** with TurboQuant KV (`turbo4` K / `turbo3` V): 7,525 MB VRAM, 29 tok/s gen — [dev.to](https://dev.to/upayanghosh/from-oom-to-262k-context-running-qwen3-coder-30b-locally-on-8gb-vram-1ej1)
- Qwen3.5-35B-A3B, **102K ctx** on a 6GB RTX 2060 laptop with all experts on CPU: ~15 tok/s gen — [Discussion #21112](https://github.com/ggml-org/llama.cpp/discussions/21112)
- gpt-oss-20b official 8GB recipes: 32K with `--n-cpu-moe 16`, full 128K with `--n-cpu-moe 22` — [Discussion #15396](https://github.com/ggml-org/llama.cpp/discussions/15396)
- On RTX 3060 12GB, gpt-oss-20b at 32K with `-ncmoe 3` was "risky (OOM)" — [Discussion #15396](https://github.com/ggml-org/llama.cpp/discussions/15396)
- Dense models on RTX 3070 8GB at 32K (Q4_K_M, Apr 2026):

  | Model | Decode | Peak VRAM | GPU layers |
  |---|---|---|---|
  | Qwen3.5-9B | 54.9 tok/s | 6.96 GB | 33/33 |
  | GLM-4.6V-Flash | 17.4 tok/s | 7.16 GB | 37/41 (spill) |
  | Nemotron 12B v2 | 6.6 tok/s | 7.75 GB | 44/63 |
  | Gemma 3 12B | 4.3 tok/s | — | — |
  | Phi-4 14B | 1.8 tok/s | — | — |

  Source: [localllm.in](https://localllm.in/blog/best-local-llms-8gb-vram-2025)
- Qwen3.5-9B at 4K: 57.9 tok/s decode, 6.09 GB — [localllm.in](https://localllm.in/blog/best-local-llms-8gb-vram-2025)
- The community prefers q8_0 KV over q4_0 for quality — [Discussion #21112 summary](https://github.com/ggml-org/llama.cpp/discussions/21112)

### Inferences
- Qwen3-family MoE models (Qwen3-Coder-30B-A3B, Qwen3.5/3.6-35B-A3B; the 3.5/3.6 models use hybrid linear attention) have small KV footprints, so 64K–128K with q8_0 KV is realistic on 8GB when most experts stay on CPU. The trade-off is lower generation speed (≈15 tok/s at 100K vs ≈30 tok/s at 32K).
- Dense Qwen3 14B at Q4 will not fit with long context on 8GB. Generation then drops into single digits (compare Phi-4 14B at 1.8 tok/s at 32K).

### Gaps
- No measured table of max ctx vs `--n-cpu-moe` vs KV type (f16/q8_0/q4_0) for an 8GB card.
- TurboQuant KV types are a non-mainline fork. Mainline status was not verified.

## 4. Laptop vs desktop (RTX 4060 Laptop TGP; HX 370 LPDDR5X vs 9950X DDR5)

### Takeaway
Direct laptop measurements on RTX 4060 Laptop with MoE offload were not found. The only laptop data point is a 6GB RTX 2060 laptop with 32GB RAM running Qwen3.5-35B-A3B (15 tok/s gen, 350–400 pp at 102K). On HX 370-class laptops, decode with offloaded experts depends on system RAM bandwidth, which is quoted at ~83–90 GB/s for SODIMM DDR5.

### Cited Findings
- RTX 4060 Laptop: 3072 shaders, 8GB GDDR6, 128-bit bus — [Notebookcheck](https://www.notebookcheck.net/NVIDIA-GeForce-RTX-4060-Laptop-GPU-Benchmarks-and-Specs.675692.0.html)
- The RTX 4060 Laptop TGP varies by chassis (up to 115W), and generation in thin-and-lights is "noticeably slower" and throttles under sustained load. This is a qualitative claim from a calculator site — [willitrunai (es)](https://willitrunai.com/es/can-run/qwen-2.5-14b-on-rtx-4060-8gb)
- RTX 2060 6GB laptop (i7-9750H, 32GB RAM): Qwen3.5-35B-A3B Q4_K_M, all experts on CPU, 350–400 tok/s prefill, 15 tok/s gen at 102K ctx (2026-03-29) — [Discussion #21112](https://github.com/ggml-org/llama.cpp/discussions/21112)
- Framework community on Ryzen AI 300 (June 2025): output-token speed expected to be bandwidth-bound like the older 7640U (~83–90 GB/s with SODIMM DDR5), while prompt processing should improve — [Framework community](https://community.frame.work/t/fw13-ai-370-performance/70063)
- Desktop reference with DDR5: RTX 3090 + 128GB DDR5-6400 + Core Ultra 265K, Nemotron-3-Super-120B-A12B Q3: ~16 tok/s; advice was to use all cores, not just P-cores, for expert compute (2026-03-28) — [Discussion #21112](https://github.com/ggml-org/llama.cpp/discussions/21112)

### Inferences
- Decode speed for CPU-resident experts scales roughly with RAM bandwidth. Dual-channel desktop DDR5-6000 (~96 GB/s theoretical) and HX 370 LPDDR5X-7500 (~120 GB/s theoretical) are in the same class, so desktop vs laptop decode should differ less than GPU TGP would suggest. These are theoretical figures, not from cited sources.
- Laptop disadvantages are more likely in prefill (PCIe lanes, GPU TGP/clock limits) and in sustained thermals.

### Gaps
- No measured RTX 4060 Laptop + HX 370 or 9950X + 8GB-GPU MoE benchmarks found. No TGP-sweep LLM measurements found.

## 5. Can the Ryzen AI 9 HX 370 Radeon 890M iGPU / XDNA NPU help? (brief)

### Takeaway
They help only marginally. The 890M via Vulkan is roughly a 13 tok/s-on-8B-dense device, far below a discrete RTX 4060. The NPU (Lemonade hybrid) works mainly on Windows. On Linux in late 2025 / early 2026, NPU support was experimental. Neither meaningfully helps when an 8GB NVIDIA dGPU is present.

### Cited Findings
- LocalScore for HX 370 / 890M:

  | Model | pp | tg | TTFT |
  |---|---|---|---|
  | Llama 3.2 1B Q4_K_M | 551 tok/s | 67.0 tok/s | — |
  | Llama 3.1 8B Q4_K_M | 99 tok/s | 12.9 tok/s | 13.6 s |
  | Qwen2.5 14B Q4_K_M | 51 tok/s | 7.1 tok/s | 26.3 s |

  Source: [localscore.ai](https://www.localscore.ai/accelerator/721)
- HX 370 with 96GB RAM, Vulkan (RADV, Debian 13), GTT raised to 40GB: Qwen3 30B Q8_0 >23 tok/s peak and ~18 tok/s sustained. Qwen3-Next-80B Q8_0 ~10.9 tok/s at 17.5K ctx (2026-02-06) — [llama.cpp issue #19396](https://github.com/ggml-org/llama.cpp/issues/19396)
- ROCm 7.10 added HX 370 support, but NPU+iGPU hybrid was "possible with lemonade only on Windows currently". Linux NPU support was not practical (Dec 2025 – Jan 2026) — [Framework community](https://community.frame.work/t/ai-workloads-finally-supported-on-the-framework-13-ryzen-ai-9-hx-370/78810)
- Lemonade can split prefill onto the XDNA2 NPU and decode onto the GPU. Its hybrid mode on 8B models gives ~38 tok/s (Llama-3.1-8B-Hybrid). It reaches full performance only when both CPU/NPU and GPU are AMD — [runaihome](https://runaihome.com/blog/amd-lemonade-local-llm-server-npu-gpu-guide-2026/); [Framework FW16 thread](https://community.frame.work/t/fw16-newer-radeon-gpu-module-needed-for-actual-npu-gpu-hybrid-work-via-lemonade/83682)

### Inferences
- On an HX 370 + RTX 4060 Laptop machine, the NVIDIA dGPU plus CPU experts (llama.cpp CUDA) is the path to use. The 890M could at most host a small separate model (e.g. an autocomplete/draft model) via Vulkan.

### Gaps
- No measured Linux NPU (Lemonade/FastFlowLM) numbers for coding models found.

## 6. Practical recommended configurations from users

### Takeaway
The consistent recipe: llama.cpp `llama-server`, `-ngl 99/999`, `--n-cpu-moe N` lowered until VRAM is nearly full, `-fa on`, q8_0 KV, `-b/-ub 2048` (or larger) for long-prompt prefill, `--no-mmap`, all CPU cores, `--jinja` for tool calling.

### Cited Findings
- Qwen3-Coder-30B-A3B on 8GB / 32GB: `--n-cpu-moe 40 --ctx-size 32768` → ~32 tok/s gen (RTX 3060 Ti) — [dev.to](https://dev.to/upayanghosh/from-oom-to-262k-context-running-qwen3-coder-30b-locally-on-8gb-vram-1ej1)
- gpt-oss-20b on 8GB:
  ```
  llama-server -hf ggml-org/gpt-oss-20b-GGUF --ctx-size 32768 --jinja -ub 2048 -b 2048 --n-cpu-moe 16
  ```
  Use `--ctx-size 0 ... --n-cpu-moe 22` for full context. Sampling: temp 1.0, top-p 1.0, no repetition penalty — [Discussion #15396](https://github.com/ggml-org/llama.cpp/discussions/15396)
- Generic MoE hybrid: `-ngl 999 -ot "exps=CPU" -b 4096 -ub 4096 -fa on --no-mmap` — [HF blog Doctor-Shotgun](https://huggingface.co/blog/Doctor-Shotgun/llamacpp-moe-offload-guide)
- Low-VRAM laptop: `-ngl 99 --n-cpu-moe 99`, vision mmproj on CPU to free ~600MB — [Discussion #21112](https://github.com/ggml-org/llama.cpp/discussions/21112)
- Use all cores (not P-cores only) for CPU expert compute. Prefer q8_0 KV over q4_0. Use `--cache-reuse` for repeated prefixes — [Discussion #21112](https://github.com/ggml-org/llama.cpp/discussions/21112)
- If the model fits fully in VRAM, `--n-cpu-moe` only slows inference. The big speedup applies only when VRAM would otherwise be overcommitted — [aliteq explainer](https://aliteq.com/n-cpu-moe-llama-cpp-what-it-actually-does) (via search snippet)
- Dense alternative: Qwen3.5-9B Q4_K_M runs fully in 8GB at 32K: 55 tok/s gen, ~1.9k tok/s prefill — [localllm.in](https://localllm.in/blog/best-local-llms-8gb-vram-2025)

### Inferences
- For agent use (long prompts), there are two realistic choices on 8GB + 32GB:
  - **A:** a dense ~9B that fits fully in VRAM. Fast prefill (~2k tok/s), ~55 tok/s gen, weaker model.
  - **B:** a 30–35B-A3B MoE with expert offload. Stronger model, ~15–32 tok/s gen, prefill of tens to a few hundred tok/s depending on ubatch.

### Gaps
- No user-shared, measured "best config" specific to RTX 4060 Laptop + HX 370 or desktop 9950X + 8GB card was found.
