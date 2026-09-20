#!/usr/bin/env bash
# Rebuild the v4.7 manuscript from the v4.6 template and the recorded results.
#
# Every pass is a separate script so a failed anchor names itself, and the build
# stops there instead of carrying on with a half-edited file.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="/d/texlive/2025/bin/windows:$PATH"

for pass in make_v47.py make_v47_figs.py make_v47_pages.py \
            make_v47_tighten.py make_v47_evidence.py make_v47_fit.py; do
  if ! python "$pass" > "/tmp/${pass}.out" 2>&1; then
    echo "BUILD STOPPED in $pass"
    tail -5 "/tmp/${pass}.out"
    exit 1
  fi
  echo "ok  $pass"
done

rm -f IntroActTS_20260919_v47_filled.tex
python fill_v47.py IntroActTS_20260919_v47.tex IntroActTS_20260919_v47_filled.tex \
  | grep -E '"filled"|"remaining"|complete|PARTIAL'

J="${1:-v47_build}"
pdflatex -interaction=nonstopmode -jobname="$J" IntroActTS_20260919_v47_filled.tex > /dev/null 2>&1 || true
bibtex "$J" > /dev/null 2>&1 || true
pdflatex -interaction=nonstopmode -jobname="$J" IntroActTS_20260919_v47_filled.tex > /dev/null 2>&1 || true
pdflatex -interaction=nonstopmode -jobname="$J" IntroActTS_20260919_v47_filled.tex > /dev/null 2>&1 || true

grep "Output written" "$J.log" || true
echo "errors $(grep -c '^! ' "$J.log" || true)  overfull $(grep -c Overfull "$J.log" || true)"
grep -oE "newlabel\{sec:conclusion\}\{\{[0-9]+\}\{[0-9]+\}" "$J.aux" || true
