"""Second trim: the conclusion restated the method, and two figures were wider
than they need to be at this level of detail.
"""
import io

PATH = "latex/IntroActTS_20260918_v45_review.tex"

PAIRS = [
    ("""We studied incomplete-input handling for frozen \\tsfm{}s as a per-request decision over a
fixed catalog of admissible interventions. The central question is whether an intervention
improves forecasting for the current request relative to leaving the input unchanged. That
answer cannot be read off the future, which is unavailable, nor off reconstruction quality,
which is not the same criterion as realised forecasting utility. \\introact{} answers it from
history by replaying TRAIN windows as pseudo-deployments, executing every catalog action with
the frozen forecaster, and storing the realised utility of each action with an
action-conditioned state. A request is then scored from the same-action neighbourhood of its
state, and an action is executed only when a conservative utility score is positive.""",
     """We studied incomplete-input handling for frozen \\tsfm{}s as a per-request decision over a fixed
catalog of admissible interventions. The realised utility of an intervention is not observable
at forecast time, and reconstruction quality turns out to be close to uninformative about it,
so \\introact{} reads the answer off history: it replays TRAIN windows as pseudo-deployments,
executes every catalog action with the frozen forecaster, and stores what each action did."""),

    ("""This section tests the two premises the method relies on. Both statistics are diagnostics
computed on TEST after the configuration is frozen, and neither is used for any selection.

The first premise is that the best action varies across requests. For each evaluation episode
we compute the oracle-best action as the minimiser of the realised loss over the catalog, and
we report the share of episodes on which each action is best together with the gap between the
best fixed catalog action and the catalog oracle. Figure~\\ref{fig:concept}(a) shows the
distribution.""",
     """Both statistics below are diagnostics computed on TEST after the configuration is frozen, and
neither is used for any selection.

The first premise is that the best action varies across requests. For each episode the
oracle-best action is the minimiser of the realised loss over the catalog, and
Figure~\\ref{fig:concept}(a) shows how often each action takes that role."""),

    ("""The stratum-level breakdown of the same episodes is deferred to
Appendix~\\ref{app:opportunity}, where the opportunity thresholds are also reported together
with their sensitivity to the boundary choice.""",
     """Appendix~\\ref{app:opportunity} breaks the same episodes down by how much improvement was
available."""),

    ("\\includegraphics[width=0.70\\textwidth]{figure/fig1_selective_governance.pdf}",
     "\\includegraphics[width=0.64\\textwidth]{figure/fig1_selective_governance.pdf}"),
    ("\\includegraphics[width=0.70\\textwidth]{figure/fig3_why_selective.pdf}",
     "\\includegraphics[width=0.62\\textwidth]{figure/fig3_why_selective.pdf}"),
]


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    for old, new in PAIRS:
        assert old in text, old[:60]
        text = text.replace(old, new)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print(f"trimmed {len(PAIRS)} passages")


if __name__ == "__main__":
    main()
