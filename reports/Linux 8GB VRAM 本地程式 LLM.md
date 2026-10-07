# 讓 8GB 顯卡跑動 35B 程式代理

截至 2026 年 10 月，在 8GB VRAM + 約 30GB RAM 的 Linux 機器上，寫程式最划算的組合是**主線 llama.cpp 的 `llama-server`，搭配 Qwen3.6-35B-A3B（Unsloth UD-Q4_K_XL，22.4GB）**。做法是把所有層放上 GPU，再用 `--n-cpu-moe` 把大部分 MoE 專家權重留在系統 RAM。補全另開一個 Qwen2.5-Coder-1.5B base 的 FIM 小模型。前端分工如下：VS Code 裡用 Cline（開 Compact Prompt）或 Copilot Chat BYOK 當 agent，用 llama.vscode 或 Continue 做 Tab 補全，終端機用 OpenCode 或 Claude Code。

選 Qwen3.6-35B-A3B 的理由很直接。它在約 3B active 參數這一級裡的 SWE-bench Verified（73.4）和 Terminal-Bench 2.0（51.5）都是最高分，而且 40 層裡只有 10 層有 KV cache，長 context 幾乎不占 VRAM。最接近你硬體的公開實測，是一台 8GB 筆電 GPU 跑出生成 35–38 tok/s、預填 875–935 tok/s。

真正限制體驗的是預填速度（prefill），不是生成速度。agent harness 每回合都會送出數千到數萬 token 的前綴，所以 `-ub 2048` 以上的大 micro-batch、prompt cache，以及系統提示短的 harness，比多擠一兩層專家到 GPU 更重要。

要先講清楚：**目前沒有任何公開數據是在 resolute（RTX 4060 Laptop + HX 370）或 noble（RTX 5060 Ti 8GB + 9950X）上量的**。下文的數字凡標「他人實測」，都來自相近硬體；凡標「推估」，都是外推，需要在你的機器上用 `llama-bench` 驗證。

## llama-server 加專家卸載是 8GB 唯一的甜蜜點

8GB 卡要跑比 VRAM 大的模型，關鍵是「逐張量（per-tensor）切分」：attention、shared expert 和 KV 放 GPU，routed experts 放 CPU。目前只有 GGUF／llama.cpp 家族把這件事做得成熟，包括主線 llama.cpp、ik_llama.cpp，以及包裝它們的 LM Studio（llmster）和 Ollama。主線 `llama-server` 提供 `--cpu-moe`（全部專家放 CPU）、`--n-cpu-moe N`（前 N 層的專家放 CPU）和 `-ot` 正則覆寫三種控制 ([llama-server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md))。它還同時提供 OpenAI `/v1/chat/completions`、`/v1/responses`，以及 **Anthropic `/v1/messages`（含 `count_tokens`、tool_use、thinking）**，Claude Code 可以直接接上 ([HF blog](https://huggingface.co/blog/ggml-org/anthropic-messages-api-in-llamacpp))。主線在 2026-05-16 合併了 Multi-Token Prediction（`--spec-type draft-mtp`）([PR #22673](https://github.com/ggml-org/llama.cpp/pull/22673))。Linux 版有 CUDA 12.8 與 13.4 的預編譯檔，build 編號是滾動式的，本文撰寫時是 `b11465` ([llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases))。

卸載的效益有實測可證。同一張 RTX 3060 Ti 8GB 跑 Qwen3-Coder-30B-A3B：用 `--cpu-moe` 只有 **13.38 tok/s**；把 `--n-cpu-moe` 調到 40、讓 VRAM 用到 7,265MB 後，升到 **32.49 tok/s**，約 2.4 倍 ([dev.to](https://dev.to/upayanghosh/from-oom-to-262k-context-running-qwen3-coder-30b-locally-on-8gb-vram-1ej1))。調法是先把 N 設高，再逐步調低，直到速度突然崩落（代表 VRAM 溢出到共享記憶體），然後退回一格。RTX 5090 上的掃描就看得到這種懸崖：n=12 時 69.4 tok/s，再往下就跌到 27.5 ([openclawdc](https://openclawdc.com/blog/llama-cpp-moe-offload-flags-explained/))。

其他引擎各有不適合的地方：

| 引擎 | 結論 | 原因 |
|---|---|---|
| ik_llama.cpp | 值得做效能 A/B | 有 fused MoE、IQK 量化、MTP，社群把它當 MoE 混合推論的首選 ([Doctor-Shotgun](https://huggingface.co/blog/Doctor-Shotgun/llamacpp-moe-offload-guide))。但它在 CPU/GPU 混合 MoE 下不能用 `-rtr`，含 f16 張量的 Unsloth `_XL` 檔可能載入失敗 ([ik_llama.cpp README](https://github.com/ikawrakow/ik_llama.cpp))，也沒確認有 `/v1/messages` |
| LM Studio / llmster | 最省事的備案 | 有「Force Model Expert Weights onto CPU」選項 ([LM Studio 0.3.23](https://www.lmstudio.ai/blog/lmstudio-v0.3.23))、Anthropic 端點（0.4.1 起）和 MTP。2025 年時該選項還是全有或全無的開關，現在有沒有逐層滑桿未確認 ([bug tracker #900](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/900)) |
| Ollama | 不建議用在比 VRAM 大的 MoE | `num_moe_offload` PR 沒被合併，維護者傾向自動配置 ([Ollama #11005](https://github.com/ollama/ollama/issues/11005))。Anthropic 端點沒有 `count_tokens`、不支援 `tool_choice` ([Ollama docs](https://docs.ollama.com/api/anthropic-compatibility))。預設 4,096 context 會悄悄截掉工具 schema ([localaimaster](https://localaimaster.com/blog/crush-ollama-setup)) |
| vLLM / SGLang / ExLlamaV3 | 只適合整個模型放得進 8GB 的情況 | 主打 GPU 常駐與批次吞吐。vLLM 在 sm_120 上需要從原始碼編譯 ([vLLM #35432](https://github.com/vllm-project/vllm/issues/35432)) |
| KTransformers | 不適用 | 參考配置是 24GB GPU 加 AMX/AVX512 伺服器 CPU ([KTransformers](https://github.com/kvcache-ai/ktransformers)) |

noble 的 RTX 5060 Ti 是 Blackwell（sm_120），需要 **CUDA Toolkit ≥ 12.8、驅動 ≥ 570**，自行編譯時要加 `-DCMAKE_CUDA_ARCHITECTURES=120`。如果出現「no kernel image is available」，代表要重新編譯 ([bestllmfor sm120](https://bestllmfor.com/guides/llama-cpp-cuda-blackwell-sm120-build/))。

resolute 的風險在筆電功耗。有人回報 Linux 下 RTX 4060 Laptop 的功耗上限被鎖在 60W，規格是 140W，要靠 `nvidia-powerd`（Dynamic Boost）解鎖 ([NVIDIA 論壇](https://forums.developer.nvidia.com/t/the-default-power-limit-of-my-4060-laptop-halves-its-performance/294699)；[NVIDIA README](https://download.nvidia.com/XFree86/Linux-x86_64/580.126.18/README/dynamicboost.html))。Dynamic Boost 在 AMD CPU 筆電上能不能用，目前沒有來源確認。

Blackwell 的 NVFP4 加速在這裡派不上用場。Unsloth 測到 35B-A3B 快 1.56–1.79 倍，但前提是整個模型放在 GPU 上 ([Unsloth Qwen3.6](https://unsloth.ai/docs/models/qwen3.6))，8GB 放不下。

## Qwen3.6-35B-A3B 以 Q4 量化稱霸 30GB RAM 預算

扣掉作業系統、VS Code 和瀏覽器，8GB VRAM + 30GB RAM 能放的 GGUF 大約在 28GB 以內，而且只有 MoE 能跑得快。dense 模型一旦溢出到 CPU，每個 token 都要讀過全部權重，速度直接掉到個位數。Qwen3.8-27B 是目前分數最好的小型開放模型，但在 RTX 4060 8GB 上實測只有 **5–6 tok/s**，同一台機器跑 Qwen3.6-35B-A3B 則有 15–18 tok/s ([r/LocalLLaMA 快照](https://reddit.sentinel-team.org/posts/1w6y128/snapshots/2026-09-04T21%3A20%3A12.3645Z))。所以這個預算下該看的是「35B 總參數、約 3B active」這一級的 MoE。

| 模型 | SWE-bench Verified | Terminal-Bench | LiveCodeBench v6 | Q4 檔案大小 | 定位 |
|---|---|---|---|---|---|
| **Qwen3.6-35B-A3B** | 73.4（官方）／70.12（NVIDIA 評測） | TB2.0 51.5 | 80.4 | UD-Q4_K_XL 22.4GB | 首選 agent、對話 |
| GLM-4.7-Flash（30B-A3B） | 59.2 | — | 64.0 | 約 18GB | 第二選擇，τ² 79.5，工具使用強 |
| gpt-oss-20b | 60.7（NVIDIA）／34.0（Z.ai 表） | — | 61.0 | MXFP4 約 13–15GB | 最小最快的 MoE，llama.cpp 有官方 8GB 配方 |
| Gemma 4 26B-A4B | 無官方數字 | — | 77.1 | 約 16–18GB | 對話、演算法題 |
| Nemotron 3.5 Lightning 30B-A3B | 51.56 | TB2.1 24.58 | — | Q4 | 偏速度與指令遵循 |
| Qwen3.5-9B（dense） | — | — | 65.6 | 4-bit 約 6.5GB | 能整個放進 VRAM 的快速對話模型 |

表中數據來源：[Qwen3.6 卡](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)、[NVIDIA Nemotron 卡](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16)、[GLM-4.7-Flash 卡](https://huggingface.co/zai-org/GLM-4.7-Flash)、[NVIDIA NIM gpt-oss](https://docs.api.nvidia.com/nim/reference/openai-gpt-oss-20b)、[Gemma 4 卡](https://huggingface.co/google/gemma-4-26B-A4B-it)、[Qwen3.5-9B 卡](https://huggingface.co/Qwen/Qwen3.5-9B)。

各家自報分數會因評測 harness 不同差很多。gpt-oss-20b 有 60.7 和 34.0 兩種說法，就是同一個模型在兩張表上的差距。比較可信的是 NVIDIA 的第三方表：在那裡 Qwen3.6-35B-A3B 仍領先 Nemotron 約 19 分。

Qwen3.6-35B-A3B 還有一個對 8GB 特別有利的架構特性。它的 40 層排成 10 組「3 層 Gated DeltaNet + 1 層 Gated Attention」，**只有 10 層需要 KV cache**。原生 context 是 262,144 ([HF 模型卡](https://huggingface.co/Qwen/Qwen3.6-35B-A3B))，長 context 的 VRAM 代價很小。Sebastian Raschka 用它測了幾個 harness：Codex 和 Claude Code 都是 5/5，Qwen Code 是 4/5 ([Raschka](https://magazine.sebastianraschka.com/p/using-local-coding-agents))。

**量化選擇：預設用 Unsloth UD-Q4_K_XL（22.4GB）**，RAM 吃緊時改用 UD-Q4_K_S（20.9GB）或 UD-IQ4_XS（17.7GB）。UD-Q3_K_XL（16.8GB）是最後的退路 ([Unsloth GGUF 清單](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF/tree/main))。Unsloth 的 Dynamic 量化會把重要的層升到 8 或 16-bit。第三方測試裡，Qwen3.5-397B 的 UD-Q4_K_XL 只比原版低 0.8 分 ([Unsloth Qwen3.5](https://unsloth.ai/docs/models/qwen3.5))。

最接近 resolute 的參考配置用的是 UD-Q6_K_XL（31.8GB），但那台有 64GB RAM，作者也明說 32GB 系統會有「明顯的頻寬限制」([numsu repo](https://github.com/numsu/Qwen3.6-A3B-8GB-llama.cpp))，所以 30GB 的機器不要照抄 Q6。EXL3、AWQ、NVFP4 都是 GPU 常駐格式，不適用於專家卸載。

**Tab 補全另用專門的模型。** FIM（fill-in-the-middle）生態還停在 Qwen2.5-Coder 世代。llama.vscode 的預設檔依 VRAM 分級：8–16GB 用 3B、8GB 以下用 1.5B ([llama.vscode](https://github.com/ggml-org/llama.vscode))。Qwen3.6、Gemma 4、GLM 的模型卡都沒寫有 FIM 訓練，因此主模型不能兼任補全。Qwen2.5-Coder-1.5B base 下載約 986MB，即使在 CPU 上也能做到 500ms 以內的延遲 ([localaimaster](https://localaimaster.com/blog/best-local-autocomplete-models))。

## 預填而非生成速度決定 agent 體驗

下表是公開的他人實測，硬體都和你的機器相近，但沒有一台完全相同：

| 情境 | 硬體 | 預填 tok/s | 生成 tok/s | 來源 |
|---|---|---|---|---|
| Qwen3.6-35B-A3B UD-Q6_K_XL，262K ctx，q8_0 KV，專家在 CPU | 8GB 筆電 GPU + Core Ultra 7 265HX + **64GB** | 875–935 | **35–38** | [numsu](https://github.com/numsu/Qwen3.6-A3B-8GB-llama.cpp) |
| Qwen3.6-35B-A3B | RTX 4060 8GB + 12 核 + 64GB **DDR4** | — | 15–18 | [r/LocalLLaMA](https://reddit.sentinel-team.org/posts/1w6y128/snapshots/2026-09-04T21%3A20%3A12.3645Z) |
| Qwen3-Coder-30B-A3B Q4_K_XL，`--n-cpu-moe 40`，32K | RTX 3060 Ti 8GB + 32GB | 51.6（小 ubatch） | **32.5** | [dev.to](https://dev.to/upayanghosh/from-oom-to-262k-context-running-qwen3-coder-30b-locally-on-8gb-vram-1ej1) |
| Qwen3.5-35B-A3B Q4_K_M，專家全在 CPU，102K | RTX 2060 **6GB 筆電** + 32GB | 350–400 | ~15 | [Discussion #21112](https://github.com/ggml-org/llama.cpp/discussions/21112) |
| Qwen3.5-9B Q4_K_M，全部在 GPU，32K | RTX 3070 8GB | ~1,932 | 54.9 | [localllm.in](https://localllm.in/blog/best-local-llms-8gb-vram-2025) |

另外有一則 HF 討論宣稱 RTX 4060 Laptop + 32GB 跑出 33–34 tok/s，但參數不公開、只提供改過的二進位檔，可信度低，所以不列入表中 ([HF #58](https://huggingface.co/Qwen/Qwen3.6-35B-A3B/discussions/58))。

**生成速度主要看系統 RAM 頻寬。** 專家權重在 RAM 裡，每個 token 都要讀一遍。Framework 社群對 Ryzen AI 300 的判斷也是輸出速度受頻寬限制 ([Framework 社群](https://community.frame.work/t/fw13-ai-370-performance/70063))。

**【推估】** resolute 的 HX 370 用的是 LPDDR5X，noble 的 9950X 用雙通道 DDR5，兩者屬於同一頻寬等級。筆電的劣勢比較可能出現在 PCIe 鏈路、GPU 功耗牆和長時間降頻，影響的主要是預填。換成 Q4 後每個 token 要讀的位元組比 Q6 少，因此推估 **Qwen3.6-35B-A3B UD-Q4_K_XL 在 64K context 下，resolute 生成約 20–35 tok/s、noble 約 25–40 tok/s**。這兩個數字都要實測確認。

**預填才是 agent 的瓶頸。** 一次處理的 token 夠多時，llama.cpp 會把放在 CPU 的專家權重經 PCIe 搬到 GPU，整批一起算，所以預填速度取決於 micro-batch 大小和 PCIe 頻寬 ([Doctor-Shotgun](https://huggingface.co/blog/Doctor-Shotgun/llamacpp-moe-offload-guide))。上表的 3060 Ti 用 64–256 的小 ubatch，只有 40–52 tok/s；6GB 筆電用正確設定就有 350–400 tok/s。

換算成實際等待時間（純算術）：Claude Code 第一回合約送出 **33k token**，OpenCode 約 **7k** ([systima.ai](https://systima.ai/blog/claude-code-vs-opencode-token-overhead))。

| 預填速度 | Claude Code 首回合（33k） | OpenCode 首回合（7k） |
|---|---|---|
| 900 tok/s | 約 37 秒 | 約 8 秒 |
| 350 tok/s | 約 94 秒 | 約 20 秒 |
| 50 tok/s | 超過 11 分鐘 | 超過 2 分鐘 |

這就是 `-b 2048 -ub 2048`（甚至 4096）必開的原因。代價是 compute buffer 會占 VRAM，`--n-cpu-moe` 要多讓出一兩層。

**context 的取捨。** KV cache 只會和你選擇留在 GPU 的專家搶 VRAM。Qwen3.6 只有 10 層有 KV，所以 numsu 能在 8GB 上用 q8_0 KV 跑到 262K。但 context 越大，能放上 GPU 的專家越少，長 context 下的生成速度也會下降：舊世代實測約是 32K 時 30 tok/s、102K 時 15 tok/s ([Discussion #21112](https://github.com/ggml-org/llama.cpp/discussions/21112))。

KV 量化是省記憶體用的，不是加速用的：放得下的話，f16 比 q8_0 快 ([openclawdc](https://openclawdc.com/blog/llama-cpp-moe-offload-flags-explained/))。社群偏好 q8_0，不建議 q4_0。

實務上建議這樣配：Claude Code 至少開 **64K**，因為光基線就有 33k；OpenCode 和 Cline 開 32–64K。

**MTP 的實際效果還不確定。** Unsloth 回報 MTP 能加速 1.4–2.2 倍，`--spec-draft-n-max 2` 效果最好 ([Unsloth Qwen3.6](https://unsloth.ai/docs/models/qwen3.6))。但 8GB 加 CPU 專家的參考配置實測後放棄了 speculative decoding ([numsu](https://github.com/numsu/Qwen3.6-A3B-8GB-llama.cpp))，原因可能是驗證批次仍要經過 CPU 上的專家。所以 MTP 列為「可試、預設關」。

## 輕量 harness 比重型 harness 更適合 8GB

harness 是包在模型外面的代理程式。它負責系統提示、工具定義、檔案讀寫和指令執行的迴圈，決定模型「怎麼做事」；推論引擎則決定模型「跑多快」。在 8GB 上，harness 的固定提示長度直接等於每次新對話要付的預填時間，所以挑 harness 和挑模型一樣重要。

**VS Code 內的 agent 有四個選擇。**

**Cline** 是本地路徑投入最多的擴充。官方文件要本地使用者開啟 **Settings → Features → Use Compact Prompt**，並把任務切小 ([Cline docs](https://docs.cline.bot/running-models-locally/overview))。它的原生 tool calling 只支援 Anthropic、OpenAI 等雲端供應商，本地供應商仍走 XML 文字協定 ([Cline v3.35](https://cline.bot/blog/cline-v3-35))。模型格式出錯時可能無限迴圈：有人回報 Qwen2.5-Coder-32B 輸出 JSON 工具呼叫，Cline 卻在等 XML ([cline #10843](https://github.com/cline/cline/issues/10843))。

**Roo Code** 已在 2026-04-21 宣布停止，repo 在 2026-05-15 封存，官方建議遷移到 Cline ([localaimaster](https://localaimaster.com/blog/roo-code-shutdown-local-alternative))。**Kilo Code** 是仍在維護的分支，能直接讀 `.roomodes` ([Kilo 遷移指南](https://kilo.ai/articles/roo-to-kilo-migration-guide))。

**Copilot Chat BYOK** 不需要 GitHub 帳號，可以完全離線使用。新的「Custom Endpoint」供應商支援 Chat Completions、Responses 或 Anthropic Messages，取代了已棄用的「OpenAI Compatible」和內建 Ollama 供應商。但它**不能用本地模型做 inline 補全** ([VS Code docs](https://code.visualstudio.com/docs/copilot/customization/language-models)；[VS Code blog](https://code.visualstudio.com/blogs/2026/06/18/byok-vscode))。還有一個要注意的已知問題：llama.cpp #22684 回報 Qwen3.5/3.6 的工具呼叫在 Copilot 客戶端下被塞進 `reasoning_content`，該 issue 已以 stale 關閉，沒有修正 ([llama.cpp #22684](https://github.com/ggml-org/llama.cpp/issues/22684))。

**Tab 補全**用 llama.vscode（直連 llama-server、Tab 接受建議，另附 Llama Agent）或 Continue（對話模型加 1.5B FIM 模型的組合）([llama.vscode](https://github.com/ggml-org/llama.vscode)；[insiderllm](https://insiderllm.com/guides/replace-github-copilot-local-llms-vscode/))。Twinny 已封存。

**終端機 agent 首推 OpenCode。** 用 logging proxy 實測，第一回合的負擔差異很大 ([systima.ai](https://systima.ai/blog/claude-code-vs-opencode-token-overhead))：

| Harness | 系統提示 | 工具定義 | 首回合合計 | 前綴快取 |
|---|---|---|---|---|
| OpenCode | 約 2k | 約 4.8k | **約 7k** | 前綴逐位元組相同，快取效果好 |
| Claude Code | 約 6.5k | 約 24k | **約 33k** | 實際使用中可膨脹到 51–75k ([XDA](https://www.xda-developers.com/claude-code-using-fifty-thousand-tokens-before-typed-prompt-fixed-it/)) |

兩者的任務通過率相同。在 8GB 預填只有數百 tok/s 的條件下，OpenCode 每次新對話少等大約一分鐘。

Claude Code 透過 llama-server 的 `/v1/messages` 也能正常運作，Raschka 的測試是 5/5。但它累積歷史的速度很快，一個例子裡輸入 578k、輸出只有 4.5k ([Raschka](https://magazine.sebastianraschka.com/p/using-local-coding-agents))。Codex CLI 用 `--oss` 可以接 Ollama 或 LM Studio。Pi 的系統提示不到 1k，適合極度精簡的場景 ([pinggy](https://pinggy.io/blog/best_open_source_cli_coding_agents/))。

**工具呼叫是本地方案最脆弱的環節。** Qwen3.5/3.6 用 XML 風格的 `qwen3_coder` 工具格式，在 llama.cpp 上反覆出過解析問題：工具呼叫被印在 thinking 區塊內 ([#20837](https://github.com/ggml-org/llama.cpp/issues/20837))，或 `<tool_call>` 前面有一段文字就讓所有結構化呼叫失效 ([openclaw #32916](https://github.com/openclaw/openclaw/issues/32916))。今天（2026-10-07）還有新 issue 回報 PEG 解析器把格式正確的 `<tool_call>` 判成一般內容，失敗率 30–50% ([#30078](https://github.com/ggml-org/llama.cpp/issues/30078))。Unsloth 已修正 chat template ([Unsloth Qwen3.6](https://unsloth.ai/docs/models/qwen3.6))。對策是用最新的 Unsloth GGUF，並**固定一個驗證過可用的 llama.cpp build**，不要盲目追最新版。

長 agent 對話還有一個 Qwen3.6 特有的問題：DeltaNet 的遞迴狀態可能讓 checkpoint 被拒，導致整段 prompt 重新預填。numsu repo 收錄了上游衍生的修正 ([numsu](https://github.com/numsu/Qwen3.6-A3B-8GB-llama.cpp))。這個修正是否已進主線未確認，所以 `--ctx-checkpoints` 和 `--cache-ram` 要保留。

**LM Studio Bionic 在這張圖裡的位置。** Bionic 是「LM Studio 給開放模型用的 agent」，一個獨立的桌面 app，建在 LM Studio 的 runtime 上，也能接零資料保留的雲端模型 ([lmstudio.ai/bionic](https://lmstudio.ai/bionic))。官方 changelog 上，「Bionic 1.1.7」（2026-10-01）附帶 llama.cpp 2.48.0 extension pack，1.1.3 加入 MTP ([LM Studio changelog](https://lmstudio.ai/changelog))。換句話說，Bionic 等於「harness + 引擎」打包在一起，角色和 OpenCode、Claude Code 相同。差別有兩點：它不在 VS Code 裡；它在 8GB 上的專家卸載能力受限於 LM Studio runtime 的設定。

Linux 版的狀態不明。第三方部落格說 1.1.2（9 月 8 日）已支援 Linux x64/ARM64，可用 `install.sh`、AppImage 或 .deb 安裝，NVIDIA 走 llama.cpp ([gyanaangan](https://gyanaangan.in/blog/lm-studio-bionic-finally-runs-on-linux-v112-install-guide-and-everything-else-new-in-11/))。但抓取到的官方頁面只顯示 Windows 下載。對你以 VS Code 為中心的工作流程，Bionic 適合當作「裝得起來就試試」的獨立 agent，不是主力。

## 兩台機器的可直接啟動配方

以下指令分三類標示：**【官方／他人實測配方】**是引用來源的原始寫法；**【推估起始值】**是依來源改寫給 8GB + 30GB 的起點，一定要經過下面的掃描步驟。

### 安裝 llama.cpp

兩台都可以直接下載 releases 頁的 Linux CUDA 12.8 或 13.4 預編譯檔。如果要自己編譯，一次編出同時支援兩張卡（sm_89 + sm_120）的版本，需要 nvcc ≥ 12.8：

```bash
# 自行編譯（同時支援 RTX 4060 Laptop 的 sm_89 與 RTX 5060 Ti 的 sm_120）
nvidia-smi --query-gpu=name,compute_cap,driver_version --format=csv   # noble 應顯示 12.0、驅動 ≥ 570
git clone https://github.com/ggml-org/llama.cpp && cd llama.cpp
cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="89;120" -DCMAKE_BUILD_TYPE=Release
cmake --build build -j --config Release
```

### 下載模型並掃描 `--n-cpu-moe`

**【推估起始值】**掃描方法改寫自 [openclawdc](https://openclawdc.com/blog/llama-cpp-moe-offload-flags-explained/)：

```bash
hf download unsloth/Qwen3.6-35B-A3B-GGUF --include "*UD-Q4_K_XL*" --local-dir ~/models/qwen3.6-35b-a3b
M=~/models/qwen3.6-35b-a3b/<實際檔名>.gguf   # 依下載結果填入
for n in 40 38 36 34 32 30; do
  ./build/bin/llama-bench -m "$M" -ngl 999 --n-cpu-moe $n -fa 1 -ctk q8_0 -ctv q8_0 \
    -b 2048 -ub 2048 -p 8192 -n 128 -t 16      # resolute 改 -t 12，再試 -t 8
done
# 另開一個終端機監看 VRAM：nvidia-smi --query-gpu=memory.used,memory.total --format=csv -l 1
```

取速度崩落前的最小 N。如果還要同時跑 FIM 模型，就再加 2–3 層。

### 主模型伺服器

**【推估起始值】**參數組合自 [llama-server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)、[Doctor-Shotgun](https://huggingface.co/blog/Doctor-Shotgun/llamacpp-moe-offload-guide)，取樣參數來自 [Unsloth Qwen3.6](https://unsloth.ai/docs/models/qwen3.6)：

```bash
./build/bin/llama-server -m "$M" --alias qwen3.6-35b-a3b \
  -ngl 999 --n-cpu-moe 36 --fit off \
  -c 65536 -ctk q8_0 -ctv q8_0 -fa on \
  -b 2048 -ub 2048 --no-mmap \
  -t 16 -np 1 --cache-ram 4096 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 --presence-penalty 0 \
  --host 127.0.0.1 --port 8080
# resolute：-t 12、-c 49152~65536；若要關閉 thinking 做快速問答：
#   --chat-template-kwargs '{"enable_thinking":false}' --temp 0.7 --top-p 0.8 --presence-penalty 1.5
# 想試 MTP：改用含 MTP head 的 GGUF（約多 1GB），加 --spec-type draft-mtp --spec-draft-n-max 2，並和關閉時比速度
```

各參數的理由：

- `--no-mmap`：有使用者回報這樣做讓系統 RAM 占用從 98% 降到 71%。
- `--cache-ram 4096`：預設是 8192 MiB，會和 30GB 的預算搶記憶體。
- `-np 1`：避免自動開多個 slot，把 KV 預算切碎。
- `--fit off`：讓調校結果可以重現。只想先求能跑的話，拿掉 `--n-cpu-moe` 和 `--fit off`，交給預設的 `--fit` 自動配置。
- 模型有 vision 部分：如果改用 `-hf` 下載，會連 mmproj（約 900MB）一起抓並占用 VRAM，需要加 `--no-mmproj` 關掉。

### 備案：gpt-oss-20b

**【官方配方，8GB 無公開速度數據】**出自 [Discussion #15396](https://github.com/ggml-org/llama.cpp/discussions/15396)：

```bash
llama-server -hf ggml-org/gpt-oss-20b-GGUF --ctx-size 32768 --jinja -ub 2048 -b 2048 --n-cpu-moe 16
```

### Tab 補全（FIM）伺服器

**【官方預設檔】**出自 [llama.vscode](https://github.com/ggml-org/llama.vscode)：

```bash
llama-server --fim-qwen-1.5b-default    # 8GB 以下的預設；llama.vscode 端點設成此伺服器的位址
```

這個 FIM 伺服器會吃掉約 1–2.5GB VRAM（推估）。如果補全不是一直在用，比較好的做法是只在寫程式時開，跑長 agent 任務時關掉，把 VRAM 還給主模型的專家。

**【推估】**resolute 另有一個選項：用 Vulkan 版 llama.cpp 把 1.5B 放到 Radeon 890M 內顯上跑。890M 跑 1B 模型約 551 tok/s 預填、67 tok/s 生成 ([localscore](https://www.localscore.ai/accelerator/721))，這樣 dGPU 的 VRAM 可以全部留給主模型。這個做法沒有人實際驗證過。

### 接上 harness

**【官方設定】**Claude Code 的寫法改自 [HF blog](https://huggingface.co/blog/ggml-org/anthropic-messages-api-in-llamacpp) 與 [LM Studio docs](https://lmstudio.ai/docs/integrations/claude-code)。OpenCode 的設定格式依其文件慣例，請以當前版本文件為準：

```bash
# Claude Code（主模型 context 至少 64K）
export ANTHROPIC_BASE_URL=http://127.0.0.1:8080
export ANTHROPIC_AUTH_TOKEN=local
export CLAUDE_CODE_ATTRIBUTION_HEADER=0
claude --model qwen3.6-35b-a3b
```

OpenCode 設定檔 `~/.config/opencode/opencode.json`：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "llamacpp": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "llama.cpp (local)",
      "options": { "baseURL": "http://127.0.0.1:8080/v1" },
      "models": { "qwen3.6-35b-a3b": { "name": "Qwen3.6-35B-A3B" } }
    }
  }
}
```

VS Code 這邊有兩種接法：

- **Cline**：選 OpenAI Compatible，Base URL 填 `http://127.0.0.1:8080/v1`，然後開啟 Compact Prompt。
- **Copilot Chat**：選「Custom Endpoint」供應商，指向同一個位址。

### 兩台機器各自要確認的事

resolute 有三件事：

- 用 `nvidia-smi -q -d POWER` 確認功耗上限沒有卡在 60W 附近，必要時執行 `sudo systemctl enable --now nvidia-powerd`。
- 確認桌面由內顯驅動，`nvidia-smi` 裡不應該看到 gnome-shell 占用 dGPU。
- HX 370 是 Zen5 加 Zen5c 共 12 核，`-t 12` 和 `-t 8` 要各測一次。

noble 有兩件事：

- 如果螢幕接在 5060 Ti 上，桌面會吃掉部分 VRAM。改接主機板輸出（9950X 有內顯）可以多放一兩層專家（推估）。
- `-t 16` 對應 16 個實體核心。來源建議用上全部核心算專家 ([Discussion #21112](https://github.com/ggml-org/llama.cpp/discussions/21112))。

## 結論

這個問題的答案不是單一模型，而是一個分工原則：**讓 8GB VRAM 專門放「每個 token 都會用到」的東西（attention、shared expert、KV、FIM 小模型），讓 RAM 頻寬去扛「偶爾才用到」的 routed experts。** MoE 加上混合線性注意力，讓 35B 等級的程式代理在消費級筆電上第一次有了實用速度。但瓶頸也因此從「生成多快」轉到「預填多快」，所以 harness 的提示長度和前綴快取命中率，現在和模型分數一樣是選型條件。選 OpenCode 而不是 Claude Code，在你的硬體上省下的等待時間，可能比從 Q4 換成 Q6 多出的品質更有價值。

接下來最有價值的一步，是在 resolute 和 noble 上各跑一輪 `llama-bench` 掃描（`--n-cpu-moe` × `-ub` × KV 型別），補上目前所有推估值背後缺的那一塊實測。附帶幾個值得留意的變數：llama.cpp 的滾動 build 隨時可能修好或弄壞 Qwen 的工具呼叫解析；MTP 在 CPU 專家卸載下的實際效益還沒有人量過；Bionic 的 Linux 版一旦正式出現，LM Studio 系的一體化方案就可能成為「省事版」的合理選項。
