"""Find Python escape sequences that eat a LaTeX command.

A plain string writes chr(13) for the four characters of a reference, so the
generated sentence loses the command and the reader sees a stray line break.
A correctly doubled backslash is not a hit, so the lookbehind skips it.
"""
import glob
import io
import re

PATTERN = re.compile(r"(?<!\\)\\(?:r|b|f|v|a|t)(?=[a-zA-Z{])")


def main() -> None:
    hits = 0
    for path in sorted(glob.glob("latex/fill_v46*.py") + glob.glob("latex/patches/*.py")):
        for number, line in enumerate(io.open(path, encoding="utf-8").read().split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for match in PATTERN.finditer(line):
                before = line[:match.start()]
                if 'r"' in before or "r'" in before:
                    continue
                hits += 1
                print(f"{path}:{number}: {line.strip()[:120]}")
    data = io.open("latex/IntroActTS_20260919_v46_filled.tex", "rb").read()
    stray = sum(1 for i, byte in enumerate(data)
                if byte == 13 and (i + 1 >= len(data) or data[i + 1] != 10))
    print(f"stray carriage returns in the filled source: {stray}")
    print(f"suspect escapes: {hits}")


if __name__ == "__main__":
    main()
