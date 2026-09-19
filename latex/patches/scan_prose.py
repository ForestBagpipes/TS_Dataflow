"""House-style check on the rendered source.

The paper does not use semicolons, em dashes, or quotation marks in its prose,
so anything that survives here is either a style slip or a LaTeX construct that
needs an exemption.
"""
import io
import re

PATH = "latex/IntroActTS_20260919_v46_filled.tex"
SKIP = ("{rgb}", "definecolor", "newcommand", "setlength", "usepackage",
        "renewcommand", "DeclareMathOperator", "hypersetup", "lstset")


def context(text: str, position: int) -> str:
    return " ".join(text[max(0, position - 95):position + 45].split())


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    text = re.sub(r"(?m)^\s*%.*$", "", text)
    # Math spacing is not prose.
    text = text.replace(chr(92) + ";", " ")
    for label, pattern in (("semicolon", ";"), ("em dash", "—"),
                           ("en dash", "–"), ("double quote", "“"),
                           ("single quote", "‘")):
        for match in re.finditer(re.escape(pattern), text):
            seg = context(text, match.start())
            if any(token in seg for token in SKIP):
                continue
            print(f"[{label}] {seg}")


if __name__ == "__main__":
    main()
