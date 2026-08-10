"""Is behavioural risk driven by predictability rather than by contamination?

Two clean strata sit at opposite ends of the behavioural risk range. Synthetic
out of distribution shapes score a median of +0.489 and real cross domain
windows score -0.017, with contaminated windows between them at +0.090. Both
clean strata are equally far outside the pretraining mixture, so unfamiliarity
cannot be what separates them.

The candidate explanation is predictability. This computes predictability
proxies that never touch a TSFM, so the explanation is not being tested with
the same instrument that produced the thing to be explained, and correlates
them against the behavioural risk already measured.

Three proxies, cheap and standard:

  spectral_entropy   normalised entropy of the power spectrum. Low for a strong
                     cycle, high for something spread across all frequencies.
  ar_r2              out of sample R squared of a linear autoregression fit on
                     the first half and scored on the second. This is directly
                     "how well can a simple model predict this".
  naive_nmse         error of a persistence forecast, normalised. The floor any
                     forecaster should beat.

Usage:
    python -u experiments/predictability.py
"""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from corpus import CorpusSpec, build_corpus  # noqa: E402
from stratum_risk import mann_whitney  # noqa: E402


def spectral_entropy(x: np.ndarray) -> float:
    """Normalised spectral entropy, 0 for a pure tone and 1 for white noise."""
    x = np.asarray(x, float)
    x = x - x.mean()
    if np.std(x) < 1e-12:
        return 0.0
    p = np.abs(np.fft.rfft(x)) ** 2
    p = p[1:]
    total = p.sum()
    if total <= 0:
        return 0.0
    p = p / total
    p = p[p > 0]
    return float(-(p * np.log(p)).sum() / np.log(len(p)))


def ar_r2(x: np.ndarray, order: int = 12) -> float:
    """Out of sample R squared of a linear AR model, clipped at zero.

    Fit on the first half and score on the second, so a model that memorises
    the window gets no credit. Clipped below at 0 because a negative R squared
    only says "worse than the mean", and how much worse is not informative for
    ranking predictability.
    """
    x = np.asarray(x, float)
    x = (x - x.mean()) / max(np.std(x), 1e-12)
    T = len(x)
    if T < 4 * order:
        return 0.0
    rows = np.lib.stride_tricks.sliding_window_view(x, order + 1)
    X, y = rows[:, :-1], rows[:, -1]
    split = len(y) // 2
    Xtr, ytr, Xte, yte = X[:split], y[:split], X[split:], y[split:]
    try:
        coef, *_ = np.linalg.lstsq(Xtr, ytr, rcond=None)
    except np.linalg.LinAlgError:
        return 0.0
    resid = float(np.mean((yte - Xte @ coef) ** 2))
    denom = float(np.var(yte))
    if denom < 1e-12:
        return 0.0
    return float(max(0.0, 1.0 - resid / denom))


def naive_nmse(x: np.ndarray, horizon: int = 48) -> float:
    """Persistence forecast error over the last `horizon` points, normalised."""
    x = np.asarray(x, float)
    if len(x) <= horizon + 1:
        return float("nan")
    ctx, tgt = x[:-horizon], x[-horizon:]
    pred = np.full(horizon, ctx[-1])
    denom = max(float(np.var(tgt)), 1e-12)
    return float(np.mean((tgt - pred) ** 2) / denom)


def pearson(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    if len(a) < 3:
        return float("nan")
    a = a - a.mean()
    b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else float("nan")


def spearman(a, b):
    def rank(v):
        v = np.asarray(v, float)
        order = np.argsort(v)
        r = np.empty(len(v), float)
        r[order] = np.arange(len(v))
        return r

    return pearson(rank(a), rank(b))


def main():
    risk_path = ROOT / "results" / "ood_check.json"
    if not risk_path.exists():
        print("deferred, results/ood_check.json not present")
        return

    spec = CorpusSpec(
        n_contaminated=350, n_clean=200, n_hard=100, n_rare_valid=100,
        n_changepoint=100, n_clean_ood=150, n_real_ood=150, seed=42,
    )
    windows = build_corpus(spec, source="ett")
    print(f"rebuilt {len(windows)} windows", flush=True)

    rows = []
    for w in windows:
        x = w.series
        finite = x[np.isfinite(x)]
        if len(finite) < 64:
            continue
        rows.append({
            "window_id": w.window_id,
            "stratum": w.stratum,
            "spectral_entropy": spectral_entropy(finite),
            "ar_r2": ar_r2(finite),
            "naive_nmse": naive_nmse(finite),
        })

    # Behavioural risk comes from the run that measured it, matched by stratum
    # order. The agent iterates windows in build order, so the per stratum
    # sequences line up.
    risk = json.loads(risk_path.read_text(encoding="utf-8"))
    have_per_window = "raw" in risk.get("strata", {}).get("contaminated", {})
    print(f"per window risk available in ood_check.json: {have_per_window}")

    by = {}
    for r in rows:
        by.setdefault(r["stratum"], []).append(r)

    print()
    print(f"{'stratum':14s}{'n':>5s}{'spec_ent':>10s}{'ar_r2':>9s}{'naive_nmse':>12s}"
          f"{'median behav':>14s}")
    summary = {}
    for k in sorted(by):
        g = by[k]
        se = float(np.median([r["spectral_entropy"] for r in g]))
        ar = float(np.median([r["ar_r2"] for r in g]))
        nn = float(np.median([r["naive_nmse"] for r in g]))
        br = risk["strata"].get(k, {}).get("behavioural_risk", {}).get("median")
        summary[k] = {"n": len(g), "spectral_entropy": se, "ar_r2": ar,
                      "naive_nmse": nn, "median_behav_risk": br}
        brs = f"{br:+14.3f}" if br is not None else f"{'n/a':>14s}"
        print(f"{k:14s}{len(g):5d}{se:10.3f}{ar:9.3f}{nn:12.3f}{brs}")

    # Stratum level correlation between the proxies and the measured risk.
    ks = [k for k in sorted(by) if summary[k]["median_behav_risk"] is not None]
    br = [summary[k]["median_behav_risk"] for k in ks]
    print()
    print("stratum level correlation against median behavioural risk")
    corr = {}
    for proxy in ["spectral_entropy", "ar_r2", "naive_nmse"]:
        v = [summary[k][proxy] for k in ks]
        corr[proxy] = {"pearson": pearson(v, br), "spearman": spearman(v, br)}
        print(f"  {proxy:18s} pearson {corr[proxy]['pearson']:+.3f}"
              f"  spearman {corr[proxy]['spearman']:+.3f}   n={len(ks)} strata")

    payload = {"per_stratum": summary, "correlations": corr, "windows": rows}
    (ROOT / "results" / "predictability.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8")
    print(f"\nwritten results/predictability.json")


if __name__ == "__main__":
    main()
