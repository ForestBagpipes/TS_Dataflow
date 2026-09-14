"""Stage zero. Is there anything for a policy to learn.

A learned policy over actions only beats a fixed rule if the chance an action
is admitted depends on the state it is proposed in. If admission rates are flat
across states then the fixed ordering is already close to optimal under this
state representation and there is nothing for SPO to fit.

This script tests that precondition on governance traces that already exist. No
model is loaded and no window is curated. The statistical profile is a pure
function of the series, so the clustering runs on CPU from the corpus alone, and
the admission outcomes are read from the stored traces.

The profile space is the one CDP retrieves peers in, `calibration.calibrate`
L2 normalises the profiles and runs cosine nearest neighbours, so clustering
uses the same normalised vectors under the same metric.

Reported per cell, cell being one cluster crossed with one operator:
  n            candidates the shield actually adjudicated
  accept rate  admitted over adjudicated
  mean dU      mean utility change of the admitted ones

The verdict is one of exactly two readings, fixed before the run:
  differ   admission rate varies across clusters beyond sampling noise, so
           there is learnable structure and SPO is worth implementing
  flat     it does not, so the fixed rule is already near optimal under this
           representation, SPO is not implemented, and the negative result is
           reported with the conclusion that the state needs finer granularity

Usage:
    python -u experiments/spo_feasibility.py --k 12
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import normalize as sk_normalize
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from corpus import build_corpus  # noqa: E402
from run_agent import SCALES  # noqa: E402

from introact_ts.profiling import extract_statistical_profile  # noqa: E402

#: Operators that rewrite the series and therefore reach the shield. KEEP,
#: ABSTAIN and QUARANTINE terminate the episode and are always NO_OP, so they
#: carry no admission decision.
MUTATING = ("IMPUTE", "DESPIKE", "DENOISE", "RESEGMENT")

#: A NO_OP verdict means the operator did not apply to this window, so the
#: shield never ruled on it. Those candidates are excluded from every rate.
ADJUDICATED = ("ACCEPTED", "ROLLED_BACK_UTILITY", "ROLLED_BACK_STRUCTURE",
               "ROLLED_BACK_RISK")


def load_traces(path, arm):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if arm not in d:
        raise SystemExit(f"arm {arm} not in {sorted(d)}")
    return d[arm]


def profile_matrix(windows, n_jobs=None):
    """The L2 normalised profile space CDP retrieves peers in.

    Computed once for all values of k. The profile is a pure function of the
    series so this parallelises the same way `IntroActAgent.perceive` does.
    """
    series = [np.asarray(w.series, dtype=np.float64) for w in windows]
    if n_jobs == 1:
        profiles = [extract_statistical_profile(x) for x in series]
    else:
        import multiprocessing as mp
        n = n_jobs or max(1, (mp.cpu_count() or 2) - 2)
        chunk = max(1, len(series) // (n * 4))
        with mp.Pool(n) as pool:
            profiles = list(pool.map(extract_statistical_profile, series,
                                     chunksize=chunk))
    return sk_normalize(np.nan_to_num(np.stack(profiles)), norm="l2")


def cluster_profiles(pn, k, seed):
    """Cluster in that space. On L2 normalised vectors euclidean k means and
    cosine distance induce the same ordering, so this is CDP's geometry."""
    return KMeans(n_clusters=k, n_init=10, random_state=seed).fit(pn).labels_


def build_cells(rows, labels, window_ids):
    """One record per adjudicated candidate, tagged with its cluster."""
    cluster_of = {wid: int(c) for wid, c in zip(window_ids, labels)}
    cells = defaultdict(lambda: {"n": 0, "accepted": 0, "dU": []})
    skipped_unknown = 0
    for r in rows:
        c = cluster_of.get(r["window_id"])
        if c is None:
            skipped_unknown += 1
            continue
        for s in r["steps"]:
            if s["action"] not in MUTATING or s["verdict"] not in ADJUDICATED:
                continue
            cell = cells[(c, s["action"])]
            cell["n"] += 1
            if s["verdict"] == "ACCEPTED":
                cell["accepted"] += 1
                cell["dU"].append(float(s["delta_utility"]))
    return cells, skipped_unknown


def chi2_by_action(cells, k):
    """Per operator, does the admission rate vary across clusters."""
    out = {}
    for a in MUTATING:
        rows = [(c, cells[(c, a)]["n"], cells[(c, a)]["accepted"])
                for c in range(k) if (c, a) in cells and cells[(c, a)]["n"] > 0]
        if len(rows) < 2:
            out[a] = {"testable": False, "reason": "fewer than two occupied clusters"}
            continue
        table = np.array([[acc, n - acc] for _, n, acc in rows], dtype=float)
        keep = table.sum(axis=1) > 0
        table = table[keep]
        if table.shape[0] < 2 or table.sum(axis=0).min() == 0:
            out[a] = {"testable": False,
                      "reason": "a margin is zero, no variation to test"}
            continue
        chi2, p, dof, exp = stats.chi2_contingency(table)
        small = int((exp < 5).sum())
        # Fisher is exact and does not need the expected count rule. It is only
        # tractable on small tables, so it is attempted and reported when it
        # returns.
        p_exact = None
        if table.shape[0] <= 8 and table.sum() < 400:
            try:
                p_exact = float(stats.fisher_exact(table)[1]) if table.shape[0] == 2 else None
            except Exception:
                p_exact = None
        rates = [acc / n for _, n, acc in rows]
        out[a] = {"testable": True, "chi2": float(chi2), "p": float(p), "dof": int(dof),
                  "n_clusters": int(table.shape[0]), "n_candidates": int(table.sum()),
                  "cells_expected_below_5": small,
                  "rate_min": float(min(rates)), "rate_max": float(max(rates)),
                  "p_fisher": p_exact}
    return out


def permutation_p(cells, k, action, n_perm, seed):
    """Chi square p without the expected count approximation.

    Several cells hold fewer than five expected candidates, where the asymptotic
    chi square is unreliable. This reshuffles the admit labels across candidates
    holding the per cluster counts fixed, which is exact up to Monte Carlo error.
    """
    ns, accs = [], []
    for c in range(k):
        v = cells.get((c, action))
        if v and v["n"] > 0:
            ns.append(v["n"])
            accs.append(v["accepted"])
    ns, accs = np.array(ns), np.array(accs)
    N, A = int(ns.sum()), int(accs.sum())
    if len(ns) < 2 or A == 0 or A == N:
        return None
    obs = stats.chi2_contingency(np.array([accs, ns - accs]).T)[0]
    rng = np.random.RandomState(seed)
    labels = np.zeros(N, dtype=np.int64)
    labels[:A] = 1
    bounds = np.cumsum(ns)[:-1]
    hits = 0
    for _ in range(n_perm):
        rng.shuffle(labels)
        pa = np.array([s.sum() for s in np.split(labels, bounds)])
        t = np.array([pa, ns - pa]).T.astype(float)
        if t.sum(axis=0).min() == 0:
            continue
        if stats.chi2_contingency(t)[0] >= obs:
            hits += 1
    return float(hits / n_perm)


def stratum_confound(labels, windows, k):
    """Is a cluster merely a restatement of the stratum label.

    If it is, then admission varying across clusters says only that admission
    varies across strata, which CDP already reports as its hypothesis field, and
    nothing new is learnable from the profile geometry.
    """
    from sklearn.metrics import adjusted_mutual_info_score
    strata = np.array([w.stratum for w in windows])
    names = sorted(set(strata))
    table = {int(c): {s: int(((labels == c) & (strata == s)).sum()) for s in names}
             for c in range(k)}
    return {"ami": float(adjusted_mutual_info_score(strata, labels)),
            "strata": names, "table": table,
            "cluster_sizes": {int(c): int((labels == c).sum()) for c in range(k)}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces", default=str(
        ROOT / "results" / "xl" / "xl_ett_multi-family_seed42_traces.json"))
    ap.add_argument("--arm", default="introact_full")
    ap.add_argument("--scale", default="xl", choices=list(SCALES))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--k", type=int, nargs="+", default=[10, 12, 15, 20])
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=None)
    ap.add_argument("--n-perm", dest="n_perm", type=int, default=20000)
    ap.add_argument("--out", default=str(ROOT / "results" / "spo_feasibility.json"))
    args = ap.parse_args()

    spec = SCALES[args.scale]
    spec.seed = args.seed
    windows = build_corpus(spec, source="ett")
    rows = load_traces(args.traces, args.arm)
    print(f"corpus {len(windows)} windows, traces {len(rows)} rows, "
          f"arm {args.arm}", flush=True)

    wids = [w.window_id for w in windows]
    trace_ids = {r["window_id"] for r in rows}
    overlap = len(set(wids) & trace_ids)
    print(f"window id overlap {overlap} of {len(wids)}", flush=True)
    if overlap < 0.99 * len(wids):
        raise SystemExit("corpus and traces do not line up, refusing to proceed")

    payload = {"arm": args.arm, "scale": args.scale, "seed": args.seed,
               "n_windows": len(windows), "by_k": {}}

    t0 = time.time()
    pn = profile_matrix(windows, n_jobs=args.n_jobs)
    print(f"profiles {pn.shape} in {time.time() - t0:.0f}s", flush=True)

    for k in args.k:
        labels = cluster_profiles(pn, k, args.seed)
        cells, skipped = build_cells(rows, labels, wids)
        tests = chi2_by_action(cells, k)

        occupied = len(cells)
        total_cells = k * len(MUTATING)
        n_all = sum(c["n"] for c in cells.values())
        thin = sum(1 for c in cells.values() if c["n"] < 5)

        print(f"\n=== k={k}  cells occupied {occupied} of {total_cells}, "
              f"candidates {n_all}, cells with n<5: {thin}, "
              f"windows not in corpus: {skipped}")
        print(f"{'cluster':>8s}" + "".join(f"{a:>26s}" for a in MUTATING))
        for c in range(k):
            line = f"{c:8d}"
            for a in MUTATING:
                cell = cells.get((c, a))
                if not cell or cell["n"] == 0:
                    line += f"{'-':>26s}"
                else:
                    rate = cell["accepted"] / cell["n"]
                    du = np.mean(cell["dU"]) if cell["dU"] else float("nan")
                    line += f"{cell['n']:>8d}{rate:>8.2f}{du:>10.2f}"
            print(line)

        print(f"\n{'operator':<12s}{'clusters':>9s}{'n':>7s}{'rate min':>10s}"
              f"{'rate max':>10s}{'chi2':>10s}{'p':>12s}{'exp<5':>7s}")
        for a in MUTATING:
            t = tests[a]
            if not t["testable"]:
                print(f"{a:<12s}  not testable, {t['reason']}")
                continue
            print(f"{a:<12s}{t['n_clusters']:9d}{t['n_candidates']:7d}"
                  f"{t['rate_min']:10.3f}{t['rate_max']:10.3f}{t['chi2']:10.2f}"
                  f"{t['p']:12.3e}{t['cells_expected_below_5']:7d}")

        # Permutation p, because several cells fall below the expected count
        # rule that the asymptotic chi square needs.
        print(f"\n{'operator':<12s}{'asymptotic p':>15s}{'permutation p':>16s}")
        for a in MUTATING:
            if not tests[a]["testable"]:
                continue
            pp = permutation_p(cells, k, a, args.n_perm, args.seed)
            tests[a]["p_permutation"] = pp
            print(f"{a:<12s}{tests[a]['p']:15.3e}{pp if pp is not None else float('nan'):16.4f}")

        empty = [(c, a) for c in range(k) for a in MUTATING if (c, a) not in cells]
        conf = stratum_confound(labels, windows, k)
        print(f"\nAMI(cluster, stratum) = {conf['ami']:.4f}, "
              f"1.0 means the clustering is the stratum label restated")
        print(f"empty cells never tried by the fixed policy: {len(empty)}")
        for c, a in empty:
            print(f"    cluster {c:2d}  {a:<10s} cluster size "
                  f"{conf['cluster_sizes'][c]}")

        payload["by_k"][str(k)] = {
            "cells_occupied": occupied, "cells_total": total_cells,
            "n_candidates": n_all, "cells_below_5": thin,
            "empty_cells": [[c, a] for c, a in empty],
            "grid": {f"{c}|{a}": {"n": v["n"], "accepted": v["accepted"],
                                  "mean_dU": float(np.mean(v["dU"])) if v["dU"] else None}
                     for (c, a), v in sorted(cells.items())},
            "tests": tests,
            "stratum_confound": conf,
        }

    Path(args.out).write_text(json.dumps(payload, indent=1, default=float),
                              encoding="utf-8")
    print(f"\nwritten to {args.out}")
    print("___SPO_FEASIBILITY_DONE___", flush=True)


if __name__ == "__main__":
    main()
