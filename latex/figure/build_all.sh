#!/usr/bin/env bash
# 一步生成全部图源并转出 PDF:
#   python build_figures.py   -> *.eps / *.pptx
#   bash   build_pdf.sh       -> *.pdf (ghostscript)
#   bash   preview.sh         -> _preview_*.png (人工检查用)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PY:-C:/Users/lzfd/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe}"
# 必须用 cygpath -w: 直接传 /f/... 给原生 python.exe 会被 MSYS 误转成 F:\f\...
"$PY" "$(cygpath -w "$HERE/build_figures.py")"
bash "$HERE/build_pdf.sh"
