"""Trim the body to fit nine pages once the numbers are in.

Cuts are to wording, not to content: the state groups are named once instead of
enumerated feature by feature (the appendix table is the canonical list), the
cap is stated in one sentence instead of three, and the setup stops repeating
what the appendix already says.
"""
import io

PATH = "latex/IntroActTS_20260918_v45_review.tex"

PAIRS = [
    ("""four groups of features. Mask state describes how the request is incomplete through the
missing fraction, the run structure of the gaps, the distance from the nearest gap to the
forecast origin, and whether other channels are affected. Visible-context state summarises the
observed part of the target channel by its robust scale, local trend, lag-one and seasonal
autocorrelation, recent level shift, and recent volatility. Intervention state describes how
$X^{a}$ differs from $X^{a_0}$, in the size of the change, the fraction of positions changed,
its trend, and how much of it falls near the forecast origin. Reference-forecast state is
computed from $p_0 = F(X^{a_0})$ and summarises forecast level, range, trend, the jump from
the last visible observation, and roughness. The complete feature list with window lengths and
normalisation is given once in Appendix~\\ref{app:features}, and continuous features are
standardised with statistics fitted on the replay bank only.""",
     """four groups of features, twenty-two numbers in total. Mask state describes how the request is
incomplete, through the missing fraction, the run structure of the gaps, the distance from the
nearest gap to the forecast origin, and whether other channels are affected. Visible-context
state summarises the observed part of the target channel. Intervention state describes how
$X^{a}$ differs from $X^{a_0}$. Reference-forecast state summarises $p_0 = F(X^{a_0})$.
Appendix~\\ref{app:features} is the canonical list, with the window lengths and the
normalisation, which is fitted on the replay bank only."""),

    ("""so the bandwidth is set by the query neighbourhood itself and is not tuned. Using the
median keeps the effective number of contributing neighbours roughly stable as the local
density of the bank changes, and $\\epsilon$ guards the degenerate case where every retrieved
distance is zero. The local mean utility, the local dispersion, and the effective sample size
are""",
     """so the bandwidth is set by the query neighbourhood itself and is not tuned. Taking the median
keeps the effective number of contributing neighbours stable as the local density of the bank
changes, and $\\epsilon$ guards the case where every retrieved distance is zero. The local mean
utility, the local dispersion, and the effective sample size are"""),

    ("""lowest cross-validated MASE, so harm enters as a constraint rather than as a quantity traded
against accuracy. The cap is not a free number. It is the conditional harmful rate of the best
fixed intervention, meaning the non-reference action with the highest mean realised utility on
the same bank, so the constraint reads as a requirement that choosing per request may not be
more harmful, given that it intervenes, than always applying the strongest single
intervention. If no grid point satisfies the cap the configuration falls back to the largest
penalty strength. The anchor action, the resulting cap and the selected pair are recorded with
the frozen configuration before any evaluation record is scored.

Two consequences of \\eqref{eq:decision} matter. The reference action is always available, so
the rule always returns a forecast. The rule also has no way to detect that a request lies
outside the replay support, so it applies to the registered missingness grid and the results
should not be read as out-of-grid generalisation.""",
     """lowest cross-validated MASE. The cap is not a free number: it is the conditional harmful rate
of the action with the highest mean realised utility on the same bank, so the constraint says
that choosing per request may not be more harmful, given that it intervenes, than always
applying the strongest single intervention. If no grid point satisfies it the configuration
falls back to the largest penalty strength. The anchor, the cap and the selected pair are
recorded before any evaluation record is scored.

The reference action is always available, so the rule always returns a forecast. It has no way
to detect that a request lies outside the replay support, so it applies to the registered
missingness grid and the results should not be read as out-of-grid generalisation."""),

    ("""Four cost components are kept separate and reported individually in Appendix~\\ref{app:calls},
namely the one-off offline bank construction, candidate materialisation, the
forecasting-backbone call, and retrieval overhead. A request costs one forecasting-backbone
call for the reference action plus one more if an intervention is executed. Two of the four
interventions build their candidate input by calling a frozen in-context imputation model,
which is paid before the decision and is booked under candidate materialisation rather than
hidden inside the forecasting count. The returned forecast is always one call of the unchanged
$F$ on one executed input version.""",
     """A request costs one forecasting-backbone call for the reference action plus one more if an
intervention is executed, and the returned forecast is always one call of the unchanged $F$ on
one executed input version. Two of the four interventions build their candidate by calling a
frozen in-context imputation model, which is paid before the decision.
Appendix~\\ref{app:calls} keeps the one-off bank construction, candidate materialisation, the
backbone call and retrieval overhead in separate columns."""),

    ("""Each source is split chronologically at three quarters of its rows. The earlier part is TRAIN,
the later part is TEST, and the last TRAIN window of each source is dropped so that the gap
between the two exceeds the $L + H$ purge everywhere. TRAIN is then split by origin time into
the replay bank and a TRAIN-eval block used once as an internal acceptance check. All design,
hyperparameter selection, feature normalisation and baseline fitting use TRAIN only, and every
reported table is computed once on TEST after the configuration is frozen.
MASE~\\citep{hyndman2006mase} is the primary metric and RMSSE the secondary one, aggregated
source-macro with the parent as the statistical unit and paired cluster bootstrap confidence
intervals against each control. Appendix~\\ref{app:splits} records the split boundaries and the
TEST manifest, Appendix~\\ref{app:metric-conventions} gives the metric and statistics
conventions, and Appendix~\\ref{app:diagnostic-conventions} fixes the counting rules the
diagnostics rely on, including tie-breaking for the oracle-best action and the treatment of
zero-utility interventions.""",
     """Each source is split chronologically at three quarters of its rows, the earlier part TRAIN and
the later part TEST, and the last TRAIN window of each source is dropped so that the gap
exceeds the $L + H$ purge everywhere. TRAIN is split by origin time into the replay bank and a
TRAIN-eval block used once as an internal acceptance check. All design, hyperparameter
selection, feature normalisation and baseline fitting use TRAIN only, and every reported table
is computed once on TEST after the configuration is frozen. MASE~\\citep{hyndman2006mase} is the
primary metric and RMSSE the secondary one, aggregated source-macro with the parent as the
statistical unit and paired cluster bootstrap intervals against each control. Appendices
\\ref{app:splits}, \\ref{app:metric-conventions} and \\ref{app:diagnostic-conventions} record the
split boundaries and TEST manifest, the metric and statistics conventions, and the counting
rules the diagnostics rely on."""),
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
