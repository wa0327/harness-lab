# n-cpu-moe 掃描 resolute 2026-10-07 21:18:44

- GPU: NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB, 610.57.04
- llama.cpp: b11469 (CUDA 13.4)
- 模型: Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf
- 參數: -b 2048 -ub 2048 -ctk/-ctv q8_0 -lm auto -t 12 -p 8192 -n 128

== --n-cpu-moe 35
| model                          |       size |     params | backend    | ngl |  n_cpu_moe | n_ubatch | type_k | type_v |  fa |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ---------: | -------: | -----: | -----: | --: | --------------: | -------------------: |
| qwen35moe 35B.A3B Q4_K - Medium |  20.81 GiB |    34.66 B | CUDA       | 999 |         35 |     2048 |   q8_0 |   q8_0 |   1 |          pp8192 |        948.86 ± 2.91 |
| qwen35moe 35B.A3B Q4_K - Medium |  20.81 GiB |    34.66 B | CUDA       | 999 |         35 |     2048 |   q8_0 |   q8_0 |   1 |           tg128 |         45.20 ± 0.18 |

build: ad2156533 (11469)

== --n-cpu-moe 34
| model                          |       size |     params | backend    | ngl |  n_cpu_moe | n_ubatch | type_k | type_v |  fa |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ---------: | -------: | -----: | -----: | --: | --------------: | -------------------: |
| qwen35moe 35B.A3B Q4_K - Medium |  20.81 GiB |    34.66 B | CUDA       | 999 |         34 |     2048 |   q8_0 |   q8_0 |   1 |          pp8192 |        946.35 ± 3.94 |
| qwen35moe 35B.A3B Q4_K - Medium |  20.81 GiB |    34.66 B | CUDA       | 999 |         34 |     2048 |   q8_0 |   q8_0 |   1 |           tg128 |         45.25 ± 0.02 |

build: ad2156533 (11469)

== --n-cpu-moe 33
| model                          |       size |     params | backend    | ngl |  n_cpu_moe | n_ubatch | type_k | type_v |  fa |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ---------: | -------: | -----: | -----: | --: | --------------: | -------------------: |
| qwen35moe 35B.A3B Q4_K - Medium |  20.81 GiB |    34.66 B | CUDA       | 999 |         33 |     2048 |   q8_0 |   q8_0 |   1 |          pp8192 |        953.89 ± 1.55 |
| qwen35moe 35B.A3B Q4_K - Medium |  20.81 GiB |    34.66 B | CUDA       | 999 |         33 |     2048 |   q8_0 |   q8_0 |   1 |           tg128 |         45.26 ± 0.48 |

build: ad2156533 (11469)

