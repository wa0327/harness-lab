#!/usr/bin/env bash
# 簽入路線 2 的前半：在臨時 index 上組出「BASE＋本 session 的改動」的 tree。
# 主 index、工作區、HEAD 都不碰；組好的 tree 核對過，再由 land.sh 簽入。
#
# 用法：build-tree.sh [-p <patch>]... [--] [<整檔路徑>...]
#   -p <patch>  只含本 session hunk 的 patch，以 HEAD 為底（產生方式見 SKILL.md）
#   <整檔路徑>   改動整個出自本 session 的檔案，含新檔與刪檔
#
# 輸出 BASE、TREE 兩個雜湊（land.sh 要用），以及兩份差異：
#   BASE→TREE    將簽入的內容，必須只有本 session 的改動
#   TREE→工作區  這些路徑上留著不簽的，必須只有別的 session 的改動
set -euo pipefail
export GIT_LITERAL_PATHSPECS=1

patches=()
while [[ $# -gt 0 ]]; do
  case $1 in
    -p) patches+=("$(realpath "$2")"); shift 2 ;;
    --) shift; break ;;
    *) break ;;
  esac
done

cd "$(git rev-parse --show-toplevel)"
base=$(git rev-parse --verify HEAD)
# 臨時 index 放 .git/ 裡：在專案目錄內、又不會變成 untracked
idx="$(git rev-parse --absolute-git-dir)/commit-skill-$$.idx"
trap 'rm -f "$idx"' EXIT

GIT_INDEX_FILE=$idx git read-tree "$base"
for p in ${patches[@]+"${patches[@]}"}; do
  GIT_INDEX_FILE=$idx git apply --cached --recount "$p"
done
if [[ $# -gt 0 ]]; then
  GIT_INDEX_FILE=$idx git add -A -- "$@"
fi
tree=$(GIT_INDEX_FILE=$idx git write-tree)

echo "BASE=$base"
echo "TREE=$tree"
if [[ $(git rev-parse "$base^{tree}") == "$tree" ]]; then
  echo "TREE 與 BASE 相同：沒有要簽的東西" >&2
  exit 1
fi

echo
echo "===== 將簽入（BASE→TREE）"
git diff --stat "$base" "$tree"
git diff "$base" "$tree"

# 工作區的檔案逐一和 TREE 比；新檔還沒被追蹤，git diff <tree> 看不到，所以直接 diff 內容
echo
echo "===== 這些路徑留在工作區沒簽的（TREE→工作區）"
blobf="$idx.blob"
trap 'rm -f "$idx" "$blobf"' EXIT
git diff --name-only -z "$base" "$tree" | while IFS= read -r -d '' p; do
  if git cat-file -e "$tree:$p" 2>/dev/null; then
    if [[ -e $p ]]; then
      git cat-file blob "$tree:$p" > "$blobf"
      diff -u --label "TREE:$p" --label "工作區:$p" "$blobf" "$p" || true
    else
      echo "$p：TREE 有、工作區已刪除"
    fi
  elif [[ -e $p ]]; then
    echo "$p：TREE 刪除、工作區仍在"
  fi
done
