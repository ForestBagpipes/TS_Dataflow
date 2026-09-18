"""Fourth trim, after the bibliography resolves and citations take their real width."""
import io

PATH = "latex/IntroActTS_20260918_v45_review.tex"

PAIRS = [
    ("""Both statistics below are diagnostics computed on TEST after the configuration is frozen, and
neither is used for any selection.

The first premise is that the best action varies across requests. For each episode the
oracle-best action is the minimiser of the realised loss over the catalog, and
Figure~\\ref{fig:concept}(a) shows how often each action takes that role.""",
     """Both statistics below are diagnostics computed on TEST after the configuration is frozen and
are used for no selection. The first premise is that the best action varies across requests.
For each episode the oracle-best action is the minimiser of the realised loss over the catalog,
and Figure~\\ref{fig:concept}(a) shows how often each action takes that role."""),

    ("""The second premise is that reconstruction quality does not tell a deployment which repair to
run. The four interventions all produce an explicit estimate of the hidden positions, and the
mask is synthetic, so both rankings exist for the same episode: how accurately each repair
recovered what was hidden, and how much it changed the forecasting loss. Ranking them within an
episode rather than pooling keeps sources of different scale and difficulty apart.
\\ph{RECON_READING}. Figure~\\ref{fig:why-selective}(a) shows the comparison and
Appendix~\\ref{app:recutils} reports it per action. \\introact{} is not placed in this ranking,
because it returns a forecast from an executed input rather than a reconstruction.""",
     """The second premise is that reconstruction quality does not tell a deployment which repair to
run. All four interventions estimate the hidden positions explicitly and the mask is synthetic,
so both rankings exist for the same episode, and ranking inside an episode keeps sources of
different scale apart. \\ph{RECON_READING}. Figure~\\ref{fig:why-selective}(a) shows it and
Appendix~\\ref{app:recutils} reports it per action. \\introact{} is not in this ranking, because
it returns a forecast from an executed input rather than a reconstruction."""),

    ("""Each source is split chronologically at three quarters of its rows, the earlier part TRAIN and
the later part TEST, and the last TRAIN window of each source is dropped so that the gap
exceeds the $L + H$ purge everywhere. TRAIN is split by origin time into the replay bank and a
TRAIN-eval block used once as an internal acceptance check. All design, hyperparameter
selection, feature normalisation and baseline fitting use TRAIN only, and every reported table
is computed once on TEST after the configuration is frozen. MASE~\\citep{hyndman2006mase} is the
primary metric and RMSSE the secondary one, aggregated source-macro with the parent as the
statistical unit and paired cluster bootstrap intervals against each control. Appendices
\\ref{app:splits}, \\ref{app:metric-conventions} and \\ref{app:diagnostic-conventions} record the
split boundaries and TEST manifest, the metric and statistics conventions, and the counting
rules the diagnostics rely on.""",
     """Each source is split chronologically at three quarters of its rows, the earlier part TRAIN and
the later part TEST, and the last TRAIN window of each source is dropped so the gap exceeds the
$L + H$ purge everywhere. TRAIN is split by origin time into the replay bank and a TRAIN-eval
block used once as an internal acceptance check. All design, hyperparameter selection, feature
normalisation and baseline fitting use TRAIN only, and every reported table is computed once on
TEST after the configuration is frozen. MASE~\\citep{hyndman2006mase} is the primary metric and
RMSSE the secondary one, aggregated source-macro with the parent as the statistical unit and
paired cluster bootstrap intervals. Appendices \\ref{app:splits},
\\ref{app:metric-conventions} and \\ref{app:diagnostic-conventions} hold the split boundaries,
the metric and statistics conventions, and the diagnostic counting rules."""),
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
