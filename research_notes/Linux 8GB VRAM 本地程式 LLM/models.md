# Open-weight coding / agentic-coding LLMs for 8GB VRAM + ~30GB RAM (as of 2026-10-07)

Scope note: hardware budget = 8GB VRAM + ~30GB RAM ≈ 38GB total. After OS/desktop (~4-6GB) and KV cache, a GGUF file of roughly ≤ 28-30GB is the practical ceiling for MoE-with-CPU-expert-offload; dense models must fit almost entirely in 8GB to be fast (dense models spilling to CPU become very slow because every weight is read per token). Several sources below are SEO/aggregator blogs; primary sources (Hugging Face model cards, GitHub) are preferred and conflicts are flagged.

## 1. What are the latest (2026) coding/agentic open models, and which are relevant to this hardware?

### Takeaway
The 2026 landscape is dominated by Qwen's hybrid (Gated DeltaNet + MoE) family: Qwen3.5 (Feb 2026) → Qwen3.6-35B-A3B (Apr 16, 2026) and Qwen3.6-27B (Apr 22) → Qwen3.8-27B (Aug 14, 2026; dense only, no 3.8 small MoE confirmed). For 8GB VRAM + 30GB RAM, the strongest practical agentic-coding model is **Qwen3.6-35B-A3B** (SWE-bench Verified 73.4) with experts offloaded to CPU; alternatives are Gemma 4 26B-A4B, GLM-4.7-Flash (30B-A3B), NVIDIA Nemotron 3.5 Lightning 30B-A3B (Aug 2026), and gpt-oss-20b. Qwen3-Coder-30B-A3B (Jul 2025) and Qwen3.5-35B-A3B are superseded.

### Cited Findings

**Qwen family timeline (primary: QwenLM GitHub)**
- Qwen3.5-397B-A17B, 122B-A10B, 35B-A3B, 27B released Feb 24, 2026; Qwen3.5-9B/4B/2B/0.8B Mar 2, 2026; Qwen3.6-35B-A3B Apr 16, 2026; Qwen3.6-27B Apr 22, 2026; Qwen3.8-2.4T-A95B Aug 12, 2026; Qwen3.8-27B Aug 14, 2026 — [QwenLM/Qwen3.8 GitHub](https://github.com/QwenLM/Qwen3.8)
- Aggregator dates differ slightly (e.g., lists Qwen3.5 small models as Feb 16, 2026, and wrongly dates Qwen3-Coder-30B-A3B to "May 2026" — it actually dates from 2025); treat [Codersera guide](https://codersera.com/blog/qwen-3-5-complete-guide-2026/) as lower reliability vs [QwenLM GitHub](https://github.com/QwenLM/Qwen3.8)
- The same aggregator states "no 3.8 Coder variant has shipped" and that Qwen3.7-Max (May 20, 2026) is API-only/closed — [Codersera](https://codersera.com/blog/qwen-3-5-complete-guide-2026/)
- Qwen3.8 open-weight releases are only the 27B dense and the 2.4T-A95B flagship (custom license); no Qwen3.8 35B-A3B / 9B found — [QwenLM GitHub](https://github.com/QwenLM/Qwen3.8); [llm-stats](https://llm-stats.com/blog/research/qwen3-8-max-open-weights)
- A llama.cpp issue dated Oct 7, 2026 references a "qwen4exp (Qwen3.8-Flash-Next)" GGUF, but it is a custom-quantized variant with no official HF repo or parameter count given — unverified, do not treat as an official release — [llama.cpp #30078](https://github.com/ggml-org/llama.cpp/issues/30078)

**Qwen3.6-35B-A3B (Apr 16, 2026) — primary candidate**
- 35B total / 3B active; 40 layers laid out as 10 × (3 × (Gated DeltaNet → MoE) → 1 × (Gated Attention → MoE)); 256 experts, 8 routed + 1 shared; vision encoder; 262,144 native context (extensible to ~1.01M); Apache 2.0 — [HF Qwen/Qwen3.6-35B-A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)
- Benchmarks vs Qwen3.5-35B-A3B: SWE-bench Verified 73.4 vs 70.0; SWE-bench Pro 49.5 vs 44.6; Terminal-Bench 2.0 51.5 vs 40.5; LiveCodeBench v6 80.4 vs 74.6; QwenClawBench 52.6 vs 47.7 — [HF Qwen/Qwen3.6-35B-A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)
- NVIDIA's Nemotron 3.5 card reports Qwen3.6-35B at SWE-bench Verified 70.12 and Terminal-Bench 2.1 44.38 in its own harness (lower than Qwen's self-reported numbers — harness-dependent) — [HF nvidia Nemotron-3.5-Lightning](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16)
- Thinking mode on by default; non-thinking/instruct available; "preserve thinking" across turns feature; tool use via `--tool-call-parser qwen3_coder` (SGLang) / `--enable-auto-tool-choice` (vLLM) — [HF Qwen/Qwen3.6-35B-A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)

**Qwen3.6-27B / Qwen3.8-27B (dense, too big for 8GB)**
- Qwen3.6-27B reportedly beats Qwen3.5-397B-A17B: SWE-bench Verified 77.2 vs 76.2, Terminal-Bench 2.0 59.3 vs 52.5, SWE-bench Pro 53.5 vs 50.9 — [Codersera (aggregator)](https://codersera.com/blog/qwen-3-5-complete-guide-2026/)
- Qwen3.8-27B (Aug 14, 2026): 64 layers hybrid Gated DeltaNet/Gated Attention, vision, 262K context; thinking by default with `reasoning_effort` xhigh/medium/low; vs Qwen3.6-27B: Terminal-Bench 2.1 73.0 vs 63.4; SWE-bench Pro 61.7 vs 53.5; DeepSWE 1.1 42.2 vs 13.3; LiveCodeBench v6 90.3 vs 83.9 — [HF Qwen/Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B)
- Qwen3.8-27B Q4_K_M ≈ 16.5-19.5GB weights + ~1.5GB runtime; positioned for 24GB+ GPUs — [dev.to weight classes Sep 2026](https://dev.to/klukyanov/the-local-llm-weight-classes-september-2026-what-actually-fits-on-your-machine-128d)
- Qwen3.6-27B memory: 3-bit 15GB, 4-bit 18GB (RAM+VRAM) — [Unsloth Qwen3.6 docs](https://unsloth.ai/docs/models/qwen3.6)

**Qwen3.5 small dense (Mar 2, 2026)**
- Qwen3.5-9B: LiveCodeBench v6 65.6, BFCL-V4 66.1, TAU2-Bench 79.1; Qwen3.5-4B: LCB 55.8, BFCL-V4 50.3, TAU2 79.9; tool parser qwen3_coder; 262K context — [HF Qwen/Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B)
- Qwen3.5-9B claimed to beat gpt-oss-20b on GPQA Diamond (81.7 vs 80.1) — [HF Qwen/Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B); popular press: [VentureBeat](https://venturebeat.com/technology/alibabas-small-open-source-qwen3-5-9b-beats-openais-gpt-oss-120b-and-can-run)
- Thinking default conflict: HF card says Qwen3.5 thinks by default — [HF Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B); Unsloth says small models (0.8B-9B) have reasoning "disabled by default" — [Unsloth Qwen3.5](https://unsloth.ai/docs/models/qwen3.5)
- No SWE-bench Verified score found for Qwen3.5-9B on its card (gap).

**Qwen3-Coder-Next 80B-A3B (2026)**
- Described as "most realistic self-hosted coding model" for 24-64GB machines — [dev.to Sep 2026](https://dev.to/klukyanov/the-local-llm-weight-classes-september-2026-what-actually-fits-on-your-machine-128d)
- Unsloth GGUF sizes: UD-TQ1_0 18.9GB, UD-IQ1_M 21.7GB, UD-IQ2_XXS 23.3GB, UD-IQ2_M 25GB, UD-Q2_K_XL 26.8GB, UD-IQ3_XXS 28.5GB, UD-Q4_K_XL 49.6GB, MXFP4_MOE 48GB — [HF unsloth/Qwen3-Coder-Next-GGUF](https://huggingface.co/unsloth/Qwen3-Coder-Next-GGUF/tree/main)
- llama.cpp crash reported with Qwen3-Coder-Next at ~80K context with multiple tool calls ("unexpected empty grammar stack") — [search summary of llama.cpp reports](https://buttondown.com/weekly-project-news/archive/weekly-github-report-for-llamacpp-march-16-2026/)

**Gemma 4 (Google)**
- Family: E2B (2.3B eff., 128K), E4B (4.5B eff., 128K), 26B-A4B MoE (25.2B total / 3.8B active, 256K), 31B dense (256K); Apache 2.0 — [HF google/gemma-4-26B-A4B-it](https://huggingface.co/google/gemma-4-26B-A4B-it)
- LiveCodeBench v6: 31B 80.0, 26B-A4B 77.1, E4B 52.0, E2B 44.0; Codeforces ELO 2150 / 1718 / 940 / 633; Tau2 avg 76.9 / 68.2 / 42.2 / 24.5 — [HF gemma-4-26B-A4B-it](https://huggingface.co/google/gemma-4-26B-A4B-it)
- Release date conflict: the HF card cites a July 2026 tech report (arXiv 2607.02770) — [HF](https://huggingface.co/google/gemma-4-26B-A4B-it); but third-party usage articles exist from April 10, 2026 — [Codex CLI + Gemma 4 blog](https://codex.danielvaughan.com/2026/04/10/gemma-4-local-model-codex-cli). Model likely released ~April 2026, tech report later.
- Thinking enabled via `<|think|>` token in system prompt; native tool tokens `<|tool_call>` / `<|tool_response>`; sampling temp 1.0, top-p 0.95, top-k 64 — [HF](https://huggingface.co/google/gemma-4-26B-A4B-it); [Verdent review](https://verdent.ai/guides/gemma-4-coding-agent-review)
- Community SWE-bench Lite run of Gemma 4 26B on DGX Spark reported 38% — [ai-muninn](https://ai-muninn.com/en/blog/swe-bench-lite-gemma4-26b-38-percent) (single-blog result; not an official number)
- Q4_K_M ~16-18GB memory for 26B MoE — [Verdent](https://verdent.ai/guides/gemma-4-coding-agent-review)

**GLM-4.7-Flash (Z.ai, Jan 2026)**
- 30B-A3B MoE (31B total), MIT license; SWE-bench Verified 59.2 vs Qwen3-30B-A3B-Thinking-2507 22.0 vs gpt-oss-20b 34.0; τ²-Bench 79.5 / 49.0 / 47.7; LiveCodeBench v6 64.0 / 66.0 / 61.0; BrowseComp 42.8 / 2.29 / 28.3; tool parser `glm47`; "Preserved Thinking" for agentic tasks; code/terminal sampling temp 0.7 top-p 1.0 — [HF zai-org/GLM-4.7-Flash](https://huggingface.co/zai-org/GLM-4.7-Flash)
- Released January 20, 2026 — [NYU Shanghai RITS](https://rits.shanghai.nyu.edu/ai/glm-4-7-flash-z-ais-efficient-30b-moe-model-for-coding-and-agents/) (HF fetch returned Aug 8, 2025, which is the GLM-4.5 arXiv date, not the Flash release)
- Successor GLM-5.3-Flash (Aug 26, 2026, MIT) is 320B total / 18B active — far beyond this hardware — [Codersera GLM-5.3-Flash](https://codersera.com/blog/glm-5-3-flash-complete-guide-2026/); [CometAPI specs](https://www.cometapi.com/models/zhipuai/glm-5-3-flash/)

**NVIDIA Nemotron 3.5 Lightning 30B-A3B (Aug 11, 2026)**
- Mamba-2 + MoE + Attention hybrid (LatentMoE, MTP layers), 30B / 3B active, up to 1M context, OpenMDW-1.1 license; reasoning on/off via `enable_thinking`; vLLM tool parser `qwen3_coder`; temp 1.0 top-p 0.95 — [HF nvidia BF16](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16)
- vs Qwen3.6-35B (NVIDIA's eval): SWE-bench Verified 51.56 vs 70.12; Terminal-Bench 2.1 24.58 vs 44.38; IFBench 71.88 vs 63.71; GPQA 75.44 vs 83.40 — [HF nvidia BF16](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16)
- NVFP4 variant: SWE-bench Verified 52.80 — [search summary of HF NVFP4 card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4); Unsloth GGUF exists — [HF unsloth GGUF](https://huggingface.co/unsloth/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF)
- 56,000+ downloads in three days — [local-ai-zone Sep 2026](https://local-ai-zone.github.io/blog/September_2026_AI_Model_Updates.html)

**gpt-oss-20b (OpenAI, Aug 2025)**
- 20.9B total / ~3.6B active MoE; MoE weights in MXFP4, rest BF16; runs in ~16GB; Harmony prompt format; SWE-bench Verified 60.7%, Aider Polyglot 34.2% (per NVIDIA's catalog page) — [NVIDIA NIM docs](https://docs.api.nvidia.com/nim/reference/openai-gpt-oss-20b)
- Conflict: Z.ai's GLM-4.7-Flash table lists gpt-oss-20b SWE-bench Verified at 34.0 (different harness / reasoning effort) — [HF GLM-4.7-Flash](https://huggingface.co/zai-org/GLM-4.7-Flash)
- llama.vscode README: "gpt-oss 20B is the best choice" for its Llama Agent feature — [ggml-org/llama.vscode](https://github.com/ggml-org/llama.vscode)

**Devstral Small 2 (Mistral, 24B dense, Dec 2025 — "2512")**
- 24B, 256K context, Apache 2.0, vision input; SWE-bench Verified 68.0, SWE-bench Multilingual 55.7, Terminal-Bench 2 22.5; recommended harness Mistral Vibe CLI, also Cline, Kilo Code, Claude Code, OpenHands; temp 0.15 — [HF mistralai/Devstral-Small-2-24B-Instruct-2512](https://huggingface.co/mistralai/Devstral-Small-2-24B-Instruct-2512); [Mistral blog](https://mistral.ai/news/devstral-2-vibe-cli/)
- Q4_K_M ≈ 12.8GB VRAM; Q8_0 25.1GB — [canirun.ai](https://www.canirun.ai/model/devstral-small-2-24b)

**Other 2026 releases (not suitable for this hardware)**
- DeepSeek V4-Flash-0731 (284B/13B active), DeepSeek V4.1-Flash (Sep 10, 2026), Kimi K3, MiMo-V2.6 (1.02T/42B), Hy4 Preview (770B/49B), Cohere Command A+ — all far too large — [local-ai-zone Sep 2026](https://local-ai-zone.github.io/blog/September_2026_AI_Model_Updates.html)
- Bonsai 2 27B (Prism ML, Sep 17, 2026): ternary 1.76 bits/weight, 5.9GB file, claims 98.2% of FP16 benchmark "intelligence" — [local-ai-zone](https://local-ai-zone.github.io/blog/September_2026_AI_Model_Updates.html) (vendor claim, unverified; could fit fully in 8GB VRAM — worth testing)
- "Nemotron Cascade 2 30B A3B" mentioned as a local coding option — [search snippet, KDnuggets/vdf.ai lists](https://www.kdnuggets.com/top-7-coding-models-you-can-run-locally-in-2026) (no primary card fetched)

### Inferences
- Best agentic pick for this rig: Qwen3.6-35B-A3B. It has the top SWE-bench Verified and Terminal-Bench scores among models in the ~3B-active class, plus a hybrid architecture where only 10 of 40 layers carry a KV cache, so long context costs little VRAM.
- GLM-4.7-Flash is the second-tier alternative, with strong τ²-bench (tool use) scores. gpt-oss-20b is the smallest and fastest MoE but is clearly weaker at SWE tasks. Nemotron 3.5 Lightning favors speed and instruction-following over coding. Gemma 4 26B-A4B is good for chat and competitive coding but has less agentic SWE evidence.
- Qwen3-Coder-30B-A3B (2025), Qwen3-30B-A3B-2507, Qwen3.5-35B-A3B, Devstral Small 1.x and Qwen2.5-Coder-7B-Instruct (as an agent) are superseded for agentic use.

### Gaps
- No primary SWE-bench/Terminal-Bench numbers found for Qwen3.5-9B, Gemma 4 26B-A4B (official), Granite 4.x, Seed-OSS-36B, Phi-4/5, LFM2/3 or DeepSeek small distills in 2026. These were not researched in depth because of budget, and most are either too big (Seed-OSS 36B dense) or weak at agentic coding.
- No current (Oct 2026) Aider polyglot or BFCL leaderboard snapshot was fetched.
- Could not confirm whether any official "Qwen3.8 small MoE" or "Qwen4" open checkpoint exists. Only the unverified "Qwen3.8-Flash-Next" llama.cpp issue was found.

## 2. Which fit in 8GB VRAM fully, and which MoE models fit 8GB VRAM + 30GB RAM with expert offload?

### Takeaway
Fully in 8GB VRAM at Q4 with usable context: Qwen3.5-9B (~6.5GB at 4-bit), Qwen3.5-4B, Gemma 4 E4B (~6GB), plus small FIM models. MoE with CPU expert offload (llama.cpp `--n-cpu-moe` / `--cpu-moe` / `-ot`): Qwen3.6-35B-A3B UD-Q4_K_XL (22.4GB) or UD-Q3_K_XL (16.8GB), GLM-4.7-Flash Q4 (~18GB), Gemma 4 26B-A4B Q4 (~16-18GB), Nemotron 3.5 Lightning Q4, and gpt-oss-20b MXFP4 (~12-13GB) all fit within 38GB. Qwen3-Coder-Next 80B-A3B only fits at ≤UD-Q2_K_XL (26.8GB), with tight headroom. Dense 24-27B models (Devstral Small 2, Qwen3.6/3.8-27B) do not fit well and would run slowly.

### Cited Findings
- Qwen3.6-35B-A3B Unsloth GGUF sizes: UD-IQ2_M 11.5GB, UD-Q2_K_XL 12.3GB, UD-IQ3_XXS 13.2GB, UD-Q3_K_XL 16.8GB, UD-IQ4_XS 17.7GB, UD-IQ4_NL 18GB, UD-IQ4_NL_XL 19.5GB, UD-Q4_K_S 20.9GB, MXFP4_MOE 21.7GB, UD-Q4_K_M 22.1GB, UD-Q4_K_XL 22.4GB, UD-Q5_K_XL 26.6GB, UD-Q6_K 29.3GB, UD-Q6_K_XL 31.8GB, Q8_0 36.9GB; mmproj-F16 899MB — [HF unsloth/Qwen3.6-35B-A3B-GGUF](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF/tree/main)
- Unsloth memory guidance for 35B-A3B (RAM+VRAM): 3-bit 17GB, 4-bit 23GB, 6-bit 30GB, 8-bit 38GB; MTP variants need ~1GB extra — [Unsloth Qwen3.6](https://unsloth.ai/docs/models/qwen3.6)
- Qwen3.5-9B: 4-bit 6.5GB, 3-bit 5.5GB; Qwen3.5-27B: 4-bit 17GB — [Unsloth Qwen3.5](https://unsloth.ai/docs/models/qwen3.5)
- Measured on 8GB GPU + 64GB RAM (Core Ultra 7 265HX): Qwen3.6-35B-A3B UD-Q6_K_XL, CPU-offloaded MoE experts, 262K context with Q8_0 KV cache, ~875-935 tok/s prefill, ~35-38 tok/s generation; speculative decoding was rejected after testing; author warns 32GB systems face "meaningful bandwidth constraints" and the setup "assumes plenty of system RAM" — [numsu/Qwen3.6-A3B-8GB-llama.cpp](https://github.com/numsu/Qwen3.6-A3B-8GB-llama.cpp)
- Same repo carries an upstream-derived "hybrid checkpoint fix". Without it, edits to a long agent conversation could make llama.cpp reject checkpoints and re-process much of the prompt from scratch, because of the recurrent (DeltaNet) state — [numsu repo](https://github.com/numsu/Qwen3.6-A3B-8GB-llama.cpp)
- An RTX 4060 Laptop (8GB) + 32GB RAM report claims 33-34 tok/s decode for Qwen3.6-35B-A3B Q4_K_M via a patched ik_llama.cpp. However, the flags are undisclosed ("pending patent filings") and it is shipped as a binary, so credibility is low. The same report claims Gemma 4 26B-A4B at 40+ tok/s on the same hardware — [HF discussion #58](https://huggingface.co/Qwen/Qwen3.6-35B-A3B/discussions/58)
- `--n-cpu-moe 36` on 8GB VRAM reported ~134 tok/s prompt processing for Qwen3.6-35B-A3B; that source's recommendation of 64-96GB RAM is for higher quants — [search summary citing willitrunai/apxml](https://willitrunai.com/blog/qwen-3-6-vram-requirements)
- Without proper MoE offload, an RTX 4060 8GB is estimated at only ~9 tok/s on Qwen3.6-35B-A3B — [insiderllm](https://insiderllm.com/guides/best-way-run-qwen-3-6-35b-moe-locally/)
- Gemma 4 E4B ~6GB quantized, growing to ~12.5GB at full 128K context. Qwen3 14B (~9GB) is listed for 12-16GB VRAM — [dev.to weight classes](https://dev.to/klukyanov/the-local-llm-weight-classes-september-2026-what-actually-fits-on-your-machine-128d)
- Gemma 4 26B-A4B Q4_K_M ~16-18GB — [Verdent](https://verdent.ai/guides/gemma-4-coding-agent-review)
- gpt-oss-20b runs in ~16GB, with MoE weights natively MXFP4 — [NVIDIA NIM docs](https://docs.api.nvidia.com/nim/reference/openai-gpt-oss-20b)
- Devstral Small 2 Q4_K_M needs 12.8GB VRAM, so it will not fit fully in 8GB — [canirun.ai](https://www.canirun.ai/model/devstral-small-2-24b)
- Qwen3-Coder-Next Q4 is ~46-50GB, so it exceeds budget; UD-Q2_K_XL is 26.8GB and UD-IQ2_M is 25GB — [HF unsloth/Qwen3-Coder-Next-GGUF](https://huggingface.co/unsloth/Qwen3-Coder-Next-GGUF/tree/main)

### Inferences
- With 30GB RAM (not 64GB), use Qwen3.6-35B-A3B **UD-Q4_K_XL (22.4GB)** or **UD-Q4_K_S/IQ4_XS (~18-21GB)** to leave RAM for the OS, IDE, the FIM model, and the browser. UD-Q6_K_XL (31.8GB), which the 64GB reference setup uses, is too tight here.
- Expected decode speed with 30GB DDR5 is probably ~20-35 tok/s, extrapolating from the 64GB data point. Generation is bound by RAM bandwidth, so dual-channel DDR5 vs DDR4 matters more than capacity. This is unverified for this exact rig.
- Qwen3-Coder-Next at UD-Q2_K_XL would technically fit, but it leaves almost no headroom and heavy 2-bit quantization of an 80B model is risky. Prefer Qwen3.6-35B-A3B at Q4.
- Dense 27B models (Qwen3.8-27B is the best open small model by benchmarks) need ~17GB at Q4. With only 8GB on GPU they would run at low single-digit tok/s, which is impractical for agent loops. Not recommended on this rig.

### Gaps
- No verified benchmark found for exactly 8GB VRAM + 32GB RAM with GLM-4.7-Flash, Nemotron 3.5 Lightning, or gpt-oss-20b (tok/s).
- GGUF file sizes for GLM-4.7-Flash, Gemma 4 26B-A4B, and Nemotron 3.5 Lightning were not fetched directly from the HF file listings. The sizes above are approximate secondary figures.

## 3. Benchmark scores (SWE-bench Verified, LiveCodeBench, Aider polyglot, Terminal-Bench, BFCL)

### Takeaway
Among models runnable on this rig, by vendor-reported numbers: SWE-bench Verified — Qwen3.6-35B-A3B 73.4 > Devstral Small 2 68.0 (does not fit VRAM) > gpt-oss-20b 60.7 (OpenAI/NVIDIA; Z.ai measured 34.0) > GLM-4.7-Flash 59.2 > Nemotron 3.5 Lightning 51.6. Terminal-Bench: Qwen3.6-35B-A3B 51.5 (TB2.0) leads by a wide margin. LiveCodeBench v6: Qwen3.6-35B-A3B 80.4, Gemma 4 26B-A4B 77.1, Qwen3.5-9B 65.6, GLM-4.7-Flash 64.0.

### Cited Findings
| Model | SWE-bench Verified | Terminal-Bench | LiveCodeBench v6 | Tool/agent bench | Source |
|---|---|---|---|---|---|
| Qwen3.6-35B-A3B | 73.4 (Qwen) / 70.12 (NVIDIA eval) | TB2.0 51.5 / TB2.1 44.38 (NVIDIA) | 80.4 | SWE-bench Pro 49.5 | [Qwen HF](https://huggingface.co/Qwen/Qwen3.6-35B-A3B), [NVIDIA HF](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16) |
| Qwen3.5-35B-A3B (superseded) | 70.0 | TB2.0 40.5 | 74.6 | SWE-Pro 44.6 | [Qwen HF](https://huggingface.co/Qwen/Qwen3.6-35B-A3B) |
| Qwen3.5-9B | n/a | n/a | 65.6 | BFCL-V4 66.1, TAU2 79.1 | [Qwen HF](https://huggingface.co/Qwen/Qwen3.5-9B) |
| Qwen3.5-4B | n/a | n/a | 55.8 | BFCL-V4 50.3, TAU2 79.9 | [Qwen HF](https://huggingface.co/Qwen/Qwen3.5-9B) |
| Gemma 4 26B-A4B | n/a official (community SWE-bench Lite 38%) | n/a | 77.1 | Tau2 68.2 | [Google HF](https://huggingface.co/google/gemma-4-26B-A4B-it), [ai-muninn](https://ai-muninn.com/en/blog/swe-bench-lite-gemma4-26b-38-percent) |
| Gemma 4 E4B | n/a | n/a | 52.0 | Tau2 42.2 | [Google HF](https://huggingface.co/google/gemma-4-26B-A4B-it) |
| GLM-4.7-Flash | 59.2 | n/a | 64.0 | τ² 79.5, BrowseComp 42.8 | [Z.ai HF](https://huggingface.co/zai-org/GLM-4.7-Flash) |
| gpt-oss-20b | 60.7 (NVIDIA catalog) / 34.0 (Z.ai table) | n/a | 61.0 (Z.ai table) | τ² 47.7 (Z.ai); Aider Polyglot 34.2 | [NVIDIA](https://docs.api.nvidia.com/nim/reference/openai-gpt-oss-20b), [Z.ai HF](https://huggingface.co/zai-org/GLM-4.7-Flash) |
| Nemotron 3.5 Lightning 30B-A3B | 51.56 (BF16), 52.80 (NVFP4) | TB2.1 24.58 | n/a | IFBench 71.88 | [NVIDIA HF](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16) |
| Devstral Small 2 24B (dense) | 68.0 | TB2 22.5 | n/a | SWE-Multilingual 55.7 | [Mistral HF](https://huggingface.co/mistralai/Devstral-Small-2-24B-Instruct-2512) |
| Qwen3-30B-A3B-Thinking-2507 (superseded) | 22.0 | n/a | 66.0 | τ² 49.0 | [Z.ai HF](https://huggingface.co/zai-org/GLM-4.7-Flash) |
| Qwen3.8-27B (dense; too big) | n/a (SWE-Pro 61.7) | TB2.1 73.0 | 90.3 | DeepSWE 42.2 | [Qwen HF](https://huggingface.co/Qwen/Qwen3.8-27B) |

### Inferences
- Vendor-reported scores differ substantially by harness, as the gpt-oss-20b 60.7 vs 34.0 and Qwen3.6 73.4 vs 70.1 gaps show. Rank models within the same table where possible. On NVIDIA's third-party table, Qwen3.6-35B-A3B leads Nemotron 3.5 Lightning by ~19 points on SWE-bench Verified.
- Terminal-Bench results are the best proxy for CLI-agent harnesses (OpenCode, Claude Code-style), and Qwen3.6-35B-A3B leads its class there.

### Gaps
- No up-to-date Aider polyglot leaderboard or BFCL v4 leaderboard numbers were fetched for 2026 models. Aider and BFCL coverage is thin (only gpt-oss-20b Aider and Qwen3.5-9B/4B BFCL).

## 4. Quantization recommendations (Unsloth Dynamic, MXFP4, imatrix, EXL3, AWQ; Q3/Q4 loss)

### Takeaway
For llama.cpp with CPU expert offload, use Unsloth Dynamic GGUFs: UD-Q4_K_XL is the default recommendation, with UD-IQ4_XS/UD-IQ4_NL_XL as smaller 4-bit options, and UD-Q3_K_XL / UD-Q2_K_XL acceptable when memory-bound. Use native MXFP4 for gpt-oss-20b. EXL3/AWQ/NVFP4 are GPU-only formats that need the whole model in VRAM, so they do not apply to MoE offload on 8GB (NVFP4 also needs Blackwell).

### Cited Findings
- Unsloth recommends Dynamic 4-bit `UD-Q4_K_XL`, and says to use "at least 2-bit dynamic quant `UD-Q2_K_XL`" for size/quality balance. A new `UD-IQ4_NL_XL` quant was added in June 2026 — [Unsloth Qwen3.6](https://unsloth.ai/docs/models/qwen3.6)
- Unsloth Dynamic 2.0: in 4-bit, "important layers upcasted to 8 or 16-bit" — [Unsloth Qwen3.5](https://unsloth.ai/docs/models/qwen3.5)
- Unsloth KL-divergence tests (July 2026) claim its GGUFs are on the "SOTA Pareto frontier", "top-performing in 21 of 22 sizes" (vendor self-claim) — [Unsloth Qwen3.6](https://unsloth.ai/docs/models/qwen3.6)
- Quality loss data point: Qwen3.5-397B-A17B UD-Q4_K_XL scored 80.5% vs 81.3% for the original (−0.8 pts) on a mixed suite including LiveCodeBench (third-party test) — [Unsloth Qwen3.5](https://unsloth.ai/docs/models/qwen3.5)
- MTP (multi-token prediction) speculative decoding gives a 1.4-2.2× speedup with no accuracy loss, best at `--spec-draft-n-max 2` (acceptance falls from 83% to 50% at 4 tokens). NVFP4 on Blackwell: 27B 2.5× faster, 35B-A3B 1.56-1.79× — [Unsloth Qwen3.6](https://unsloth.ai/docs/models/qwen3.6)
- Conversely, the 8GB/CPU-MoE reference setup found speculative decoding unhelpful and used vanilla decoding — [numsu repo](https://github.com/numsu/Qwen3.6-A3B-8GB-llama.cpp)
- gpt-oss-20b ships with MoE weights in MXFP4 natively — [NVIDIA NIM](https://docs.api.nvidia.com/nim/reference/openai-gpt-oss-20b). An MXFP4_MOE GGUF also exists for Qwen3.6-35B-A3B (21.7GB) — [HF unsloth](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF/tree/main)
- Nemotron 3.5 Lightning has an official NVFP4 checkpoint (SWE-bench Verified 52.80 vs BF16 51.56, so no loss) — [HF NVFP4](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4)
- Q8_0 KV cache is used for 256K context in the 8GB reference setup — [numsu repo](https://github.com/numsu/Qwen3.6-A3B-8GB-llama.cpp)

### Inferences
- On this rig, prefer UD-Q4_K_XL (or UD-Q4_K_S / IQ4_XS when RAM is tight) for Qwen3.6-35B-A3B. Drop to UD-Q3_K_XL (16.8GB) only if the FIM model plus other apps leave too little RAM.
- Agentic tool-use is generally more sensitive to aggressive quantization than chat. Avoid ≤Q2 for agent work where possible. This is a general community heuristic and is not quantified in the fetched sources.

### Gaps
- No 2026 EXL3 or AWQ quality/speed comparisons for these MoE models were found. No direct Q3-vs-Q4 SWE-bench degradation numbers for Qwen3.6-35B-A3B were found.

## 5. Best small FIM autocomplete models that can co-exist in VRAM

### Takeaway
The FIM ecosystem has not moved past Qwen2.5-Coder base models. llama.vscode/llama.vim presets are all Qwen2.5-Coder (1.5B/3B/7B/30B-A3B). On an 8GB card shared with an offloaded MoE, Qwen2.5-Coder-1.5B (≈1GB) or 3B base is the realistic co-resident autocomplete model. Qwen3.6/3.5 general models are not documented as FIM-trained.

### Cited Findings
- llama.vscode presets by VRAM: >64GB `--fim-qwen-30b-default`; 16-64GB `--fim-qwen-7b-default`; 8-16GB `--fim-qwen-3b-default`; <8GB `--fim-qwen-1.5b-default`. The same README says "gpt-oss 20B is the best choice" for its agent feature — [ggml-org/llama.vscode](https://github.com/ggml-org/llama.vscode)
- Qwen2.5-Coder 1.5B base: ~986MB download, Apache 2.0, FIM-trained, within a sub-500ms latency budget even on CPU. Continue's validated local stack is qwen2.5-coder:7b for chat plus qwen2.5-coder:1.5b for autocomplete. "llama.vscode's own preset tiers are all Qwen2.5-Coder FIM builds", so "the dedicated-autocomplete ecosystem has not moved to the Qwen3 generation yet" — [localaimaster FIM comparison](https://localaimaster.com/blog/best-local-autocomplete-models) / [insiderllm](https://insiderllm.com/guides/best-local-coding-models-2026/) (aggregators, consistent with llama.vscode README)
- Qwen2.5-Coder 7B, ~5GB at Q4_K_M and ~50 tok/s on an RTX 4060, is described as the strongest 7B-class completion model; DeepSeek-Coder 6.7B is a close second for FIM — [localaimaster 8GB](https://localaimaster.com/vram/best-coding-llm-8gb-vram)

### Inferences
- Suggested split: run Qwen2.5-Coder-1.5B (or 3B) base Q8_0/Q4 fully on GPU in a second llama-server (~1-2.5GB VRAM incl. small context). Run Qwen3.6-35B-A3B with attention/shared layers on GPU and experts on CPU, increasing `--n-cpu-moe` until both fit. The 30B-A3B FIM preset (Qwen3-Coder-30B-A3B) could also serve FIM and chat from one process, but it is a 2025 model and is slow for latency-sensitive autocomplete with offload.

### Gaps
- No 2026 FIM-specific benchmark (e.g., HumanEval-FIM, SAFIM) comparing Qwen2.5-Coder with newer models was found. FIM support in Qwen3.6/Gemma 4/GLM-4.7-Flash is not documented on their cards.

## 6. Known issues: tool-call format bugs, chat templates, thinking vs non-thinking

### Takeaway
Tool calling through llama.cpp's OpenAI-compatible server is the main fragility. Qwen3.5/3.6 use an XML-style `qwen3_coder` tool format that has had repeated parsing bugs: tool calls emitted inside reasoning_content or inside thinking, leaked as plain content, or broken by text before `<tool_call>`. Unsloth shipped chat-template fixes. Use recent llama.cpp builds with `--jinja` and Unsloth's fixed templates, and use thinking-mode sampling for coding.

### Cited Findings
- Unsloth Mar 5, 2026 update: "tool-calling improved following our chat template fixes. Fix is universal and applies to any Qwen3.5 format and any uploader." Qwen3.5 GGUFs did not work in Ollama at the time, because of separate mmproj vision files — [Unsloth Qwen3.5](https://unsloth.ai/docs/models/qwen3.5)
- Qwen3.6: "improved parsing nested objects to make tool calling succeed more". Developer-role support was added for Codex, OpenCode and others. `preserve_thinking` is available via `--chat-template-kwargs` — [Unsloth Qwen3.6](https://unsloth.ai/docs/models/qwen3.6)
- llama.cpp #22684 (May 4, 2026): Qwen3.5/3.6 tool calls streamed inside `delta.reasoning_content` with `finish_reason: stop` (GitHub Copilot client). Closed as stale/not planned — [llama.cpp #22684](https://github.com/ggml-org/llama.cpp/issues/22684)
- llama.cpp #20837: Qwen3.5 9B often prints tool calls as XML inside the thinking block and stops when thinking is enabled — [llama.cpp #20837](https://github.com/ggml-org/llama.cpp/issues/20837)
- llama.cpp #21158: Qwen3.5-27B tool call parsing still broken after PR #20424 (build 8576) — [llama.cpp #21158](https://github.com/ggml-org/llama.cpp/issues/21158)
- OpenClaw issue: with Qwen3.5-35B-A3B on llama.cpp, any text before `<tool_call>` breaks all structured tool calls — [openclaw #32916](https://github.com/openclaw/openclaw/issues/32916)
- llama.cpp #30078 (Oct 7, 2026): in the PEG parser, well-formed `<tool_call>` blocks get assigned to content instead of tool_calls, failing stochastically in ~30-50% of runs on a Qwen3.8-derived model. No workaround yet — [llama.cpp #30078](https://github.com/ggml-org/llama.cpp/issues/30078)
- Qwen3.6 sampling: thinking/coding temp 0.6, top_p 0.95, top_k 20, presence 0. Non-thinking temp 0.7, top_p 0.8, presence_penalty 1.5. Disable thinking with `--chat-template-kwargs '{"enable_thinking":false}'` — [Unsloth Qwen3.6](https://unsloth.ai/docs/models/qwen3.6)
- GLM-4.7-Flash: use Preserved Thinking for agentic tasks, tool parser `glm47` — [HF](https://huggingface.co/zai-org/GLM-4.7-Flash). gpt-oss uses Harmony format — [NVIDIA](https://docs.api.nvidia.com/nim/reference/openai-gpt-oss-20b). Gemma 4 uses its own `<|tool_call>` tokens and `<|think|>` toggle — [HF Gemma 4](https://huggingface.co/google/gemma-4-26B-A4B-it)
- Long agent sessions on hybrid/recurrent Qwen3.6 can trigger full prompt re-processing in llama.cpp, because checkpoints are rejected. A patch exists in the numsu repo — [numsu repo](https://github.com/numsu/Qwen3.6-A3B-8GB-llama.cpp)

### Inferences
- For Cline/Roo Code, which use their own XML-in-text tool protocol in many modes, native-tool-call parser bugs matter less. OpenCode and Claude-Code-style harnesses rely on native OpenAI tool_calls, so llama.cpp parser bugs hit them directly. Keep llama.cpp updated and test.
- Suitability summary (inference from all of the above):
  - (a) Agentic coding: Qwen3.6-35B-A3B (best), then GLM-4.7-Flash, then gpt-oss-20b (fast, weaker).
  - (b) Chat Q&A: Qwen3.6-35B-A3B, Gemma 4 26B-A4B, or Qwen3.5-9B fully on GPU for speed.
  - (c) FIM: Qwen2.5-Coder-1.5B/3B base co-resident on GPU.

### Gaps
- No reliability statistics (e.g., % successful tool calls in Cline/Roo/OpenCode) were found per model. Evidence is anecdotal or issue-based.
- Status of gpt-oss Harmony-format tool-calling issues in llama.cpp/Cline in 2026 was not verified.
