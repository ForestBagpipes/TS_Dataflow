#!/usr/bin/env python3
"""Stand-in numbers for every placeholder, to check the layout before the run lands.

This produces nothing that may enter the paper.  Its only job is to answer two
questions early: does the template compile, and does the main text still fit in
nine pages once the figures became tables.

Usage: python latex/dummy_fill.py <source.tex> <target.tex>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BS = "\\" * 2

ROWGEN = {
    "HOLM_ROWS": "\n".join(
        f"    Bolt & baseline {i} & -0.0100 & [-0.0200, -0.0010] & 0.0100 & 0.0200 {BS}"
        for i in range(1, 6)),
    "SELSTAB_ROWS": "\n".join(
        f"    Bolt & full bank & 128 & 1 & 1.366 & 53.0\\% {BS}" for _ in range(7)),
}

SENTENCE = re.compile(
    r"(READING|CLOSING|RESULT|STATS|SHARES|GAP$|_GAP|_CI$|SEMANTICS|BASELINE_SPREAD"
    r"|RISKCURVE|_HOLM$|R2CART|MAIN_BACKBONE|STRONG_BASELINE|COLDSTART)")
INTERVAL = re.compile(r"(_CI$|INTERVAL$)")
PERCENT = re.compile(r"(_IR$|_HIR$|_SHARE$|_BP$|_MO$|_CHIR$|^RG_|^OPPT_|RATE$|FAILRATE)")
COUNT = re.compile(r"(_N$|PARENTS$|ORIGINS$|SOURCES$|_CAND$|CALLS_.*_N$)")


def value(key: str) -> str:
    if key in ROWGEN:
        return ROWGEN[key]
    if key.startswith("FIGURE_"):
        return key
    if INTERVAL.search(key):
        return "[-0.020, -0.001]"
    if SENTENCE.search(key):
        return ("a stand-in sentence of the length the generated prose is expected to have "
                "in the finished manuscript")
    if PERCENT.search(key):
        return "42.0\\%"
    if COUNT.search(key):
        return "760"
    if key.endswith(("_MEAN", "_P95", "_MAX")):
        return "80 ms"
    if key.endswith("_CI"):
        return "[-0.020, -0.001]"
    return "1.234"


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    text = src.read_text(encoding="utf-8")
    out = re.sub(r"\\ph\{([A-Za-z0-9_\-]+)\}", lambda m: value(m.group(1)), text)
    dst.write_text(out, encoding="utf-8")
    print(f"wrote {dst.name}, placeholders left {out.count(chr(92) + 'ph{')}")


if __name__ == "__main__":
    main()
