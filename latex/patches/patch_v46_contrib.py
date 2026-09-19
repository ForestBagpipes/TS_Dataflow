"""Contribution three now names the published baselines and reads its own result."""
import io

PATH = "latex/IntroActTS_20260919_v46.tex"

OLD = """\\textbf{(3)~Evidence on accuracy, harm
and cost.} Against a no-op control, the best fixed intervention and a simple learned
selector, on eight sources, three frozen \\tsfm{} families, four missingness patterns
and three severity levels, \\introact{} improves on the untouched input on every
backbone with paired intervals that exclude zero and has the best average rank of the
deployable rows on every backbone, at one to two backbone calls per request. We also
report where it does not win, which is the held-out backbone on which one fixed repair
reaches a lower macro average (\\S\\ref{sec:exp-main}, \\S\\ref{sec:exp-harm},
\\S\\ref{sec:exp-robust})."""

NEW = """\\textbf{(3)~Evidence on accuracy, harm
and cost.} Against a no-op control, the best fixed intervention, a simple learned selector, a
published reconstruction baseline and a published data-side adaptation baseline, on eight
sources, three frozen \\tsfm{} families, four missingness patterns and three severity levels,
\\ph{CONTRIB_RESULT} (\\S\\ref{sec:exp-main}, \\S\\ref{sec:exp-harm}, \\S\\ref{sec:exp-robust})."""


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert OLD in text, "contribution three"
    io.open(PATH, "w", encoding="utf-8").write(text.replace(OLD, NEW))
    print("contribution three parameterised")


if __name__ == "__main__":
    main()
