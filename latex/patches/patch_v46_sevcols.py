"""The per-severity tables used raw-error columns the metric convention forbids
averaging across sources.  They now carry the two scaled metrics and the rank.
"""
import io
import re

PATH = "latex/IntroActTS_20260919_v46.tex"


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    old_head = ("    Method & MASE $\\downarrow$ & MSE $\\downarrow$ & MAE $\\downarrow$ & "
                "RMSE $\\downarrow$ & Rank $\\downarrow$ \\\\")
    new_head = ("    Method & MASE $\\downarrow$ & RMSSE $\\downarrow$ & Rank $\\downarrow$ \\\\")
    assert old_head in text, "severity header"
    text = text.replace(old_head, new_head)

    # Drop the two raw-error cells from every per-severity row.
    def fix(match):
        level, method = match.group(1), match.group(2)
        return (f"\\ph{{SEV{level}-{method}-MASE}} & \\ph{{SEV{level}-{method}-RMSSE}} & "
                f"\\ph{{SEV{level}-{method}-RANK}}")

    text = re.sub(
        r"\\ph\{SEV(\d+)-([A-Z0-9]+)-MASE\} & \\ph\{SEV\d+-[A-Z0-9]+-MSE\} & "
        r"\\ph\{SEV\d+-[A-Z0-9]+-MAE\} & \\ph\{SEV\d+-[A-Z0-9]+-RMSE\} & "
        r"\\ph\{SEV\d+-[A-Z0-9]+-RANK\}", fix, text)

    text = text.replace(
        "\\resizebox{\\textwidth}{!}{\\begin{tabular}{lccccc}\n    \\toprule\n"
        "    Method & MASE $\\downarrow$ & RMSSE $\\downarrow$ & Rank $\\downarrow$ \\\\",
        "\\resizebox{\\textwidth}{!}{\\begin{tabular}{lccc}\n    \\toprule\n"
        "    Method & MASE $\\downarrow$ & RMSSE $\\downarrow$ & Rank $\\downarrow$ \\\\")
    text = text.replace(
        "all four metrics, source-macro averaged",
        "source-macro averaged in the two scaled metrics")
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("severity tables now use the scaled metrics")


if __name__ == "__main__":
    main()
