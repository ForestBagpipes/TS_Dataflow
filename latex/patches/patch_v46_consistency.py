"""Ninth v4.6 patch: remove the terms the v4.6 protocol no longer uses.

The gate block is gone, absorbed into the replay bank and replaced by
leave-one-parent-out cross-validation; the reconstruction oracle is gone,
replaced by the catalog comparison in Appendix~D; and the severity sweep uses
the roster of Table 1 rather than a reduced set.
"""
import io
import re

PATH = "latex/IntroActTS_20260918_v45_review.tex"

PAIRS = [
    ("D. Reconstruction and utility diagnostics & within-parent rank comparison, Reconstruction Oracle, governance diagnostics & is reconstruction quality a usable substitute for forecasting utility? \\\\",
     "D. Reconstruction and utility diagnostics & within-episode rank comparison over the catalog, governance diagnostics & is reconstruction quality a usable substitute for forecasting utility? \\\\"),
    ("The replay bank is constructed as follows. For every replay-fit parent we take the historical",
     "The replay bank is constructed as follows. For every bank parent we take the historical"),
    ("The replay bank is subsampled to $25\\%$, $50\\%$, and $100\\%$ of its replay-fit support to",
     "The replay bank is subsampled to $25\\%$, $50\\%$, and $100\\%$ of its parents to"),
    ("  \\caption{Replay-bank size ablation. The bank is subsampled by replay-fit parent, keeping",
     "  \\caption{Replay-bank size ablation. The bank is subsampled by parent, keeping"),
    ("pre-declared quantiles of $\\Delta_i$ computed on the gate split, computed once and applied",
     "pre-declared quantiles of $\\Delta_i$ computed on the replay bank, computed once and applied"),
    ("\\emph{high-opportunity} stratum. The two boundaries are fitted on the gate split and applied",
     "\\emph{high-opportunity} stratum. The two boundaries are fitted on the replay bank and applied"),
    ("  \\caption{Action-opportunity strata on TEST. Boundaries are the gate thresholds, applied",
     "  \\caption{Action-opportunity strata on TEST. Boundaries are the bank thresholds, applied"),
    ("  shifted by the indicated factor of the gate threshold, and every other setting is unchanged.",
     "  shifted by the indicated factor of the bank threshold, and every other setting is unchanged."),
    ("but type-complete set, and all three tables use the same seven methods. No method is retuned\nbetween severities. \\introact{} reuses the $k$ and $\\beta$ frozen on the gate, and every",
     "roster of Table~\\ref{tab:main}, and all three tables use it. No method is retuned\nbetween severities. \\introact{} reuses the $k$ and $\\beta$ frozen on the bank, and every"),
    ("  \\caption{Complete results at $10\\%$ severity for the reduced but type-complete set, all four metrics, source-macro averaged. Ranks are over deployable methods only and exclude the diagnostic row. This is the same seven-method set that Table~\\ref{tab:robust} summarises, and the two tables are computed from the same records.}",
     "  \\caption{Complete results at $10\\%$ severity, all four metrics, source-macro averaged. Ranks are over deployable methods only and exclude the diagnostic row. This is the roster that Table~\\ref{tab:robust} summarises, and the two tables are computed from the same records.}"),
    ("  \\caption{Ablation, full outcome vector. The Reconstruction Oracle reads the hidden values,\n  is a diagnostic rather than a deployable row, and is excluded from every rank. Calls counts\n  forecasting-backbone calls per request. Harmful loss is measured relative to\n  \\textsc{Keep}.}",
     "  \\caption{Ablation, full outcome vector. Calls counts forecasting-backbone calls per request,\n  and harmful loss is measured relative to \\textsc{Keep}.}"),
    ("    \\texttt{ablations}      & the six ablation variants plus the Reconstruction Oracle diagnostic & Table~\\ref{tab:ablation}, \\ref{tab:app-ablation} \\\\",
     "    \\texttt{ablations}      & the five ablation variants and the catalog oracle diagnostic & Table~\\ref{tab:ablation}, \\ref{tab:app-ablation} \\\\"),
]


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    applied = 0
    for old, new in PAIRS:
        if old in text:
            text = text.replace(old, new)
            applied += 1
    # The full ablation table keeps the same rows as the compact one.
    lines = [ln for ln in text.split("\n")
             if not ("Reconstruction Oracle (diagnostic)" in ln and "AF_ORACLE_MASE" in ln)]
    text = "\n".join(lines)
    text = text.replace("A4 w/o conservative gate", "A4 Always act")
    text = re.sub(r"A4 w/o conservative gate\s*", "A4 Always act ", text)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print(f"consistency patched, {applied}/{len(PAIRS)} replacements applied")


if __name__ == "__main__":
    main()
