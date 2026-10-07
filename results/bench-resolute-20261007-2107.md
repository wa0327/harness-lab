# n-cpu-moe 掃描 resolute 2026-10-07 21:07:39

- GPU: NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB, 610.57.04
- llama.cpp: b11469 (CUDA 13.4)
- 模型: Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf
- 參數: -b 2048 -ub 2048 -ctk/-ctv q8_0 -lm auto -t 12 -p 8192 -n 128

== --n-cpu-moe 40
| model                          |       size |     params | backend    | ngl |  n_cpu_moe | n_ubatch | type_k | type_v |  fa |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ---------: | -------: | -----: | -----: | --: | --------------: | -------------------: |
| qwen35moe 35B.A3B Q4_K - Medium |  20.81 GiB |    34.66 B | CUDA       | 999 |         40 |     2048 |   q8_0 |   q8_0 |   1 |          pp8192 |        866.82 ± 2.59 |
| qwen35moe 35B.A3B Q4_K - Medium |  20.81 GiB |    34.66 B | CUDA       | 999 |         40 |     2048 |   q8_0 |   q8_0 |   1 |           tg128 |         42.17 ± 0.19 |

build: ad2156533 (11469)

== --n-cpu-moe 36
| model                          |       size |     params | backend    | ngl |  n_cpu_moe | n_ubatch | type_k | type_v |  fa |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ---------: | -------: | -----: | -----: | --: | --------------: | -------------------: |
| qwen35moe 35B.A3B Q4_K - Medium |  20.81 GiB |    34.66 B | CUDA       | 999 |         36 |     2048 |   q8_0 |   q8_0 |   1 |          pp8192 |        925.41 ± 4.42 |
| qwen35moe 35B.A3B Q4_K - Medium |  20.81 GiB |    34.66 B | CUDA       | 999 |         36 |     2048 |   q8_0 |   q8_0 |   1 |           tg128 |         44.05 ± 0.28 |

build: ad2156533 (11469)

== --n-cpu-moe 32
| model                          |       size |     params | backend    | ngl |  n_cpu_moe | n_ubatch | type_k | type_v |  fa |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ---------: | -------: | -----: | -----: | --: | --------------: | -------------------: |
失敗（多半是 VRAM 不足），停止往下掃
