"""Theorem 6's decay bound, read off the runs that already recorded it.

Experiment two's calibration decay row. No new run is needed and none is done
here: `SPOPolicy.theorem6_report` already writes the three measurable terms into
every result file whose rung carries a policy, so this file collects them across
rungs and seeds and evaluates the bound.

The bound is

    2 q T_cal / (gamma n_min)

with q the reward clip, T_cal the decisions between two recalibrations, gamma
the gap between the best and second best confidence bound at a decision, and
n_min the smallest visit count of any touched cell within the interval.

**Why it is evaluated at several quantiles of gamma rather than at the
infimum.** Section 3.5 states the worst case form fails if the lower tail of
gamma reaches zero, and a single decision where two arms tie sends the infimum
to zero and the bound to infinity. Reporting the quantiles is how that is
decided rather than assumed, and a bound that is infinite at the infimum and
still large at the median is a bound that does not constrain anything, which is
a result about the theorem's usefulness and has to be said plainly.

Usage:
    python experiments/calibration_decay.py --results results/xl
"""

import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def collect(results_dir, pattern="ablation_*_seed*.json"):
    """Every rung and seed that recorded a theorem 6 report."""
    out = []
    for p in sorted(Path(results_dir).glob(pattern)):
        blob = json.loads(p.read_text(encoding="utf-8"))
        t6 = blob.get("theorem6")
        if not t6:
            continue
        out.append({
            "file": p.name,
            "rung": blob.get("matrix_id"),
            "level": p.stem.replace("ablation_", "").rsplit("_seed", 1)[0],
            "seed": blob.get("seed"),
            "t6": t6,
        })
    return out


def bound(q, t_cal, gamma, n_min):
    """The decay bound. Infinite when gamma vanishes, which is its own content."""
    if gamma <= 1e-12 or n_min <= 0:
        return float("inf")
    return 2.0 * q * t_cal / (gamma * n_min)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "results" / "xl"))
    ap.add_argument("--out", default=str(ROOT / "results" / "calibration_decay.json"))
    args = ap.parse_args()

    rows = collect(args.results)
    if not rows:
        raise SystemExit(f"no result file under {args.results} carries a "
                         f"theorem6 report")
    print(f"{len(rows)} rung and seed combinations carry a theorem 6 report")
    print()

    print(f"{'level':16s}{'seed':>5s}{'intervals':>10s}{'decisions':>11s}"
          f"{'gamma q00':>11s}{'gamma q05':>11s}{'gamma med':>11s}"
          f"{'zero share':>12s}{'n_min':>7s}")
    report = []
    for r in rows:
        t6 = r["t6"]
        g = t6.get("gamma") or {}
        ivs = t6.get("intervals") or []
        n_mins = [iv["n_min"] for iv in ivs]
        rec = {
            "level": r["level"], "seed": r["seed"], "rung": r["rung"],
            "n_intervals": len(ivs),
            "n_decisions_with_choice": t6.get("n_decisions_with_choice"),
            "gamma_q00": g.get("q0.00"), "gamma_q05": g.get("q0.05"),
            "gamma_median": g.get("q0.50"), "gamma_mean": g.get("mean"),
            "zero_share": g.get("zero_share"),
            "n_min_per_interval": n_mins,
            "t_cal": t6.get("t_cal"), "reward_clip": t6.get("reward_clip"),
        }
        report.append(rec)
        print(f"{r['level']:16s}{r['seed']:5d}{len(ivs):10d}"
              f"{t6.get('n_decisions_with_choice', 0):11d}"
              f"{g.get('q0.00', float('nan')):11.4f}"
              f"{g.get('q0.05', float('nan')):11.4f}"
              f"{g.get('q0.50', float('nan')):11.4f}"
              f"{g.get('zero_share', float('nan')):12.4f}"
              f"{min(n_mins) if n_mins else -1:7d}")

    # The bound itself, at the quantiles that decide whether it says anything.
    print()
    print("the decay bound 2 q T_cal / (gamma n_min), at the worst interval")
    print(f"{'level':16s}{'seed':>5s}{'at q00':>14s}{'at q05':>14s}"
          f"{'at median':>14s}")
    for rec in report:
        q, t_cal = rec["reward_clip"], rec["t_cal"]
        nm = min(rec["n_min_per_interval"]) if rec["n_min_per_interval"] else 0
        vals = {}
        for key, g in (("q00", rec["gamma_q00"]), ("q05", rec["gamma_q05"]),
                       ("median", rec["gamma_median"])):
            vals[key] = bound(q, t_cal, g if g is not None else 0.0, nm)
        rec["bound"] = vals
        def fmt(v):
            return "inf" if not np.isfinite(v) else f"{v:.4g}"
        print(f"{rec['level']:16s}{rec['seed']:5d}{fmt(vals['q00']):>14s}"
              f"{fmt(vals['q05']):>14s}{fmt(vals['median']):>14s}")

    # The reading. A bound above one is vacuous for a total variation distance,
    # which is bounded by one by definition, so it is worth saying outright
    # rather than leaving the reader to notice.
    finite = [rec["bound"]["median"] for rec in report
              if np.isfinite(rec["bound"]["median"])]
    print()
    if finite:
        print(f"at the median gamma the bound ranges "
              f"{min(finite):.4g} to {max(finite):.4g}")
        print("a total variation distance is at most 1 by definition, so any "
              "bound above 1 constrains nothing")
        vacuous = sum(1 for v in finite if v > 1.0)
        print(f"{vacuous} of {len(finite)} are above 1")
    zero_shares = [rec["zero_share"] for rec in report
                   if rec["zero_share"] is not None]
    if zero_shares:
        print(f"decisions where the top two bounds tie, so gamma is zero: "
              f"{min(zero_shares):.4f} to {max(zero_shares):.4f} of decisions")

    Path(args.out).write_text(json.dumps({"rows": report}, indent=1,
                                         default=float), encoding="utf-8")
    print()
    print("___CALIBRATION_DECAY_DONE___")


if __name__ == "__main__":
    main()
