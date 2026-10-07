# n-cpu-moe 掃描 resolute 2026-10-07 21:20:31

- GPU: NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB, 610.57.04
- llama.cpp: b11469 (CUDA 13.4)
- 模型: Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf
- 參數: -b 4096 -ub 4096 -ctk/-ctv q8_0 -lm auto -t 12 -p 8192 -n 128

== --n-cpu-moe 40
| model                          |       size |     params | backend    | ngl |  n_cpu_moe | n_batch | n_ubatch | type_k | type_v |  fa |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ---------: | ------: | -------: | -----: | -----: | --: | --------------: | -------------------: |
| qwen35moe 35B.A3B Q4_K - Medium |  20.81 GiB |    34.66 B | CUDA       | 999 |         40 |    4096 |     4096 |   q8_0 |   q8_0 |   1 |          pp8192 |       1161.22 ± 4.95 |
| qwen35moe 35B.A3B Q4_K - Medium |  20.81 GiB |    34.66 B | CUDA       | 999 |         40 |    4096 |     4096 |   q8_0 |   q8_0 |   1 |           tg128 |         42.75 ± 0.19 |

build: ad2156533 (11469)

== --n-cpu-moe 38
| model                          |       size |     params | backend    | ngl |  n_cpu_moe | n_batch | n_ubatch | type_k | type_v |  fa |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ---------: | ------: | -------: | -----: | -----: | --: | --------------: | -------------------: |
| qwen35moe 35B.A3B Q4_K - Medium |  20.81 GiB |    34.66 B | CUDA       | 999 |         38 |    4096 |     4096 |   q8_0 |   q8_0 |   1 |          pp8192 |       1167.09 ± 1.20 |
| qwen35moe 35B.A3B Q4_K - Medium |  20.81 GiB |    34.66 B | CUDA       | 999 |         38 |    4096 |     4096 |   q8_0 |   q8_0 |   1 |           tg128 |         43.42 ± 0.35 |

build: ad2156533 (11469)

