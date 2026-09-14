"""Does the reward clip percentile change what the policy does.

The clip exists because theorem 5's regret bound assumes a bounded reward and
the measured utility change is long tailed. The threshold was set at the 95th
percentile of the training rewards, and that choice was made after looking at
the reward distribution, so it needs a sensitivity check rather than an
assertion that it does not matter.

This sweeps 90, 95 and 99 and reports two things per level.

**What the tables hold.** How many admissions were actually clipped, and how far
the seeded values move.

**What the policy does with them.** For every window, the arm the upper
confidence bound selects from its cluster's row. If the selected arm is the same
across all three levels for almost every window, the downstream conclusions
cannot depend on the level. This is the policy behaviour available before the
learning loop is wired in, and it is the part the clip could plausibly distort,
since the clip only ever changes a Q value and Q values only ever matter through
the argmax.

Agreement is reported two ways, the fraction of windows whose selected arm is
identical, and Kendall tau between the full per cluster arm orderings, because
two levels could agree on the argmax while disagreeing on everything below it.

Usage:
    python -u experiments/spo_clip_sensitivity.py
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import stats
from sklearn.cluster import KMeans

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tools"))

from corpus import build_corpus  # noqa: E402
from monitor import Monitor, config_hash  # noqa: E402
from run_agent import SCALES  # noqa: E402
from spo_feasibility import profile_matrix  # noqa: E402
from spo_warmstart import (CLIP_PERCENTILE, SPLIT_SEED, TRAIN_FRACTION,  # noqa: E402
                           collect, merge_tail_clusters)

from introact_ts.spo import (ARMS, FIRST, TABLES, SPOConfig,  # noqa: E402
                             ValueTables)
from introact_ts.types import Action  # noqa: E402

LEVELS = (90, 95, 99)


def build_tables(rows, cluster_of, mapping, k, clip):
    cfg = SPOConfig(reward_clip=clip)
    cells = collect(rows, cluster_of, cfg)
    tables = ValueTables(n_clusters=k, cfg=cfg, cluster_map=mapping)
    rs = [x for (t, c, a), v in cells.items() if a == "RESEGMENT" for x in v["reward"]]
    tables.set_column(None, Action.RESEGMENT,
                      float(np.mean(rs)) if rs else 0.0,
                      min(len(rs), cfg.warm_start_cap))
    for (tbl, c, act), v in cells.items():
        if act == "RESEGMENT":
            continue
        tables.warm_start(tbl, c, Action[act], v["reward"])
    return tables


def selected_arms(tables, labels, t_value):
    """The arm the bound picks per window, with every arm feasible."""
    tables.t = t_value
    feasible = set(ARMS)
    return np.array([ARMS.index(tables.select(FIRST, int(c), feasible))
                     for c in labels])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces", default=str(
        ROOT / "results" / "xl" / "xl_ett_multi-family_seed42_traces.json"))
    ap.add_argument("--arm", default="introact_full")
    ap.add_argument("--scale", default="xl", choices=list(SCALES))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--k", type=int, default=12)
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=32)
    ap.add_argument("--out", default=str(ROOT / "results" / "spo_clip_sensitivity.json"))
    args = ap.parse_args()

    rel_out = str(Path(args.out).relative_to(ROOT)).replace("\\", "/")
    mon = Monitor("spo_clip_sensitivity", expects=[rel_out],
                  config={"k": args.k, "split_seed": SPLIT_SEED,
                          "levels": list(LEVELS), "seed": args.seed},
                  require_clean_tree=False, beat_every=10.0)
    mon.start()

    spec = SCALES[args.scale]
    spec.seed = args.seed
    windows = build_corpus(spec, source="ett")
    rows = json.loads(Path(args.traces).read_text(encoding="utf-8"))[args.arm]
    mon.beat("profiles", done=0, total=len(LEVELS))

    pn = profile_matrix(windows, n_jobs=args.n_jobs)
    km = KMeans(n_clusters=args.k, n_init=10, random_state=args.seed).fit(pn)
    labels = km.labels_
    cent = km.cluster_centers_
    cent = cent / np.maximum(np.linalg.norm(cent, axis=1, keepdims=True), 1e-12)
    mapping, _, sizes = merge_tail_clusters(labels, cent)
    cluster_of = {w.window_id: int(labels[i]) for i, w in enumerate(windows)}

    # Training split only, same rule and same seed as the warm start.
    rng = np.random.RandomState(SPLIT_SEED)
    order = rng.permutation(len(windows))
    n_train = int(round(TRAIN_FRACTION * len(windows)))
    train_ids = {windows[i].window_id for i in order[:n_train]}
    train_dU = np.array([s["delta_utility"] for r in rows
                         if r["window_id"] in train_ids
                         for s in r["steps"] if s["verdict"] == "ACCEPTED"])
    all_dU = np.array([s["delta_utility"] for r in rows
                       for s in r["steps"] if s["verdict"] == "ACCEPTED"])

    per_level, tables_by_level = {}, {}
    print(f"{'pct':>5s}{'clip':>10s}{'clipped':>9s}{'of':>6s}{'share':>8s}"
          f"{'meanQ0':>10s}{'maxQ0':>10s}")
    for i, pct in enumerate(LEVELS):
        clip = float(np.percentile(train_dU, pct))
        tables = build_tables(rows, cluster_of, mapping, args.k, clip)
        tables_by_level[pct] = tables
        q0 = tables.Q[FIRST]
        n_clipped = int((all_dU > clip).sum())
        per_level[pct] = {
            "clip": clip, "n_clipped": n_clipped, "n_admitted": int(all_dU.size),
            "clipped_share": n_clipped / max(all_dU.size, 1),
            "Q0_mean": float(q0.mean()), "Q0_max": float(q0.max()),
        }
        print(f"{pct:5d}{clip:10.4f}{n_clipped:9d}{all_dU.size:6d}"
              f"{n_clipped / all_dU.size:8.3f}{q0.mean():10.4f}{q0.max():10.4f}")
        mon.beat("levels", done=i + 1, total=len(LEVELS))

    # Policy behaviour. t is the horizon the confidence width is evaluated at,
    # taken as the corpus size so the widths match a full pass.
    t_value = len(windows)
    sel = {pct: selected_arms(tables_by_level[pct], labels, t_value)
           for pct in LEVELS}

    print(f"\nselected arm distribution over {len(windows)} windows, t={t_value}")
    print(f"{'pct':>5s}" + "".join(f"{a.value:>12s}" for a in ARMS))
    for pct in LEVELS:
        c = Counter(sel[pct])
        print(f"{pct:5d}" + "".join(f"{c.get(i, 0):12d}" for i in range(len(ARMS))))

    print(f"\npairwise agreement")
    print(f"{'pair':>10s}{'same arm':>11s}{'kendall tau':>14s}{'tau p':>10s}")
    agree = {}
    for a in LEVELS:
        for b in LEVELS:
            if a >= b:
                continue
            same = float((sel[a] == sel[b]).mean())
            qa = tables_by_level[a].Q[FIRST].ravel()
            qb = tables_by_level[b].Q[FIRST].ravel()
            tau, p = stats.kendalltau(qa, qb)
            agree[f"{a}v{b}"] = {"same_arm_fraction": same,
                                 "kendall_tau": float(tau), "tau_p": float(p)}
            print(f"{a:4d}v{b:<5d}{same:11.4f}{tau:14.4f}{p:10.2e}")

    payload = {
        "k": args.k, "seed": args.seed, "levels": list(LEVELS),
        "n_windows": len(windows), "t_value": t_value,
        "n_train_windows": n_train,
        "reward_percentiles": {str(q): float(np.percentile(all_dU, q))
                               for q in (50, 90, 95, 99, 100)},
        "per_level": {str(k_): v for k_, v in per_level.items()},
        "selected_arm_counts": {
            str(pct): {ARMS[i].value: int((sel[pct] == i).sum())
                       for i in range(len(ARMS))} for pct in LEVELS},
        "agreement": agree,
    }
    Path(args.out).write_text(json.dumps(payload, indent=1, default=float),
                              encoding="utf-8")
    mon.finish(git_add=False)
    print("___CLIP_SENSITIVITY_DONE___", flush=True)


if __name__ == "__main__":
    main()
