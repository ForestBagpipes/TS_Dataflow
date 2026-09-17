#!/usr/bin/env bash
# 把 figure/*.pdf 渲染成 _preview_*.png, 用于人工核对版面。
# 预览图是临时产物, 不参与论文编译。
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TLROOT="${TLROOT:-/d/texlive/2025}"
GS="$TLROOT/tlpkg/tlgs/bin/gswin64c.exe"
[ -x "$GS" ] || GS="$(command -v gs)"

if [ -z "${GS_LIB:-}" ]; then
  TLGS="$(cygpath -w "$TLROOT/tlpkg/tlgs" 2>/dev/null || printf '%s' "$TLROOT/tlpkg/tlgs")"
  GSFONTS="$(cygpath -w "$HERE/gsfonts" 2>/dev/null || printf '%s' "$HERE/gsfonts")"
  export GS_LIB="$GSFONTS;$TLGS\\Resource\\Init;$TLGS\\lib;$TLGS\\kanji;$TLGS\\Resource\\Font;$TLGS\\Resource\\CMap;$TLGS\\Resource\\Encoding;$TLGS\\Resource\\ColorSpace;$TLGS\\Resource\\Decoding;$TLGS\\Resource\\SubstCID;$TLGS\\Resource\\CIDFont;$TLGS\\Resource\\CIDFSubst;$TLGS\\Resource\\IdiomSet"
  export GS_FONTPATH="$(cygpath -w "$TLROOT/texmf-dist/fonts/type1/urw/helvetic" 2>/dev/null || printf '%s' "$TLROOT/texmf-dist/fonts/type1/urw/helvetic")"
fi

for pdf in "$HERE"/*.pdf; do
  [ -e "$pdf" ] || continue
  out="$HERE/_preview_$(basename "${pdf%.pdf}").png"
  "$GS" -q -dNOPAUSE -dBATCH -dEPSCrop -r200 -dTextAlphaBits=4 -dGraphicsAlphaBits=4 \
        -sDEVICE=png16m -sOutputFile="$(cygpath -w "$out")" "$(cygpath -w "$pdf")"
  echo "  $(basename "$out")"
done
