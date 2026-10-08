#!/usr/bin/env bash
# 下載 llama.cpp 官方預編譯 CUDA 版（含 cudart，不需安裝 CUDA toolkit）
# 用法：scripts/install-llama.sh [build]   例：scripts/install-llama.sh b11469
set -euo pipefail
source "$(dirname "$0")/../env.sh"

build="${1:-$LLAMA_BUILD}"
[[ -n "$build" ]] || { echo "沒有指定 build" >&2; exit 2; }
dest="$LAB_DIR/vendor/llama.cpp/$build"
base="https://github.com/ggml-org/llama.cpp/releases/download/$build"

# 目錄只用 build 命名，裝的是哪個 CUDA 版本記在 .cuda；換了 LLAMA_CUDA（例如驅動太舊改 12.8）重跑時才會重新下載。
# 這個檔加入前裝的沒有記錄，視為當時的預設 13.4
installed_cuda="$(cat "$dest/.cuda" 2>/dev/null || echo 13.4)"
if [[ -x "$dest/llama-server" && "$installed_cuda" == "$LLAMA_CUDA" ]]; then
  echo "已安裝：$dest（CUDA $LLAMA_CUDA）"
else
  if [[ -e "$dest" ]]; then
    echo "$dest 是 CUDA $installed_cuda 版，改裝 CUDA $LLAMA_CUDA 版"
    rm -rf "$dest"
  fi
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
  echo "$LLAMA_CUDA" > "$dest/.cuda"
fi

ln -sfn "$build" "$LAB_DIR/vendor/llama.cpp/current"
LD_LIBRARY_PATH="$dest${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$dest/llama-server" --version
echo "current -> $build"
