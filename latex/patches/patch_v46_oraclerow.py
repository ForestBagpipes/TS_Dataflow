"""The oracle row of each per-severity table still had five cells."""
import io
import re

PATH = "latex/IntroActTS_20260919_v46.tex"

PATTERN = re.compile(
    r"\\oracle\{Catalog Oracle \(diagnostic\)\} & "
    r"\\oracle\{\\ph\{SEV(\d+)-ORACLE-MASE\}\} & "
    r"\\oracle\{\\ph\{SEV\d+-ORACLE-MSE\}\} & "
    r"\\oracle\{\\ph\{SEV\d+-ORACLE-MAE\}\} & "
    r"\\oracle\{\\ph\{SEV\d+-ORACLE-RMSE\}\} & \\oracle\{---\}")


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()

    def repl(match):
        level = match.group(1)
        return ("\\oracle{Catalog Oracle (diagnostic)} & "
                f"\\oracle{{\\ph{{SEV{level}-ORACLE-MASE}}}} & "
                f"\\oracle{{\\ph{{SEV{level}-ORACLE-RMSSE}}}} & \\oracle{{---}}")

    text, n = PATTERN.subn(repl, text)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print(f"oracle rows fixed: {n}")


if __name__ == "__main__":
    main()
