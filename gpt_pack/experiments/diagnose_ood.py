"""Why the OOD hypothesis still almost never fires.

Fixing the unreachable 1e-3 floor moved the hypothesis from 0 wins in 90
clean_ood windows to 4. If the floor had been the only problem that number
should have changed by an order of magnitude, so it did not. There are exactly
two possibilities and they need different repairs:

  A  the threshold is still wrong, the scores separate the strata but the gate
     sits in the wrong place on that distribution
  B  the score itself does not separate, in which case corpus_reference is
     asking the wrong question and no threshold can rescue it

This decides between them by printing the distributions rather than reasoning
about them. Everything here is statistical profile only, so no TSFM is needed
and it runs on CPU.
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from corpus import CorpusSpec, build_corpus  # noqa: E402
from stratum_risk import mann_whitney  # noqa: E402

from introact_ts.calibration import ood_scores  # noqa: E402
from introact_ts.profiling import extract_statistical_profile  # noqa: E402
from introact_ts.risk import corpus_reference  # noqa: E402


def main():
    # The xl proportions, so the numbers line up with the 96 of 210 figure.
    spec = CorpusSpec(n_contaminated=740, n_clean=420, n_hard=210,
                      n_rare_valid=210, n_changepoint=210, n_clean_ood=210,
                      seed=42)
    windows = build_corpus(spec, source="ett")
    P = np.array([extract_statistical_profile(w.series) for w in windows])
    ood = ood_scores(P, K=min(20, len(windows) - 1))
    print(f"{len(windows)} windows", flush=True)

    by = {}
    for w, o in zip(windows, ood):
        by.setdefault(w.stratum, []).append(float(o))

    ref_spread = float(np.percentile(ood, 75) - np.percentile(ood, 25))
    ref_p85 = float(np.percentile(ood, 85))
    med = float(np.median(ood))
    gate_open = ref_spread > 1e-12 and ref_spread >= 0.05 * max(med, 1e-12)
    print(f"\ncorpus reference: p85 {ref_p85:.3e}  IQR spread {ref_spread:.3e}  "
          f"median {med:.3e}")
    print(f"new gate open: {gate_open}   old gate (p85 > 1e-3): {ref_p85 > 1e-3}")

    print(f"\n{'stratum':14s}{'n':>5s}{'p25':>11s}{'median':>11s}{'p75':>11s}"
          f"{'p90':>11s}{'max':>11s}{'frac > p85':>12s}")
    for k in sorted(by):
        v = np.array(by[k])
        q = np.percentile(v, [25, 50, 75, 90])
        print(f"{k:14s}{len(v):5d}{q[0]:11.3e}{q[1]:11.3e}{q[2]:11.3e}"
              f"{q[3]:11.3e}{v.max():11.3e}{np.mean(v > ref_p85):12.3f}")

    print("\nseparation of clean_ood against every other stratum, on the OOD score")
    for k in sorted(by):
        if k == "clean_ood":
            continue
        t = mann_whitney(by["clean_ood"], by[k])
        print(f"  vs {k:14s} auc {t['auc']:.3f}  p {t['p']:.2e}")

    # What the sigmoid actually returns for each stratum at the live settings.
    evid = [{} for _ in windows]
    risks = np.zeros(len(windows))
    reference = corpus_reference(evid, risks, ood)
    print(f"\nlive reference: ood_ref {reference.ood_ref:.3e}  "
          f"ood_scale {reference.ood_scale:.3e}")

    def sigmoid(x, s):
        return 1.0 / (1.0 + np.exp(-x / max(s, 1e-12)))

    print(f"\n{'stratum':14s}{'median ood_hi':>15s}{'p75':>10s}{'p90':>10s}"
          f"{'frac ood_hi > 0.5':>19s}")
    hi_by = {}
    for k in sorted(by):
        if reference.ood_scale > 0:
            hi = sigmoid(np.array(by[k]) - reference.ood_ref, reference.ood_scale)
        else:
            hi = np.zeros(len(by[k]))
        hi_by[k] = hi
        print(f"{k:14s}{np.median(hi):15.3f}{np.percentile(hi, 75):10.3f}"
              f"{np.percentile(hi, 90):10.3f}{np.mean(hi > 0.5):19.3f}")

    # The decisive arithmetic. clean_ood needs to beat contaminated on the
    # score, and the only term it has that contaminated lacks is 1.0 * ood_hi.
    print("\nwhat ood_hi has to overcome")
    print("  contaminated = 1.2*d_hi + 1.0*r_hi + 0.5*repr_anom - 0.8*rare")
    print("  clean_ood    = 1.2*d_lo + 0.6*r_hi + 1.0*ood_hi")
    print("  clean        = 1.2*d_lo + 1.0*r_lo")
    print()
    print("  With no defect (d_lo=1, d_hi=0) and an alarmed model (r_hi=1, r_lo=0):")
    print("    contaminated = 1.0 + 0.5*repr_anom")
    print("    clean_ood    = 1.2 + 0.6 + 1.0*ood_hi = 1.8 + ood_hi")
    print("    clean        = 1.2")
    print("  so clean_ood already leads on a clean unpredictable window, and the")
    print("  posterior is a softmax at temperature 0.5, meaning a 0.6 gap is")
    print("  already decisive. If clean_ood is losing, d_lo is not near 1, which")
    print("  means the statistical profile is reporting a defect on these windows.")

    hi = hi_by["clean_ood"]
    verdict = ("B, the score does not separate"
               if mann_whitney(by["clean_ood"], by["contaminated"])["auc"] < 0.60
               else "A, the score separates and the gate is misplaced"
               if np.mean(hi > 0.5) < 0.25
               else "neither, the score separates and the gate is open")
    print(f"\nverdict on the OOD score itself: {verdict}")


if __name__ == "__main__":
    main()
