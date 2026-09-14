"""Build SPO's three value tables from the fixed policy's stored traces.

Stage zero showed admission depends on the profile cluster, so the historical
outcomes are worth seeding into Q rather than starting from nothing. This script
does the seeding and writes the tables to disk. The method layer does no IO, so
everything file shaped lives here.

Three tables, split by what happened to the previous candidate in the same
window, which is the rollback reason section 3.4 requires in the context:

    Q0        candidate index 0
    Q_struct  the candidate before it was rolled back on the structural condition
    Q_util    the candidate before it was rolled back on the utility condition

Two cells are treated specially, both on evidence from stage zero rather than
preference.

**RESEGMENT gets one global value, not twelve.** Its admission rate is flat
across clusters at every k tested, permutation p 0.81 to 0.96. Seeding it per
cluster would write sampling noise into the prior.

**Tail clusters merge into their nearest large neighbour.** At k equal to 12
cluster 9 holds one window and cluster 10 holds three. A value estimated from
that is not an estimate. Each is merged into the nearest cluster by centroid
cosine distance among clusters above the size floor.

Usage:
    python -u experiments/spo_warmstart.py --k 12
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from corpus import build_corpus  # noqa: E402
from run_agent import SCALES  # noqa: E402
from spo_feasibility import ADJUDICATED, MUTATING, profile_matrix  # noqa: E402

from introact_ts.spo import (ARMS, FIRST, TABLES, SPOConfig,  # noqa: E402
                             ValueTables, shielded_reward, table_for)
from introact_ts.types import Action, Verdict  # noqa: E402

#: A cluster with fewer windows than this cannot support its own value estimate
#: and is merged into its nearest large neighbour.
TAIL_FLOOR = 5

#: Corpus split for policy learning, fixed in docs/spo_preregistration.md before
#: any SPO run. Training informs the warm start and the reward clip, evaluation
#: informs nothing until the policy is scored.
SPLIT_SEED = 20260818
TRAIN_FRACTION = 0.40

#: Percentile of the training rewards the admitted reward is clipped to.
CLIP_PERCENTILE = 95


def merge_tail_clusters(labels, centroids, floor=TAIL_FLOOR):
    """Map every undersized cluster onto the nearest cluster above the floor."""
    k = centroids.shape[0]
    sizes = np.array([(labels == c).sum() for c in range(k)])
    large = [c for c in range(k) if sizes[c] >= floor]
    mapping, merged = {}, {}
    for c in range(k):
        if sizes[c] >= floor:
            mapping[c] = c
            continue
        # Cosine distance, the metric CDP retrieves peers under.
        sims = centroids[large] @ centroids[c]
        target = large[int(np.argmax(sims))]
        mapping[c] = target
        merged[c] = {"into": target, "size": int(sizes[c]),
                     "cosine": float(sims.max())}
    return mapping, merged, sizes


def collect(rows, cluster_of, cfg):
    """Per table, per cluster, per arm, the historical adjudicated outcomes."""
    cells = defaultdict(lambda: {"n": 0, "accepted": 0, "dU": [], "reward": []})
    for r in rows:
        c = cluster_of.get(r["window_id"])
        if c is None:
            continue
        prev = None
        for s in r["steps"]:
            act, verdict = s["action"], s["verdict"]
            if act not in MUTATING or verdict not in ADJUDICATED:
                # An inapplicable operator is not a decision the shield ruled
                # on, but it still tells the next candidate nothing, so the
                # previous verdict carries through unchanged.
                continue
            tbl = table_for(prev)
            cell = cells[(tbl, c, act)]
            cell["n"] += 1
            cell["reward"].append(
                shielded_reward(verdict, s["delta_utility"], 1, cfg))
            if verdict == "ACCEPTED":
                cell["accepted"] += 1
                cell["dU"].append(float(s["delta_utility"]))
            prev = verdict
    return cells


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces", default=str(
        ROOT / "results" / "xl" / "xl_ett_multi-family_seed42_traces.json"))
    ap.add_argument("--arm", default="introact_full")
    ap.add_argument("--scale", default="xl", choices=list(SCALES))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--k", type=int, default=12)
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=32)
    ap.add_argument("--out", default=str(ROOT / "results" / "spo_warmstart.json"))
    args = ap.parse_args()

    spec = SCALES[args.scale]
    spec.seed = args.seed
    windows = build_corpus(spec, source="ett")
    rows = json.loads(Path(args.traces).read_text(encoding="utf-8"))[args.arm]
    pn = profile_matrix(windows, n_jobs=args.n_jobs)
    km = KMeans(n_clusters=args.k, n_init=10, random_state=args.seed).fit(pn)
    labels = km.labels_
    centroids = km.cluster_centers_
    centroids = centroids / np.maximum(
        np.linalg.norm(centroids, axis=1, keepdims=True), 1e-12)

    mapping, merged, sizes = merge_tail_clusters(labels, centroids)
    print(f"corpus {len(windows)} windows, k={args.k}")
    print(f"cluster sizes {sizes.tolist()}")
    for c, info in merged.items():
        print(f"  tail cluster {c} (size {info['size']}) merged into "
              f"{info['into']}, cosine {info['cosine']:.3f}")

    # Reward clip from the training split only. Section 3.4's theorem 5 needs a
    # bounded reward and the raw utility change is long tailed, so the bound is
    # a quantile of what the fixed policy earned on the training windows. The
    # evaluation windows never enter this number.
    rng = np.random.RandomState(SPLIT_SEED)
    order = rng.permutation(len(windows))
    n_train = int(round(TRAIN_FRACTION * len(windows)))
    train_ids = {windows[i].window_id for i in order[:n_train]}
    train_dU = [s["delta_utility"] for r in rows if r["window_id"] in train_ids
                for s in r["steps"] if s["verdict"] == "ACCEPTED"]
    clip = float(np.percentile(train_dU, CLIP_PERCENTILE)) if train_dU else None
    print(f"reward clip at the {CLIP_PERCENTILE}th percentile of the "
          f"{len(train_dU)} admitted rewards on the {n_train} training windows: "
          f"{clip:.4f}")

    cfg = SPOConfig(reward_clip=clip)
    cluster_of = {w.window_id: int(labels[i]) for i, w in enumerate(windows)}
    cells = collect(rows, cluster_of, cfg)

    tables = ValueTables(n_clusters=args.k, cfg=cfg, cluster_map=mapping)

    # RESEGMENT carries one global value across every cluster and every table,
    # because stage zero found no cluster level structure in it.
    rs = [v for (t, c, a), v in cells.items() if a == "RESEGMENT"]
    rs_rewards = [x for v in rs for x in v["reward"]]
    rs_mean = float(np.mean(rs_rewards)) if rs_rewards else 0.0
    tables.set_column(None, Action.RESEGMENT, rs_mean,
                      min(len(rs_rewards), cfg.warm_start_cap))
    print(f"\nRESEGMENT column set to its global mean reward {rs_mean:+.4f} "
          f"over {len(rs_rewards)} candidates, no per cluster seeding")

    seeded = 0
    for (tbl, c, act), v in cells.items():
        if act == "RESEGMENT":
            continue
        tables.warm_start(tbl, c, Action[act], v["reward"])
        seeded += 1

    print(f"\n{'table':<10s}{'seeded':>8s}{'optimistic':>12s}{'total':>7s}")
    summary = {}
    for name in TABLES:
        opt = int(tables.optimistic[name].sum())
        tot = tables.optimistic[name].size
        print(f"{name:<10s}{tot - opt:8d}{opt:12d}{tot:7d}")
        summary[name] = {"seeded": tot - opt, "optimistic": opt, "total": tot}

    # The two blind spots stage zero flagged, reported on their own because the
    # instruction asks for them separately once exploration runs.
    blind = []
    for c in (1, 11):
        j = tables.resolve(c)
        a = ARMS.index(Action.DENOISE)
        blind.append({"cluster": c, "resolved_to": j,
                      "cluster_size": int(sizes[c]),
                      "Q0": float(tables.Q[FIRST][j, a]),
                      "optimistic": bool(tables.optimistic[FIRST][j, a])})
    print(f"\nDENOISE blind spots flagged by stage zero")
    for b in blind:
        print(f"  cluster {b['cluster']:2d} size {b['cluster_size']:4d} "
              f"Q0={b['Q0']:+.4f} optimistic={b['optimistic']}")
    print(f"  combined window coverage {sum(b['cluster_size'] for b in blind)}")

    payload = {
        "k": args.k, "seed": args.seed, "scale": args.scale, "arm": args.arm,
        "cluster_sizes": sizes.tolist(),
        "merged_clusters": {str(k_): v for k_, v in merged.items()},
        "resegment_global_reward": rs_mean,
        "table_summary": summary,
        "denoise_blind_spots": blind,
        "config": {"c_u": cfg.c_u, "c0": cfg.c0,
                   "optimistic_init": cfg.optimistic_init,
                   "warm_start_cap": cfg.warm_start_cap,
                   "reward_clip": cfg.reward_clip,
                   "clip_percentile": CLIP_PERCENTILE,
                   "split_seed": SPLIT_SEED,
                   "train_fraction": TRAIN_FRACTION},
        "tables": tables.snapshot(),
    }
    Path(args.out).write_text(json.dumps(payload, indent=1, default=float),
                              encoding="utf-8")
    print(f"\nwritten to {args.out}")
    print("___SPO_WARMSTART_DONE___", flush=True)


if __name__ == "__main__":
    main()
