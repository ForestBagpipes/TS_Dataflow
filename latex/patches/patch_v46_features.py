"""Fourth v4.6 patch: the state-feature table, rewritten from the implementation.

The earlier table described a pattern one-hot, an action one-hot, spectral
seasonality and per-channel averaging, none of which the code computes.  The
table below is the 22-dimensional state the selector actually reads.
"""
import io

PATH = "latex/IntroActTS_20260918_v45_review.tex"

OLD_START = "    Group & Feature & Definition and window & Channel handling & Scaling \\\\"
OLD_END = "     & roughness & mean absolute second difference of $p_0$ & per channel, then averaged & z-scored on replay-fit \\\\"

NEW_BODY = r"""    Group & Feature & Definition & Scaling \\
    \midrule
    Mask state, 6 & missing ratio & share of target-channel positions with $M = 0$ & scale free \\
     & longest run & longest run of consecutive missing positions, as a share of $L$ & scale free \\
     & number of runs & count of maximal missing runs, divided by $L$ & scale free \\
     & distance to origin & steps from the end of the last missing run to the forecast origin, divided by $L$ & scale free \\
     & shared indicator & one if any other channel is also missing & binary \\
     & tail indicator & one if the last context position is missing & binary \\
    \midrule
    Visible-context state, 6 & robust scale $s$ & median over eight blocks of the interquartile range of the visible target values & the unit of the other context features \\
     & local trend & least-squares slope over the visible positions, divided by $s$ & scale free \\
     & lag-one autocorrelation & autocorrelation of the gap-interpolated target at lag one & scale free \\
     & seasonal autocorrelation & the same at the registered seasonal period $m$ & scale free \\
     & recent level shift & absolute difference between the means of the last and the preceding $W = 32$ steps, divided by $s$ & scale free \\
     & recent volatility & standard deviation of the first differences over the last $W$ steps, divided by $s$ & scale free \\
    \midrule
    Intervention state, 5, per action $a$ & mean absolute change & mean of $|X^{a} - X^{a_0}|$ over the context, divided by $s$ & scale free \\
     & maximum change & largest absolute difference, divided by $s$ & scale free \\
     & changed fraction & share of positions where $X^{a}$ differs from $X^{a_0}$ & scale free \\
     & change trend & least-squares slope of the difference over the changed positions, divided by $s$ & scale free \\
     & change near origin & mean absolute difference over the last $W$ steps, divided by $s$ & scale free \\
    \midrule
    Reference-forecast state, 5 & forecast level & mean of $p_0$ over the horizon, divided by $s$ & scale free \\
     & forecast range & range of $p_0$ over the horizon, divided by $s$ & scale free \\
     & forecast trend & least-squares slope of $p_0$, divided by $s$ & scale free \\
     & first-step jump & first step of $p_0$ minus the last visible value, divided by $s$ & scale free \\
     & roughness & mean absolute first difference of $p_0$, divided by $s$ & scale free"""

OLD_CAPTION = """  \\caption{Canonical definition of the action-conditioned state. Every feature is computable
  from the request and the reference forecast alone. Retrieval uses the standardised Euclidean
  distance between states, with no learned encoder and no learned metric.}"""
NEW_CAPTION = """  \\caption{The action-conditioned state, as implemented. It has 22 dimensions: six describing
  the mask, six describing the visible context, five describing the candidate intervention and
  five describing the reference forecast. Every feature is computable from the request and the
  reference forecast alone. The target channel is the forecast channel, and the only place the
  other channels enter is the shared indicator. Features are divided by the robust scale $s$ of
  the visible context where they carry a unit, and the state is then standardised with the mean
  and standard deviation of the replay bank before distances are taken.}"""

OLD_SPEC = ("\\resizebox{\\textwidth}{!}{\\begin{tabular}{@{}l p{0.24\\textwidth} "
            "p{0.30\\textwidth} p{0.18\\textwidth} p{0.13\\textwidth}@{}}")
NEW_SPEC = ("\\resizebox{\\textwidth}{!}{\\begin{tabular}{@{}l p{0.22\\textwidth} "
            "p{0.42\\textwidth} p{0.16\\textwidth}@{}}")


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    i = text.find(OLD_START)
    j = text.find(OLD_END)
    assert i > 0 and j > i, "feature table body not found"
    text = text[:i] + NEW_BODY + text[j + len(OLD_END):]
    assert OLD_CAPTION in text, "feature caption"
    text = text.replace(OLD_CAPTION, NEW_CAPTION)
    assert OLD_SPEC in text, "feature column spec"
    text = text.replace(OLD_SPEC, NEW_SPEC)
    text = text.replace(
        "of each feature. Continuous features are standardised with statistics fitted on replay-fit\nparents only, and the normalisation is frozen with the rest of the configuration.",
        "of each feature. Continuous features are standardised with statistics fitted on the replay\nbank only, and the normalisation is frozen with the rest of the configuration.")
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("feature table patched")


if __name__ == "__main__":
    main()
