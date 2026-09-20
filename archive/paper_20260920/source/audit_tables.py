#!/usr/bin/env python3
"""Which section of the manuscript carries a table, and which argues from prose alone.

Prints one line per heading with the number of floats that sit under it, so a
section with zero is a place where a claim rests on sentences only.

Usage: python latex/audit_tables.py [source.tex]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path(sys.argv[1] if len(sys.argv) > 1
           else Path(__file__).resolve().parent / "IntroActTS_20260919_v47.tex")
TEXT = SRC.read_text(encoding="utf-8")

APPENDIX = TEXT.find("\n" + chr(92) + "appendix")
TOKEN = re.compile(
    r"\\(?P<sub>(?:sub)*)section\*?\{(?P<title>[^}]*)\}"
    r"|\\label\{(?P<kind>tab|fig):(?P<name>[^}]*)\}")

current = None
counts: dict[str, int] = {}
order: list[str] = []
for match in TOKEN.finditer(TEXT):
    where = "appendix" if (APPENDIX >= 0 and match.start() > APPENDIX) else "main"
    if match.group("title") is not None:
        depth = len(match.group("sub")) // 3
        current = f"[{where}] " + "  " * depth + match.group("title")
        if current not in counts:
            counts[current] = 0
            order.append(current)
    elif current is not None:
        counts[current] += 1

print(f"{'floats':>6}  section")
for heading in order:
    mark = "   <-- prose only" if counts[heading] == 0 else ""
    print(f"{counts[heading]:>6}  {heading}{mark}")
