# Coding Agent Harnesses & VS Code Extensions for Small Local LLMs (Linux, 8GB GPU) — as of Oct 2026

Research date: 2026-10-07. ~23 tool calls. Many sources are secondary blogs (localaimaster, insiderllm, promptquorum, morphllm); primary sources (official docs, GitHub) are flagged where used. Treat blog "ranking" claims as opinion.

## VS Code extensions: status, local-model support, and which do FIM tab autocomplete

### Takeaway
For agentic work inside VS Code the maintained options are Cline (it has the most local-specific work, including a "Use Compact Prompt" mode), Kilo Code, and Copilot Chat BYOK. Roo Code shut down in May 2026. For FIM tab autocomplete with a local model, use Continue, llama.vscode, Tabby or Kilo Code. Copilot BYOK does not do local inline completions, and Twinny is effectively abandoned.

### Cited Findings
**Cline**
- Official Cline docs tell local users to enable **"Use Compact Prompt" (Settings → Features)** and to keep tasks focused. Default ports: Ollama 11434, LM Studio 1234, Atomic Chat 1337. RAM guidance: 16–32GB for small/quantized models, 32–64GB for mid-size coding models, 64GB+ for larger models and bigger context — [Cline docs: Local models](https://docs.cline.bot/running-models-locally/overview)
- In v3.35, Cline moved from XML tool definitions in the system prompt to **native tool calling (JSON schemas)**, but only for "next-generation models" (Claude 4+, Gemini 2.5, Grok 4, GPT-5) on specific providers (Cline, Anthropic, Gemini, OpenRouter, xAI, OpenAI-native, Vercel AI Gateway). "Models without native support continue using the text-based approach" — [Cline blog v3.35](https://cline.bot/blog/cline-v3-35)
- Open bug #10843 (opened 2026-05-18, Cline 3.83.0, `ollama:qwen2.5-coder:32b`): the local model emits JSON tool calls, Cline's parser expects XML, and Cline goes into an infinite loop. The reporter fixed it by telling the model to emit XML through `.clinerules`. No maintainer response yet — [GitHub cline#10843](https://github.com/cline/cline/issues/10843)
- A community discussion asks Cline to support gpt-oss native tool calling — [cline Discussion #5734](https://github.com/cline/cline/discussions/5734)
- A blog says "Cline has done more real engineering on the local path than any competitor, including a compact system prompt built specifically for Ollama and LM Studio and native tool calling per model family" (opinion; ~63.9k stars) — [morphllm open-source assistants](https://www.morphllm.com/ai-coding-assistant-open-source)
- Known problems with local models: agent loops fail more often, approving every action gets tedious, and token use is heavy. The blog recommends 24GB VRAM "for full capability" — [insiderllm local alternatives (updated 2026-06-18)](https://insiderllm.com/guides/local-alternatives-claude-code-2026/)
- One blog puts the system prompt at roughly 7–10k tokens each for Cline, OpenCode and Claude Code, versus <1k for Pi — [pinggy CLI agents 2026](https://pinggy.io/blog/best_open_source_cli_coding_agents/) (secondary; I did not verify the Cline number against a primary source)

**Roo Code (discontinued)**
- Shutdown announced **2026-04-21** and the GitHub repo archived **2026-05-15**. roocode.com now redirects to roomote.dev. The team moved to Roomote, a Slack-based ops agent, and said they "don't believe IDEs are the future of coding". Their official migration recommendation is Cline — [localaimaster Roo shutdown](https://localaimaster.com/blog/roo-code-shutdown-local-alternative); [rywalker research](https://rywalker.com/research/roo-code); [Kilo compare page](https://kilo.ai/compare/roo-code-shutdown-roomote) (vendor source)

**Kilo Code**
- An active fork that reads `.roomodes` and `.roo/rules/` directly and publishes a Roo→Kilo migration guide. Features include parallel subagents, an Agent Manager with git worktrees, **Autocomplete**, and shared sessions between CLI and VS Code — [Kilo migration guide](https://kilo.ai/articles/roo-to-kilo-migration-guide); [localaimaster](https://localaimaster.com/blog/roo-code-shutdown-local-alternative)
- ~19.9k GitHub stars (vs Cline ~63k, OpenCode ~172k) — [morphllm](https://www.morphllm.com/ai-coding-assistant-open-source)

**GitHub Copilot Chat BYOK (VS Code)**
- VS Code blog (2026-06-18): BYOK "work[s] without signing into a GitHub account and without a Copilot plan", including fully offline use with local models (Ollama, Foundry Local named). Agent mode works only "when the selected model supports the required capabilities". **BYOK covers chat and utility tasks, not standard code completions.** Semantic search and embeddings features still need GitHub/Copilot — [VS Code blog: BYOK](https://code.visualstudio.com/blogs/2026/06/18/byok-vscode)
- VS Code docs (current):
  - The built-in **Ollama provider is deprecated**; install the official Ollama extension instead.
  - A new **"Custom Endpoint" provider** (Chat Completions, Responses, or Anthropic Messages API) replaces the deprecated "OpenAI Compatible" provider. `github.copilot.chat.customOAIModels` is deprecated.
  - Agent mode needs tool-calling models.
  - "Currently, you cannot connect to a local model for inline suggestions."

  [VS Code docs: language models](https://code.visualstudio.com/docs/copilot/customization/language-models)
- The separate GitHub Copilot *app* got BYOK on 2026-06-23 with LM Studio, Ollama and any OpenAI-compatible endpoint (host only, no key needed for local). Copilot CLI got BYOK/local on 2026-04-07 — [GitHub changelog 2026-06-23](https://github.blog/changelog/2026-06-23-github-copilot-app-support-for-byok/); [Copilot CLI BYOK docs](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-byok-models)
- A third-party extension (JohnnyZ93/oai-compatible-copilot) plugs OpenAI/Ollama/Anthropic/Gemini-compatible endpoints into Copilot Chat — [GitHub](https://github.com/JohnnyZ93/oai-compatible-copilot)

**Continue**
- Recommended local stack: an instruct model for chat (e.g. qwen2.5-coder:7b) plus a small FIM-trained base model for tab autocomplete (qwen2.5-coder:1.5b). Supports Ollama out of the box — [insiderllm replace Copilot](https://insiderllm.com/guides/replace-github-copilot-local-llms-vscode/); [markaicode Ollama+Continue 2026](https://markaicode.com/integrate/ollama-with-continuedev/)
- Continue is "not an agent" in the sense of Cline, its configuration can be complex, and 7B completion lags Copilot — [insiderllm](https://insiderllm.com/guides/local-alternatives-claude-code-2026/)
- gpt-oss tool calls were not supported (issue requesting a native_tool_call_adapter) — [continuedev/continue#7805](https://github.com/continuedev/continue/issues/7805) (I did not check whether it is resolved yet)

**llama.vscode (ggml-org)**
- FIM "auto-suggest on input" with Tab to accept, plus a "Llama Agent" UI (Ctrl+Shift+A) with MCP and 9 internal tools. Connects straight to llama-server with no Ollama layer (e.g. `--fim-qwen-[size]-default` presets). VRAM model guide:
  - 8–16GB: Qwen 3B
  - <8GB: Qwen 1.5B
  - CPU-only: Qwen 0.5B

  Linux needs a manual llama.cpp binary install. MIT license, ~1.5k stars — [GitHub ggml-org/llama.vscode](https://github.com/ggml-org/llama.vscode)
- Skipping Ollama gives "slightly lower overhead on resource-limited machines" — [sitepoint/insiderllm summaries](https://insiderllm.com/guides/replace-github-copilot-local-llms-vscode/)

**Tabby**
- A self-hosted server (Docker) with its own model management. It does completion and chat only, with no agent mode. Suggested models are StarCoder-1B and Qwen2-1.5B-Instruct — [insiderllm](https://insiderllm.com/guides/local-alternatives-claude-code-2026/)

**Twinny**
- The official site shows "TWINNY HAS BEEN ARCHIVED". The Marketplace extension has not been updated since Aug 2025, though the GitHub repo merged a community PR on 2026-09-02 — [promptquorum Twinny review](https://www.promptquorum.com/power-local-llm/twinny-review)

**Others**
- Void: an open-source Cursor-like editor with local models, still in beta. Its agent mode is weaker with local models — [insiderllm](https://insiderllm.com/guides/local-alternatives-claude-code-2026/)

### Inferences
- On an 8GB GPU you cannot comfortably fit both a 7B+ agent model and a separate FIM model in VRAM. A practical split is a 1.5B–3B FIM model in llama.vscode or Continue for autocomplete, with agent work done one task at a time (or the agent model offloaded to CPU/RAM).
- The Cline native-tool-call path does not appear to cover Ollama/LM Studio/OpenAI-compatible providers (per the v3.35 provider list), so local models likely still use the XML text protocol. The Compact Prompt is the main mitigation. Small models that can't reliably emit Cline's XML will loop (#10843).
- Copilot BYOK is usable for local chat and agent work but does nothing for autocomplete. Copilot plus a separate FIM extension is a valid combination.

### Gaps
- I found no primary measurement of the Cline Compact Prompt token size, or the current full-prompt size of Cline or Kilo. The often-quoted "Cline/Roo 10k+ tokens" figure is folklore here; the only number I found is pinggy's "7–10k".
- I could not confirm whether Kilo Code's autocomplete works with local Ollama/LM Studio FIM models or only through Kilo's gateway.
- I could not confirm whether Cline has since added native tool calling for the Ollama/LM Studio providers (after v3.35).
- Continue's current version and status of gpt-oss tool calling are unverified.

## CLI agents: setup with local endpoints, tool calling, prompt overhead

### Takeaway
Codex CLI (`--oss`), Qwen Code, OpenCode, Crush, Goose, Aider, Pi and Claude Code all run against local OpenAI- or Anthropic-compatible servers. Claude Code has the heaviest upfront context (~33k tokens) and Pi the lightest (<1k). For small models, the best-documented successes are Qwen3.x-A3B MoE with Codex, Qwen Code or Claude Code.

### Cited Findings
**Claude Code**
- Setting `ANTHROPIC_BASE_URL` points Claude Code at any server that speaks the Anthropic Messages format. LM Studio added a native `/v1/messages` endpoint in **v0.4.1**. llama-server supports `POST /v1/messages` (with SSE) and `/v1/messages/count_tokens` — [KDnuggets](https://www.kdnuggets.com/pairing-claude-code-with-local-models); [LM Studio blog](https://lmstudio.ai/blog/claudecode)
- LM Studio's official setup:
  - Environment: `ANTHROPIC_BASE_URL=http://localhost:1234`, `ANTHROPIC_AUTH_TOKEN=lmstudio`, `CLAUDE_CODE_ATTRIBUTION_HEADER=0`.
  - Context: **25k+ tokens recommended** because "Claude Code can consume a lot of context".
  - Example model: `openai/gpt-oss-20b`.

  [LM Studio docs: Claude Code](https://lmstudio.ai/docs/integrations/claude-code)
- A logging-proxy study (2026-07-12, Claude Code 2.1.207 vs OpenCode 1.17.18) measured the first-turn baseline:

  | Harness | System prompt | Tool schemas | First-turn total |
  |---|---|---|---|
  | Claude Code | ~6.5k | ~24k (27 tools) | **~33k** |
  | OpenCode | ~2k | ~4.8k (10 tools) | **~7k** |

  A 72KB instruction file adds about 20k tokens per request. Five MCP servers add 4.9k (Claude Code) or 7k (OpenCode). OpenCode keeps byte-identical prefixes, so its cache works much better. Both had equal pass rates — [systima.ai](https://systima.ai/blog/claude-code-vs-opencode-token-overhead)
- With instruction files, MCP and plugins, Claude Code sent about 75k tokens upfront in real use — [digitaltoday](https://www.digitaltoday.co.kr/en/view/81376/claude-code-sends-33000-tokens-before-questions-in-real-use-up-to-75000); one user measured 51k before trimming — [XDA](https://www.xda-developers.com/claude-code-using-fifty-thousand-tokens-before-typed-prompt-fixed-it/)
- Proxies and routers (claude-code-router, CodeRouter, etc.) are surveyed in [note.com zephel01 "5 paths"](https://note.com/zephel01/n/ne471e3a7d4b7?hl=en) and [pchalasani claude-code-tools local LLMs](https://pchalasani.github.io/claude-code-tools/integrations/local-llms/) (not deeply reviewed)

**Codex CLI**
- `codex --oss` routes to a local provider (Ollama or LM Studio) and defaults to `gpt-oss:20b` on Ollama (~14GB download). No API key or sign-in is needed — [localaimaster Codex+Ollama](https://localaimaster.com/blog/codex-cli-ollama-local); [ynaito.dev](https://ynaito.dev/en/writing/codex-cli-local-models-oss/); [knightli 2026-06-18](https://knightli.com/en/2026/06/18/codex-cli-oss-mode-local-model-guide/)

**Qwen Code**
- Configure it for Ollama's OpenAI-compatible endpoint `http://127.0.0.1:11434/v1` or for LM Studio (v0.14.x+) — [LM Studio Hub doc](https://lmstudio.ai/tupik/top/files/docs/qwen_code_local.md)
- The r/LocalLLaMA standard setup is LM Studio + Qwen3-Coder on :1234 with Qwen Code as the harness — [padron.sh](https://padron.sh/blog/ai-coding-assistant-local-setup/) (citing r/LocalLLaMA)

**Sebastian Raschka, "Using Local Coding Agents" (2026-06-27)**
- He tested Qwen3.6 35B-A3B across harnesses. Task success was **4/5 in Qwen-Code, 5/5 in Codex, 5/5 in Claude Code**.
- Speed was about 40 tok/s on an M4 Mac Mini and 30 tok/s on a DGX Spark at 50k context.
- Gemma 4 E2B scored 0/5 on a reasoning/tool test, against 3/5 for Qwen3.6.
- Codex used fewer tokens than Claude Code, which accumulated large histories (578k input vs 4.5k output in one example).
- He recommends starting with Codex or Qwen-Code, and calls >20–30 tok/s "reasonable" for agent work.

  [Raschka](https://magazine.sebastianraschka.com/p/using-local-coding-agents)

**OpenCode**
- ~2k-token system prompt and ~7k first turn (above). Most-starred OSS agent (~172k) — [morphllm](https://www.morphllm.com/ai-coding-assistant-open-source)
- Local setup guides: [explainx OpenCode local 2026](https://explainx.ai/blog/how-to-run-open-source-models-locally-opencode-2026); [confidence.sh Opencode+Qwen](https://confidence.sh/blog/the-local-ai-stack-opencode-qwen/)
- **Conflict:** insiderllm describes OpenCode as a "Go-based terminal agent" with a "quiet upstream since September 2025" — [insiderllm](https://insiderllm.com/guides/local-alternatives-claude-code-2026/). This seems to confuse it with the original Go `opencode-ai/opencode`, which became Charm's Crush. The systima study benchmarked OpenCode 1.17.18 in July 2026, so sst/OpenCode is clearly active.

**Crush (Charm)**
- Ollama setup: `provider add ollama --type ollama --base-url "http://localhost:11434/v1/"` in `~/.config/crush/crushrc`. Configuration moved from JSON to a Bash-style `crushrc` in **v0.88.0 (July 2026)**, so older tutorials are outdated. It has LSP-enhanced context and MCP support — [localaimaster Crush](https://localaimaster.com/blog/crush-ollama-setup)
- Common failure: the model "talks about" actions without calling tools because **Ollama's default 4,096-token context silently truncates the tool schemas**. Fix with `OLLAMA_CONTEXT_LENGTH=65536 ollama serve` — [localaimaster Crush](https://localaimaster.com/blog/crush-ollama-setup)

**Goose**
- Relies on native tool calling for every action. The **Tool Shim** (`GOOSE_TOOLSHIM=true`) is experimental: it uses a second interpreter model (default `mistral-nemo` on Ollama) to turn text-format tool calls into structured ones for models without native tool support — [Goose docs: Tool Shim](https://goose-docs.ai/docs/guides/tool-shim/)
- Goose added built-in local inference (llama.cpp) in April 2026 — [Goose blog 2026-04-24](https://goose-docs.ai/blog/2026/04/24/use-goose-with-built-in-local-inference/)
- Local shortlist as of Aug 2026: qwen3-coder:30b first, devstral:24b for 16GB cards, qwen3:8b only for small scoped tasks — [localaimaster Goose](https://localaimaster.com/blog/goose-ollama-local-agent)

**Aider**
- Called "the best terminal-based coding agent for local models". It edits files with automatic git commits, is terminal-only, and is weaker on large multi-file refactors — [insiderllm](https://insiderllm.com/guides/local-alternatives-claude-code-2026/)

**Pi agent**
- Four tools (read/write/edit/bash) and a ~200-token system prompt (insiderllm) or <1k (pinggy). Recommended setup is Qwen3.6 35B-A3B on 24GB, or 16GB with `--cpu-moe` offload — [insiderllm](https://insiderllm.com/guides/local-alternatives-claude-code-2026/); [pinggy](https://pinggy.io/blog/best_open_source_cli_coding_agents/)

### Inferences
- **Native vs XML tool calling:**
  - Native: Codex, OpenCode, Crush, Goose, Claude Code (Anthropic tool_use) and Copilot agent all need a server-side tool-call parser to work. That means the llama.cpp `--jinja` chat template, or LM Studio/Ollama tool support.
  - Text-based: Aider (edit formats) and Cline on local providers (XML) avoid this dependency, but small models must follow the text format exactly.
- **8GB GPU budget:**
  - A 20–30B MoE (gpt-oss-20b, Qwen3-Coder-30B-A3B, Qwen3.6-35B-A3B) needs expert/CPU offload (`--cpu-moe` / `--n-cpu-moe`), with KV cache and attention on the GPU.
  - Each 1k tokens of fixed harness prompt costs KV memory and prefill time on every new session. Claude Code's ~33k baseline effectively needs a 64k context to leave working room, while OpenCode's ~7k and Pi's <1k leave much more.
  - Prompt-processing speed under CPU offload becomes the bottleneck for heavy-prompt harnesses. Good prefix caching (OpenCode, llama-server cache reuse) helps.
- Ollama's 4k default context is the single most common cause of "tools don't work" reports. Set the context explicitly (OLLAMA_CONTEXT_LENGTH, or `-c` in llama-server) whatever the harness.

### Gaps
- I found no reliable sources for **Kimi CLI** with local models, and no measured system-prompt sizes for Codex CLI, Qwen Code, Crush, Goose or Aider.
- I found no controlled benchmark specifically on 8GB GPUs. Most community reports use 16–24GB GPUs or Apple/DGX unified memory.
- I did not directly verify the claude-code-router or LiteLLM setups.
- The current Codex `--oss` default model and LM Studio provider flag syntax (e.g. `--local-provider lmstudio`) were not confirmed from OpenAI docs.

## Community-reported working combos for small models (2025–2026)

### Takeaway
The consensus model choices are Qwen3-Coder-30B-A3B / Qwen3.6-35B-A3B (MoE, ~3B active), Devstral Small 24B, and gpt-oss-20b. Models of 8B and under are reported as viable only for scoped tasks or FIM.

### Cited Findings
- Qwen3-Coder-30B-A3B has 30B total and 3.3B active parameters, a 262k context, and a ~17–20GB 4-bit footprint — [labellerr / orcarouter summaries](https://www.orcarouter.ai/blog/best-local-llm-for-coding)
- Pairings:
  - Qwen3-Coder 30B goes with Crush/Goose/Kilo/Cline on 24GB.
  - Devstral Small 2 24B is "optimized for agent reliability" and suits 16GB.
  - qwen3:8b (5.2GB) is a budget pick for scoped tasks only.

  [localaimaster Crush](https://localaimaster.com/blog/crush-ollama-setup); [localaimaster Roo](https://localaimaster.com/blog/roo-code-shutdown-local-alternative)
- Qwen3.6 35B-A3B gave 5/5 in Codex and Claude Code and 4/5 in Qwen-Code. Gemma 4 E2B failed tool tests (0/5) — [Raschka](https://magazine.sebastianraschka.com/p/using-local-coding-agents)
- LM Studio's own example model for Claude Code is gpt-oss-20b — [LM Studio docs](https://lmstudio.ai/docs/integrations/claude-code)
- For FIM, Qwen2.5-Coder was trained for fill-in-the-middle at every size from 0.5B to 32B. 1.5B is the usual autocomplete model — [insiderllm](https://insiderllm.com/guides/replace-github-copilot-local-llms-vscode/); [localaimaster FIM models](https://localaimaster.com/blog/best-local-autocomplete-models)
- Qwen2.5-Coder-32B on Cline/Ollama loops on JSON-vs-XML tool format (bug #10843) — [GitHub](https://github.com/cline/cline/issues/10843)

### Inferences
- For 8GB VRAM plus enough system RAM, the most promising combinations are:
  - gpt-oss-20b or Qwen3-Coder-30B-A3B with MoE CPU offload, driven by a light harness (OpenCode, Pi, Codex `--oss`, Qwen Code)
  - Cline with Compact Prompt, for an in-editor agent
  - llama.vscode or Continue with Qwen2.5-Coder 1.5B for FIM
- Claude Code works but has the worst prompt-to-context ratio.

### Gaps
- Direct r/LocalLLaMA threads were not fetched (Reddit not accessed). Community claims here come via blog aggregators.

## LM Studio Bionic: Linux availability (Oct 2026)

### Takeaway
A secondary source reports Linux support (x64/ARM64) shipped in Bionic 1.1.2 on September 8 (2026 implied), but the official Bionic page as fetched showed only a Windows download. Treat Linux availability as likely but unconfirmed by a primary source.

### Cited Findings
- Bionic is "LM Studio's agent for open models", a separate app built on the LM Studio runtime (llama.cpp/MLX). It can also use cloud models (GLM 5.2, Kimi K3, DeepSeek V4 Pro) under zero data retention — [lmstudio.ai/bionic](https://lmstudio.ai/bionic)
- The official page as fetched shows only a Windows download link and no Linux mention — [lmstudio.ai/bionic](https://lmstudio.ai/bionic). This may be OS detection by the fetcher, so it is unverified.
- "Bionic 1.1.2 shipped on September 8 with full Linux support for both x64 and ARM64", installable through `curl -fsSL https://lmstudio.ai/install.sh | bash`, an AppImage, or a .deb. The MLX backend is unavailable on Linux; NVIDIA runs through llama.cpp — [gyanaangan blog](https://gyanaangan.in/blog/lm-studio-bionic-finally-runs-on-linux-v112-install-guide-and-everything-else-new-in-11/); [bitdoze](https://www.bitdoze.com/lm-studio-bionic/)
- Other reviews describe Bionic as a Windows app — [therundown](https://www.therundown.ai/tools/lm-bionic); [Micro Center](https://www.microcenter.com/site/mc-news/article/get-started-with-lm-studio-bionic.aspx). These may predate 1.1.2.

### Inferences
- Bionic is a standalone agent app, not a VS Code extension, so it does not replace an editor-integrated harness.

### Gaps
- I found no official LM Studio changelog or blog URL confirming the Linux release of Bionic 1.1.2. Check at lmstudio.ai/download on a Linux browser.
