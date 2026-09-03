#!/usr/bin/env bash
# Batch-fetch Markdown source pages listed in an llms.txt index.
#
# Usage: fetch_docs.sh <llms.txt URL or local file> <out_dir> [parallelism]
#
# Produces:
#   <out_dir>/pages/<slug>.md   one file per page (fetched from URL + ".md", falling back to the raw URL)
#   <out_dir>/index.tsv         title \t url \t local file \t http status
#   <out_dir>/llms.txt          the index itself
set -uo pipefail

SRC="${1:?llms.txt URL or file}"
OUT="${2:?output directory}"
PAR="${3:-8}"
mkdir -p "$OUT/pages"

if [[ "$SRC" =~ ^https?:// ]]; then
  curl -sSL --max-time 30 "$SRC" -o "$OUT/llms.txt" || { echo "failed to fetch $SRC" >&2; exit 1; }
  BASE="$(printf '%s' "$SRC" | sed -E 's#^(https?://[^/]+).*#\1#')"
else
  cp "$SRC" "$OUT/llms.txt"
  BASE=""
fi

# "[title](url)" pairs -> links.tsv (title \t absolute url), skipping non-page assets.
grep -oE '\[[^]]*\]\([^)]+\)' "$OUT/llms.txt" \
  | sed -E 's/^\[([^]]*)\]\(([^)]+)\)$/\1\t\2/' \
  | awk -F'\t' -v base="$BASE" '
      { url=$2; if (url !~ /^https?:\/\//) url = base url;
        if (url ~ /\.(json|yaml|yml|png|jpg|jpeg|gif|svg|xml|zip|pdf)$/) next;
        print $1 "\t" url }' \
  | sort -u -t$'\t' -k2,2 > "$OUT/links.tsv"

n=$(wc -l < "$OUT/links.tsv" | tr -d ' ')
echo "found $n page links; fetching with parallelism $PAR" >&2

fetch_one() {   # $1 = url ; prints: url \t local file \t http status
  local url="$1" slug target code
  slug="$(printf '%s' "$url" | sed -E 's#^https?://[^/]+/##; s#\.md$##; s#[^A-Za-z0-9._-]+#_#g')"
  [[ -z "$slug" ]] && slug="index"
  target="$url"; [[ "$target" != *.md ]] && target="${target%/}.md"
  code=$(curl -sSL --max-time 30 -o "$OUT/pages/$slug.md" -w '%{http_code}' "$target" 2>/dev/null || echo 000)
  if [[ "$code" != "200" ]]; then
    code=$(curl -sSL --max-time 30 -o "$OUT/pages/$slug.md" -w '%{http_code}' "$url" 2>/dev/null || echo 000)
  fi
  printf '%s\t%s\t%s\n' "$url" "pages/$slug.md" "$code"
}
export -f fetch_one
export OUT

cut -f2 "$OUT/links.tsv" \
  | xargs -P "$PAR" -I{} bash -c 'fetch_one "$1"' _ {} \
  > "$OUT/fetched.tsv"

# Join titles back in: index.tsv = title \t url \t file \t status
awk -F'\t' 'NR==FNR { title[$2]=$1; next } { print title[$1] "\t" $1 "\t" $2 "\t" $3 }' \
  "$OUT/links.tsv" "$OUT/fetched.tsv" | sort -t$'\t' -k2,2 > "$OUT/index.tsv"
rm -f "$OUT/fetched.tsv"

ok=$(awk -F'\t' '$4=="200"' "$OUT/index.tsv" | wc -l | tr -d ' ')
echo "done: $ok/$n pages fetched OK -> $OUT/pages ; index at $OUT/index.tsv" >&2
awk -F'\t' '$4!="200"{print "  non-200: " $4 "  " $2}' "$OUT/index.tsv" | head -20 >&2
