# n-cpu-moe 掃描 resolute 2026-10-07 21:21:33

- GPU: NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB, 610.57.04
- llama.cpp: b11469 (CUDA 13.4)
- 模型: Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf
- 參數: -b 4096 -ub 4096 -ctk/-ctv q8_0 -lm auto -t 12 -p 8192 -n 128

== --n-cpu-moe 37
| model                          |       size |     params | backend    | ngl |  n_cpu_moe | n_batch | n_ubatch | type_k | type_v |  fa |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | ---------: | ------: | -------: | -----: | -----: | --: | --------------: | -------------------: |
[New LWP 74974]
[New LWP 74973]
[New LWP 74972]
[New LWP 74968]

This GDB supports auto-downloading debuginfo from the following URLs:
  <https://debuginfod.ubuntu.com>
Enable debuginfod for this session? (y or [n]) [answered N; input not from terminal]
Debuginfod has been disabled.
To make this setting permanent, add 'set debuginfod enabled off' to .gdbinit.
[Thread debugging using libthread_db enabled]
Using host libthread_db library "/usr/lib/x86_64-linux-gnu/libthread_db.so.1".
__syscall_cancel_arch () at ../sysdeps/unix/sysv/linux/x86_64/syscall_cancel.S:56
#0  __syscall_cancel_arch () at ../sysdeps/unix/sysv/linux/x86_64/syscall_cancel.S:56
56	in ../sysdeps/unix/sysv/linux/x86_64/syscall_cancel.S
#1  0x000075f3f00a039c in __internal_syscall_cancel (a1=<optimized out>, a2=<optimized out>, a3=<optimized out>, a4=<optimized out>, a5=0, a6=0, nr=61) at ./nptl/cancellation.c:49
#2  __syscall_cancel (a1=<optimized out>, a2=<optimized out>, a3=<optimized out>, a4=<optimized out>, a5=a5@entry=0, a6=a6@entry=0, nr=61) at ./nptl/cancellation.c:75
75	in ./nptl/cancellation.c
#3  0x000075f3f011cacf in __GI___wait4 (pid=<optimized out>, stat_loc=<optimized out>, options=<optimized out>, usage=<optimized out>) at ../sysdeps/unix/sysv/linux/wait4.c:30
#4  0x000075f3f03479b3 in ggml_print_backtrace () from /home/jack/repos/harness-lab/vendor/llama.cpp/current/libggml-base.so.0
#5  0x000075f3f0347b5b in ggml_abort () from /home/jack/repos/harness-lab/vendor/llama.cpp/current/libggml-base.so.0
#6  0x000075f3e5508287 in ggml_cuda_error(char const*, char const*, char const*, int, char const*) () from /home/jack/repos/harness-lab/vendor/llama.cpp/b11469/libggml-cuda.so
#7  0x000075f3e55231c3 in ggml_cuda_pool_vmm::alloc(unsigned long, unsigned long*) () from /home/jack/repos/harness-lab/vendor/llama.cpp/b11469/libggml-cuda.so
#8  0x000075f3e556a4cb in ggml_cuda_mul_mat_q(ggml_backend_cuda_context&, ggml_tensor const*, ggml_tensor const*, ggml_tensor const*, ggml_tensor*) () from /home/jack/repos/harness-lab/vendor/llama.cpp/b11469/libggml-cuda.so
#9  0x000075f3e551f2db in ggml_backend_cuda_graph_compute(ggml_backend*, ggml_cgraph*) () from /home/jack/repos/harness-lab/vendor/llama.cpp/b11469/libggml-cuda.so
#10 0x000075f3f0366164 in ggml_backend_sched_graph_compute_async () from /home/jack/repos/harness-lab/vendor/llama.cpp/current/libggml-base.so.0
#11 0x000075f3ef6126db in llama_context::graph_compute(ggml_cgraph*, bool) () from /home/jack/repos/harness-lab/vendor/llama.cpp/current/libllama.so.0
#12 0x000075f3ef616146 in llama_context::process_ubatch(llama_ubatch const&, llm_graph_type, llama_memory_context_i*, ggml_status&) () from /home/jack/repos/harness-lab/vendor/llama.cpp/current/libllama.so.0
#13 0x000075f3ef61e608 in llama_context::decode(llama_batch_ext const&) () from /home/jack/repos/harness-lab/vendor/llama.cpp/current/libllama.so.0
#14 0x000075f3f07a8473 in test_prompt(llama_context*, int, int, int) () from /home/jack/repos/harness-lab/vendor/llama.cpp/current/libllama-bench-impl.so
#15 0x000075f3f07b78c8 in llama_bench(int, char**) () from /home/jack/repos/harness-lab/vendor/llama.cpp/current/libllama-bench-impl.so
#16 0x000075f3f002a601 in __libc_start_call_main (main=main@entry=0x5a9208693270 <main>, argc=argc@entry=29, argv=argv@entry=0x7ffcfee459b8) at ../sysdeps/nptl/libc_start_call_main.h:59
#17 0x000075f3f002a718 in __libc_start_main_impl (main=0x5a9208693270 <main>, argc=29, argv=0x7ffcfee459b8, init=<optimized out>, fini=<optimized out>, rtld_fini=<optimized out>, stack_end=0x7ffcfee459a8) at ../csu/libc-start.c:360
#18 0x00005a92086932a5 in _start ()
[Inferior 1 (process 74966) detached]
失敗（多半是 VRAM 不足），停止往下掃
