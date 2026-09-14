"""Can the behavioural signal be made useful by removing what it really measures?

Peer calibration currently buys nothing. Corpus level AUROC is 0.468 against
0.467 for plain global standardisation, and every per type pair is within 0.03.
The reason is established in `docs/behavior_variable_identification.md`: the
signal measures predictability, not data quality, and calibrating it against
profile matched peers does not remove that because peers matched on a
statistical profile are not matched on predictability.

This tests the obvious next move. Estimate a predictability proxy per window
from cached signals, regress it out of the behavioural risk, and ask whether
what is left separates contaminated from clean data any better.

No TSFM is run. The proxies are computed from the series itself and the
behavioural risk is read from the traces of the run that measured it.

The regression uses no labels, so there is no leakage: it relates one measured
quantity to another and the residual is taken. The AUROC that follows is scored
against labels the regression never saw.

Usage:
    python -u experiments/decorrelate.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from corpus import CorpusSpec, OOD_KINDS, build_corpus  # noqa: E402
from predictability import ar_r2, naive_nmse, spectral_entropy  # noqa: E402
from stratum_risk import mann_whitney  # noqa: E402

TRACES = ROOT / "results" / "xl" / "xl_ett_multi-family_seed42_traces.json"
PROTECTED = ("clean", "hard", "rare_valid", "changepoint", "clean_ood")


def sample_entropy(x, m=2, r=0.2):
    """Sample entropy, the standard complexity measure for a time series.

    High for an irregular series, low for a repetitive one. Subsampled to keep
    the pairwise comparison affordable at this corpus size.
    """
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 64:
        return float("nan")
    x = x[::4]
    x = (x - x.mean()) / max(float(np.std(x)), 1e-12)
    n = len(x)
    tol = r
    counts = []
    for mm in (m, m + 1):
        emb = np.lib.stride_tricks.sliding_window_view(x, mm)
        d = np.abs(emb[:, None, :] - emb[None, :, :]).max(axis=2)
        np.fill_diagonal(d, np.inf)
        counts.append(float((d <= tol).sum()))
    if counts[0] <= 0 or counts[1] <= 0:
        return float("nan")
    return float(-np.log(counts[1] / counts[0]))


def spectral_flatness(x):
    """Geometric over arithmetic mean of the power spectrum, in [0, 1].

    One for white noise, near zero for a pure tone. Complements spectral
    entropy by being sensitive to a single dominant peak rather than to the
    overall spread.
    """
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 32:
        return float("nan")
    p = np.abs(np.fft.rfft(x - x.mean())) ** 2
    p = p[1:]
    p = p[p > 0]
    if len(p) < 4:
        return float("nan")
    return float(np.exp(np.mean(np.log(p))) / max(float(np.mean(p)), 1e-30))


def diff_acf1(x):
    """Lag one autocorrelation of the first difference.

    Near zero for a random walk, whose increments are unpredictable, and
    strongly negative for an over differenced or oscillating series.
    """
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 32:
        return float("nan")
    d = np.diff(x)
    if np.std(d) < 1e-12:
        return 0.0
    d = d - d.mean()
    return float(np.dot(d[:-1], d[1:]) / max(np.dot(d, d), 1e-30))


PROXIES = {
    "spectral_entropy": spectral_entropy,
    "spectral_flatness": spectral_flatness,
    "ar_r2": ar_r2,
    "naive_nmse": naive_nmse,
    "diff_acf1": diff_acf1,
    "sample_entropy": sample_entropy,
}


def auroc(scores, labels):
    """Rank based AUROC, positive class is label 1."""
    s = np.asarray(scores, float)
    y = np.asarray(labels, int)
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) < 2 or len(neg) < 2:
        return float("nan")
    return float(mann_whitney(pos, neg)["auc"])


def residualise(y, X):
    """Ordinary least squares residual of y on X with an intercept."""
    y = np.asarray(y, float)
    X = np.asarray(X, float)
    ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
    A = np.column_stack([np.ones(ok.sum()), X[ok]])
    coef, *_ = np.linalg.lstsq(A, y[ok], rcond=None)
    out = np.full(len(y), np.nan)
    out[ok] = y[ok] - A @ coef
    return out, coef


def main():
    if not TRACES.exists():
        print("deferred, no xl traces on disk")
        return
    spec = CorpusSpec(n_contaminated=740, n_clean=420, n_hard=210,
                      n_rare_valid=210, n_changepoint=210, n_clean_ood=210,
                      seed=42)
    allw = build_corpus(spec, source="ett")
    wins = {w.window_id: w for w in allw}
    oodw = [w for w in allw if w.stratum == "clean_ood"]
    form = {w.window_id: OOD_KINDS[i % len(OOD_KINDS)] for i, w in enumerate(oodw)}

    traces = json.loads(TRACES.read_text(encoding="utf-8"))["introact_full"]
    print(f"{len(traces)} traces", flush=True)

    rows = []
    for i, t in enumerate(traces):
        w = wins[t["window_id"]]
        p = {k: fn(w.series) for k, fn in PROXIES.items()}
        rows.append({
            "window_id": t["window_id"], "stratum": t["stratum"],
            "contamination": t.get("contamination"),
            "behav": float(t["behav_risk"]),
            "form": form.get(t["window_id"]),
            **p,
        })
        if (i + 1) % 400 == 0:
            print(f"  proxies {i + 1}/{len(traces)}", flush=True)

    keys = list(PROXIES)
    X = np.array([[r[k] for k in keys] for r in rows], float)
    behav = np.array([r["behav"] for r in rows], float)
    resid, coef = residualise(behav, X)

    print(f"\nregression of behavioural risk on the predictability proxies")
    print(f"  intercept {coef[0]:+.4f}")
    for k, c in zip(keys, coef[1:]):
        print(f"  {k:20s}{c:+.4f}")
    ok = np.isfinite(resid)
    ss_tot = float(np.var(behav[ok]))
    ss_res = float(np.var(resid[ok]))
    print(f"  variance explained {1 - ss_res / max(ss_tot, 1e-12):.3f}")

    y = np.array([1 if r["stratum"] == "contaminated" else 0 for r in rows])
    prot = np.array([r["stratum"] in PROTECTED for r in rows])

    print(f"\ncorpus level AUROC, contaminated against all protected strata")
    print(f"{'variant':28s}{'auroc':>9s}{'n_pos':>8s}{'n_neg':>8s}")
    mask = (y == 1) | prot
    variants = {
        "behavioural risk (as used)": behav,
        "predictability residual": resid,
    }
    out = {}
    for name, sc in variants.items():
        m = mask & np.isfinite(sc)
        a = auroc(sc[m], y[m])
        out[name] = a
        print(f"{name:28s}{a:9.3f}{int((y[m] == 1).sum()):8d}"
              f"{int((y[m] == 0).sum()):8d}")
    print(f"{'peer calibrated (recorded)':28s}{0.468:9.3f}{'':>8s}{'':>8s}")
    print(f"{'global standardised (recorded)':28s}{0.467:9.3f}{'':>8s}{'':>8s}")

    print(f"\nper contamination type, against clean windows only")
    print(f"{'type':20s}{'behavioural':>13s}{'residual':>11s}{'delta':>9s}")
    clean_idx = np.array([r["stratum"] == "clean" for r in rows])
    for ctype in sorted({r["contamination"] for r in rows if r["contamination"]}):
        idx = np.array([r["contamination"] == ctype for r in rows])
        m = idx | clean_idx
        yy = idx[m].astype(int)
        a1 = auroc(behav[m], yy)
        mm = m & np.isfinite(resid)
        a2 = auroc(resid[mm], idx[mm].astype(int))
        print(f"{ctype:20s}{a1:13.3f}{a2:11.3f}{a2 - a1:+9.3f}")

    print(f"\nclean_ood by form, median score, lower is a smaller false alarm")
    print(f"{'form':16s}{'behavioural':>13s}{'residual':>11s}"
          f"{'auc vs contam, behav':>22s}{'residual':>10s}")
    contam_b = behav[y == 1]
    contam_r = resid[(y == 1) & np.isfinite(resid)]
    for k in OOD_KINDS:
        idx = np.array([r["form"] == k for r in rows])
        b = behav[idx]
        r_ = resid[idx & np.isfinite(resid)]
        ab = mann_whitney(b, contam_b)["auc"]
        ar = mann_whitney(r_, contam_r)["auc"]
        print(f"{k:16s}{np.median(b):13.3f}{np.median(r_):11.3f}"
              f"{ab:22.3f}{ar:10.3f}")

    payload = {"coefficients": dict(zip(["intercept"] + keys, coef.tolist())),
               "variance_explained": 1 - ss_res / max(ss_tot, 1e-12),
               "auroc": out, "rows": rows}
    (ROOT / "results" / "decorrelate.json").write_text(
        json.dumps(payload, indent=1, default=float), encoding="utf-8")
    print("\n___DECORRELATE_DONE___", flush=True)


if __name__ == "__main__":
    main()
