"""Why one family calibrates to a threshold that admits nothing.

DESPIKE's per family threshold came out at zero: any threshold above it admits
candidates whose average damage exceeds the target level. Three things are
checked together rather than one at a time, because the first two are competing
explanations and the third would change the loss for every family that touches a
gap.

  one    where the damaging candidates sit, by stratum. If they are in the
         protected strata, they are proposals the perception layer should not
         have made, and the structural threshold is being asked to clean up
         after a hypothesis error

  two    what happens if the risk is conditioned on the rest of the conjunction.
         Deployment admits a candidate only if the utility gain clears epsilon
         as well, so a candidate the utility condition already refuses never
         reaches the acceptance set and does not belong in the pool the
         structural threshold is calibrated over. Conditioning is not a
         relaxation; it is the third application of the same rule that fixed the
         corpus and the candidate distribution, namely that the calibrated
         quantity has to be the deployed quantity

  three  whether IMPUTE's mean loss is real. Filling a gap on a window that has
         one should be a low damage operation, and 0.5269 is not low. If the
         loss on the missing kinds is inflated by how `_nmse` treats the filled
         positions, every family that touches a gap is affected and the number
         is an artefact rather than a property of the operator

Reads the calibration scores already on disk. No GPU, no rerun.

Usage:
    python experiments/diagnose_family_risk.py
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from introact_ts.conformal import LOSS_BOUND, check_monotone  # noqa: E402

PROTECTED = ("clean", "hard", "rare_valid", "changepoint")
PROBE = "clean_ood"
LAMBDA_GRID = [0.0, 0.005, 0.01, 0.015, 0.02, 0.03, 0.04, 0.06, 0.08, 0.10,
               0.12, 0.16, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80,
               0.90, 0.95, 1.0]


def load(path):
    rows = []
    for line in Path(path).open(encoding="utf-8"):
        rec = json.loads(line)
        for c in rec["candidates"]:
            c["window_id"] = rec["window_id"]
            rows.append(c)
    return rows


def calibrate(rows, grid, alpha):
    n = len(rows)
    if n == 0:
        return None
    d = np.asarray([r["distortion"] for r in rows], dtype=np.float64)
    L = np.asarray([r["loss"] for r in rows], dtype=np.float64)
    curve = [float((L * (d < g)).sum() / n) for g in grid]
    corrected = [(n * r + LOSS_BOUND) / (n + 1) for r in curve]
    ok = [(g, r, c) for g, r, c in zip(grid, curve, corrected) if c <= alpha]
    g, r, c = ok[-1] if ok else (grid[0], curve[0], corrected[0])
    return {"n": n, "lambda": float(g), "risk": float(r), "corrected": float(c),
            "admitted": int((d < g).sum()), "mean_loss": float(L.mean()),
            "monotone": check_monotone(tuple(curve))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default=str(ROOT / "results" / "family_scores.jsonl"))
    ap.add_argument("--alpha", type=float, default=0.03)
    ap.add_argument("--epsilon", type=float, default=0.005)
    ap.add_argument("--out", default=str(ROOT / "results" / "family_risk_diagnosis.json"))
    args = ap.parse_args()

    rows = load(args.scores)
    fams = sorted({r["family"] for r in rows})
    print(f"{len(rows)} candidates, families {fams}, epsilon {args.epsilon}")

    # One. Where the damage sits.
    print()
    print("check 1, candidates and loss by family and stratum")
    print(f"{'family':11s}{'stratum':14s}{'n':>6s}{'mean loss':>11s}"
          f"{'loss=1 share':>14s}{'mean dU':>10s}{'dU>eps':>9s}")
    layout = defaultdict(dict)
    for fam in fams:
        sub = [r for r in rows if r["family"] == fam]
        for st in sorted({r["stratum"] for r in sub}):
            g = [r for r in sub if r["stratum"] == st]
            L = np.asarray([r["loss"] for r in g])
            U = np.asarray([r["delta_utility"] for r in g])
            rec = {"n": len(g), "mean_loss": float(L.mean()),
                   "share_loss_one": float((L >= 0.999).mean()),
                   "mean_du": float(U.mean()),
                   "share_passing_utility": float((U > args.epsilon).mean())}
            layout[fam][st] = rec
            print(f"{fam:11s}{st:14s}{len(g):6d}{L.mean():11.4f}"
                  f"{rec['share_loss_one']:14.4f}{U.mean():10.4f}"
                  f"{rec['share_passing_utility']:9.4f}")
        prot = [r for r in sub if r["stratum"] in PROTECTED or r["stratum"] == PROBE]
        con = [r for r in sub if r["stratum"] == "contaminated"]
        print(f"{fam:11s}{'PROTECTED+probe':14s}{len(prot):6d}"
              f"{np.mean([r['loss'] for r in prot]) if prot else float('nan'):11.4f}")
        print(f"{fam:11s}{'contaminated':14s}{len(con):6d}"
              f"{np.mean([r['loss'] for r in con]) if con else float('nan'):11.4f}")
        print()

    # Two. Risk conditioned on the rest of the conjunction.
    print("check 2, calibration before and after conditioning on the utility "
          "condition")
    print(f"{'family':11s}{'n all':>7s}{'lam all':>9s}{'admit':>7s}"
          f"{'n dU>eps':>10s}{'lam cond':>10s}{'admit':>7s}{'risk':>9s}"
          f"{'corrected':>11s}")
    cond = {}
    for fam in fams:
        sub = [r for r in rows if r["family"] == fam]
        a = calibrate(sub, LAMBDA_GRID, args.alpha)
        passing = [r for r in sub if r["delta_utility"] > args.epsilon]
        b = calibrate(passing, LAMBDA_GRID, args.alpha)
        cond[fam] = {"all": a, "conditioned": b}
        if b is None:
            print(f"{fam:11s}{a['n']:7d}{a['lambda']:9.4f}{a['admitted']:7d}"
                  f"{0:10d}{'n/a':>10s}")
            continue
        print(f"{fam:11s}{a['n']:7d}{a['lambda']:9.4f}{a['admitted']:7d}"
              f"{b['n']:10d}{b['lambda']:10.4f}{b['admitted']:7d}"
              f"{b['risk']:9.4f}{b['corrected']:11.4f}")

    # Three. Is IMPUTE's loss real, or an artefact on the gap kinds.
    print()
    print("check 3, IMPUTE loss by contamination kind")
    imp = [r for r in rows if r["family"] == "IMPUTE"]
    print(f"{'contamination':22s}{'n':>6s}{'mean loss':>11s}{'worse share':>13s}"
          f"{'discard share':>15s}{'mean dU':>10s}")
    kinds = {}
    for k in sorted({str(r["contamination"]) for r in imp}):
        g = [r for r in imp if str(r["contamination"]) == k]
        L = np.asarray([r["loss"] for r in g])
        W = np.asarray([r["worse"] for r in g])
        D = np.asarray([r["discard"] for r in g])
        U = np.asarray([r["delta_utility"] for r in g])
        kinds[k] = {"n": len(g), "mean_loss": float(L.mean()),
                    "worse_share": float(W.mean()),
                    "discard_mean": float(D.mean()),
                    "mean_du": float(U.mean())}
        print(f"{k:22s}{len(g):6d}{L.mean():11.4f}{W.mean():13.4f}"
              f"{D.mean():15.4f}{U.mean():10.4f}")

    gap = [r for r in imp if str(r["contamination"]).startswith("missing")]
    if gap:
        W = np.asarray([r["worse"] for r in gap])
        print(f"  on the two gap kinds specifically: {len(gap)} candidates, "
              f"worse on {W.mean():.4f} of them")
        print("  if that share is near one, filling a gap is being scored as "
              "damage by construction and the loss is an artefact")

    Path(args.out).write_text(json.dumps(
        {"epsilon": args.epsilon, "alpha": args.alpha,
         "by_family_stratum": layout, "conditioning": cond,
         "impute_by_kind": kinds}, indent=1, default=float), encoding="utf-8")
    print()
    print("___FAMILY_RISK_DIAGNOSIS_DONE___")


if __name__ == "__main__":
    main()
