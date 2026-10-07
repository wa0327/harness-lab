#!/usr/bin/env bash
# 下載 llama.cpp 官方預編譯 CUDA 版（含 cudart，不需安裝 CUDA toolkit）
# 用法：scripts/install-llama.sh [build]   例：scripts/install-llama.sh b11469
set -euo pipefail
source "$(dirname "$0")/../env.sh"

build="${1:-$LLAMA_BUILD}"
dest="$LAB_DIR/vendor/llama.cpp/$build"
base="https://github.com/ggml-org/llama.cpp/releases/download/$build"

if [[ -x "$dest/llama-server" ]]; then
  echo "已安裝：$dest"
else
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  for f in "llama-$build-bin-ubuntu-cuda-$LLAMA_CUDA-x64.tar.gz" \
           "cudart-llama-$build-bin-ubuntu-cuda-$LLAMA_CUDA-x64.tar.gz"; do
    echo "下載 $f"
    curl -fL --progress-bar -o "$tmp/$f" "$base/$f"
    mkdir -p "$tmp/x"
    tar -xzf "$tmp/$f" -C "$tmp/x"
  done
  # 壓縮檔內的目錄層級不固定，以 llama-server 所在目錄為準
  bindir="$(dirname "$(find "$tmp/x" -type f -name llama-server | head -1)")"
  mkdir -p "$dest"
  cp -a "$bindir"/. "$dest"/
  # cudart 的 .so 若落在其他目錄，也一併放進來
  find "$tmp/x" -name '*.so*' -not -path "$bindir/*" -exec cp -a {} "$dest"/ \;
fi

ln -sfn "$build" "$LAB_DIR/vendor/llama.cpp/current"
LD_LIBRARY_PATH="$dest${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$dest/llama-server" --version
echo "current -> $build"
