"""The governance figure now carries measured numbers, so the text says what they are.

Panel (b) used to be a skeleton, and the paragraph around it could only describe
what the panel would show.  It now reports the sign agreement and the two
conditional means that the panel plots.
"""
import io

TEX = "latex/IntroActTS_20260919_v46.tex"
EXTRA = "latex/fill_v46_extra.py"

OLD_TEX = r"""Figure~\ref{fig:governance} visualises the diagnostics tabulated in
Table~\ref{tab:harm}. Panel~(b) is a sign-agreement check rather than a calibration
curve: the ranking score is used only to order actions, and we do not claim that its magnitude
is a calibrated probability.

\begin{figure}[h]
  \centering
  \includegraphics[width=0.84\textwidth]{figure/fig4_governance_diagnostics.pdf}
  \caption{\textbf{(a)}~Harmful loss by method. \textbf{(b)}~Realised utility against the
  binned ranking score with 95\% intervals. Panel~(b) is a sign agreement check, not a
  calibration claim.}
  \label{fig:governance}
\end{figure}"""

NEW_TEX = r"""Figure~\ref{fig:governance} visualises the diagnostics tabulated in
Table~\ref{tab:harm}. Panel~(b) checks sign agreement. The ranking score is used only to order
actions, and its magnitude is not claimed to be calibrated against the utility scale.
\ph{GOV_FIG_READING}.

\begin{figure}[h]
  \centering
  \includegraphics[width=0.84\textwidth]{figure/fig4_governance_diagnostics.pdf}
  \caption{\textbf{(a)}~Harmful loss per method, averaged over the three backbones.
  \textbf{(b)}~Realised utility of every admissible action against the quantile bin of its
  conservative score, with 95\% intervals that resample parents. Panel~(b) reports sign
  agreement and makes no calibration claim.}
  \label{fig:governance}
\end{figure}"""

ANCHOR = '''    # The severity reading, written from the sweep itself.'''

BLOCK = '''    # The governance figure reading, from the score-against-utility records.
    agree, positive, negative, pairs = [], [], [], 0
    for backbone in ("bolt", "timesfm", "chronos2"):
        path = ROOT / f"results/v46/diagnostics/score_utility_test_{backbone}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        agree.append(payload["sign_agreement"])
        if payload.get("mean_utility_positive_score") is not None:
            positive.append(payload["mean_utility_positive_score"])
        if payload.get("mean_utility_negative_score") is not None:
            negative.append(payload["mean_utility_negative_score"])
        pairs += payload["pairs"]
    if agree and positive and negative:
        out["GOV_FIG_READING"] = (
            f"Over {pairs} admissible pairs the sign of the score and the sign of the realised "
            f"utility agree on {sum(agree) / len(agree) * 100:.0f}\\\\% of them, and the mean "
            f"realised utility is {sum(positive) / len(positive):+.3f} where the score is "
            f"positive against {sum(negative) / len(negative):+.3f} where it is negative, so the "
            f"score carries the direction the decision needs without carrying the level")

    # The severity reading, written from the sweep itself.'''


def main() -> None:
    text = io.open(TEX, encoding="utf-8").read()
    assert OLD_TEX in text, "governance figure block"
    io.open(TEX, "w", encoding="utf-8").write(text.replace(OLD_TEX, NEW_TEX, 1))

    extra = io.open(EXTRA, encoding="utf-8").read()
    assert ANCHOR in extra, "extra anchor"
    io.open(EXTRA, "w", encoding="utf-8").write(extra.replace(ANCHOR, BLOCK, 1))
    print("governance figure text and reading added")


if __name__ == "__main__":
    main()
