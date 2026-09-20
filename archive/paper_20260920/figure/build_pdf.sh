#!/usr/bin/env bash
# 将 figure/ 下的 .eps 批量转为 pdflatex 可直接使用的 .pdf。
# .eps 是可编辑图源（Illustrator/Inkscape/Word 可打开），.pdf 是由它派生的编译产物。
# 两者必须始终同步：改图后先跑 build_figures.py，再跑本脚本。
#
# 依赖：TeX Live 自带的 ghostscript（tlgs）。若系统已装 ghostscript 可忽略 GS_LIB。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# TeX Live 的 tlgs 不自带 Nimbus 字体，需用 gsfonts/Fontmap 指到 texmf 里的 URW 克隆字体。
TLROOT="${TLROOT:-/d/texlive/2025}"
URWFONTS="$TLROOT/texmf-dist/fonts/type1/urw"
GSFONTPATH="$(cygpath -w "$URWFONTS/helvetic" 2>/dev/null || printf '%s' "$URWFONTS/helvetic")"

if command -v gswin64c >/dev/null 2>&1 && [ -z "${GS_LIB:-}" ]; then
  GS="gswin64c"
elif [ -x "$TLROOT/tlpkg/tlgs/bin/gswin64c.exe" ]; then
  GS="$TLROOT/tlpkg/tlgs/bin/gswin64c.exe"
  TLGS="$(cygpath -w "$TLROOT/tlpkg/tlgs" 2>/dev/null || printf '%s' "$TLROOT/tlpkg/tlgs")"
  GSFONTS="$(cygpath -w "$HERE/gsfonts" 2>/dev/null || printf '%s' "$HERE/gsfonts")"
  export GS_LIB="$GSFONTS;$TLGS\\Resource\\Init;$TLGS\\lib;$TLGS\\kanji;$TLGS\\Resource\\Font;$TLGS\\Resource\\CMap;$TLGS\\Resource\\Encoding;$TLGS\\Resource\\ColorSpace;$TLGS\\Resource\\Decoding;$TLGS\\Resource\\SubstCID;$TLGS\\Resource\\CIDFont;$TLGS\\Resource\\CIDFSubst;$TLGS\\Resource\\IdiomSet"
  export GS_FONTPATH="$GSFONTPATH"
else
  GS="$(command -v gs || true)"
fi

if [ -z "$GS" ]; then
  echo "ERROR: ghostscript not found; cannot convert eps -> pdf" >&2
  exit 1
fi

# Windows 版 ghostscript 不认识 MSYS 风格路径（/f/...），需要转成 F:\...
winpath() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else printf '%s' "$1"; fi
}

n=0
for eps in "$HERE"/*.eps; do
  [ -e "$eps" ] || continue
  pdf="${eps%.eps}.pdf"
  "$GS" -q -dNOPAUSE -dBATCH -dEPSCrop -dSAFER \
        -sDEVICE=pdfwrite -dPDFSETTINGS=/prepress \
        -sOutputFile="$(winpath "$pdf")" "$(winpath "$eps")"
  echo "  $(basename "$eps") -> $(basename "$pdf")"
  n=$((n + 1))
done
echo "converted $n figure(s)"
