#!/usr/bin/env bash
# 簽入路線 2 的後半：把使用者複核過的 TREE 簽成 commit，再讓主 index 跟上新 HEAD。
#
# 用法：land.sh <BASE> <TREE> <commit message 檔>
#       land.sh --sync <BASE> <TREE>     只重做主 index 同步（上次被 index.lock 擋下時）
#   BASE、TREE 照抄 build-tree.sh 的輸出
#
# HEAD 只在仍是 BASE 時才換（update-ref 的 compare-and-swap）；別的 session 先簽了就整個
# 失敗、什麼都沒動，從 build-tree.sh 重做。
# 主 index 逐檔處理，別人 staged 的內容一律保留：
#   index＝BASE        → 換成 TREE（沒有別人 staged 的，最常見）
#   index＝TREE        → 已經對了
#   三者都在、內容不同 → 三方合併（index, BASE, TREE），乾淨才寫入
#   其他（合併衝突、別人 staged 刪除等）→ 該檔不動，回報
set -euo pipefail
export GIT_LITERAL_PATHSPECS=1

usage() { echo "用法：land.sh <BASE> <TREE> <commit message 檔> | land.sh --sync <BASE> <TREE>" >&2; exit 2; }
sync_only=0
if [[ ${1-} == --sync ]]; then sync_only=1; shift; [[ $# -eq 2 ]] || usage
else [[ $# -eq 3 ]] || usage; msg=$(realpath "$3"); fi
cd "$(git rev-parse --show-toplevel)"
base=$(git rev-parse --verify "$1^{commit}")
tree=$(git rev-parse --verify "$2^{tree}")

if [[ $sync_only -eq 0 ]]; then
  commit=$(git commit-tree "$tree" -p "$base" -F "$msg")
  if ! git update-ref -m "commit: $(head -n1 "$msg")" HEAD "$commit" "$base"; then
    echo "HEAD 已不是 BASE（別的 session 剛簽入）：沒有簽入，從 build-tree.sh 重做並重新複核" >&2
    exit 1
  fi
  echo "已簽入 $(git log -1 --format='%h %s' "$commit")"
fi

# 主 index 被別的 git 指令鎖住時，update-index 會失敗；commit 已經簽了，只補同步
trap_lock() {
  echo "主 index 同步中斷（多半是 index.lock）：稍等後跑 land.sh --sync $base $tree，不要刪 lock 檔" >&2
}
trap 'trap_lock' ERR

# 回傳 "<mode> <blob>"；不存在時回空字串
entry_in_tree() { git ls-tree "$1" -- "$2" | awk '{print $1, $3}'; }

mergef="$(git rev-parse --absolute-git-dir)/commit-skill-$$.merge"
trap 'rm -f "$mergef"' EXIT
left=0
while IFS= read -r -d '' p; do
  b=$(entry_in_tree "$base" "$p")
  n=$(entry_in_tree "$tree" "$p")
  stages=$(git ls-files -s -- "$p")
  if [[ $stages == *$'\n'* || ( -n $stages && $(awk '{print $3}' <<<"$stages") != 0 ) ]]; then
    echo "主 index 不動：$p 在主 index 是未合併狀態"; left=1; continue
  fi
  i=""
  [[ -n $stages ]] && i=$(awk '{print $1, $2}' <<<"$stages")

  if [[ $i == "$n" ]]; then
    continue
  elif [[ $i == "$b" ]]; then
    if [[ -z $n ]]; then
      git update-index --force-remove -- "$p"
    else
      git update-index --add --cacheinfo "${n% *},${n#* },$p"
    fi
  elif [[ -n $i && -n $b && -n $n ]]; then
    if git merge-file -p --object-id "${i#* }" "${b#* }" "${n#* }" > "$mergef"; then
      # mode：本 session 改了就用新的，否則保留主 index 的（可能是別人 staged 的 chmod）
      if [[ ${n% *} != "${b% *}" ]]; then mode=${n% *}; else mode=${i% *}; fi
      blob=$(git hash-object -w --no-filters "$mergef")
      if [[ "$mode $blob" != "$i" ]]; then
        git update-index --cacheinfo "$mode,$blob,$p"
        echo "主 index 合併：$p（保留別人 staged 的部分）"
      fi
    else
      echo "主 index 不動：$p 別人 staged 的內容與本次簽入重疊"; left=1
    fi
  else
    echo "主 index 不動：$p 別人 staged 了新增或刪除整檔"; left=1
  fi
done < <(git diff --name-only -z --no-renames "$base" "$tree")

if [[ $left -ne 0 ]]; then
  echo "上面標「不動」的檔案，git status 會把本次簽入的改動顯示成 staged 的反向改動；"
  echo "那是別人 staged 的內容與本次重疊，交給使用者處理，不要自己 reset。"
fi
