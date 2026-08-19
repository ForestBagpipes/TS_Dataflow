"""The SPO learning loop. Warm start, then learn on the training split.

What is new relative to every earlier run is only which candidate is tried
first, and how many probes each window is allowed. The proposer, the shield and
the operators are unchanged, so any difference in the outcome is attributable to
the ordering and the allocation rather than to a different action space.

Budget allocation runs before the episodes. Each window's expected return is the
best value any arm offers in its cluster, divided by the probe cost that cluster
has historically charged. Windows whose defect posterior is settled and points
at clean receive zero and are skipped outright, which is where the saving comes
from and is reported as such.

The two cells stage zero flagged as blind spots, cluster 1 and cluster 11 on
DENOISE, are reported separately. Their outcome is fixed by
docs/spo_preregistration.md before this script ran, in both directions.

Usage:
    python -u experiments/spo_learn.py --scale xl --device cuda
    python -u experiments/spo_learn.py --scale small --device cpu --surrogate
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
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

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_model_pool, make_pool  # noqa: E402
from introact_ts.spo import (ARMS, FIRST, SPOConfig, SPOPolicy,  # noqa: E402
                             ValueTables, allocate_budget)
from introact_ts.types import Action  # noqa: E402

#: Cells stage zero flagged as never visited by the fixed policy.
BLIND_SPOTS = [(1, Action.DENOISE), (11, Action.DENOISE)]

#: How far the clean hypothesis must lead the runner up for a window to be
#: skipped without probing. Fixed before the run.
MARGIN = 1.5

#: Probes per window when nothing better is known, used as the cost estimate
#: before any window in a cluster has been tried.
DEFAULT_COST = 2.0


def split_windows(windows):
    rng = np.random.RandomState(SPLIT_SEED)
    order = rng.permutation(len(windows))
    n_train = int(round(TRAIN_FRACTION * len(windows)))
    train = set(order[:n_train].tolist())
    return ([w for i, w in enumerate(windows) if i in train],
            [w for i, w in enumerate(windows) if i not in train],
            [i for i in order[:n_train]], [i for i in order[n_train:]])


def skip_mask(states, margin=MARGIN):
    """True where the defect posterior is settled and points at clean.

    Settled has to be defined relatively rather than absolutely. The posterior
    spreads over five hypotheses, so its maximum on the reference corpus reaches
    only 0.554 even on windows the perception stage labels clean, and an
    absolute threshold anywhere near certainty would never fire. What separates
    a settled window from an undecided one is how far clean leads the runner up,
    which on the same corpus is a usable signal: windows labelled clean carry a
    median clean mass of 0.421 against 0.173 on contaminated ones.

    So the rule is that clean must be the top hypothesis and must lead the
    second by at least ``margin`` times. This is the only place a window can be
    dropped without the shield ever seeing it, which is why it takes a lead
    rather than a bare maximum.
    """
    out = []
    for s in states:
        post = dict(getattr(s, "posterior", None) or {})
        if not post:
            out.append(False)
            continue
        clean = float(post.pop("clean", 0.0))
        runner = max(post.values()) if post else 0.0
        out.append(clean > 0.0 and clean >= margin * max(runner, 1e-9))
    return np.array(out, dtype=bool)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="xl", choices=list(SCALES))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--k", type=int, default=12)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--surrogate", action="store_true",
                    help="offline surrogate pool, for the smoke test")
    ap.add_argument("--budget-per-window", dest="bpw", type=float, default=2.0)
    ap.add_argument("--p-inject", dest="p_inject", type=float, default=0.05,
                    help="probability of forcing an unvisited operator in")
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=32)
    ap.add_argument("--warmstart",
                    default=str(ROOT / "results" / "spo_warmstart.json"))
    ap.add_argument("--expect-hash", dest="expect_hash", default="",
                    help="abort unless the config hashes to this")
    ap.add_argument("--out", default=str(ROOT / "results" / "spo_learn.json"))
    args = ap.parse_args()

    rel_out = str(Path(args.out).relative_to(ROOT)).replace("\\", "/")
    # The clip decides which rewards the policy ever sees, so leaving it out of
    # the hash would let it change without the assertion noticing.
    ws_peek = json.loads(Path(args.warmstart).read_text(encoding="utf-8"))
    cfg_dict = {"k": args.k, "split_seed": SPLIT_SEED, "corpus_seed": args.seed,
                "scale": args.scale, "alpha": 0.02, "c_u": 1.0, "c0": 0.01,
                "optimistic_init": 1.0, "warm_start_cap": 20, "tail_floor": 5,
                "reward_clip": float(ws_peek["config"]["reward_clip"]),
                "p_inject": args.p_inject}
    mon = Monitor("spo_learn", expects=[rel_out], config=cfg_dict,
                  require_pool=None if args.surrogate else 3,
                  require_clean_tree=False, beat_every=20.0,
                  expect_config_hash=(args.expect_hash or None))

    spec = SCALES[args.scale]
    spec.seed = args.seed
    windows = build_corpus(spec, source="ett")
    models = (make_model_pool() if args.surrogate
              else make_pool(PRESETS[args.preset]["curation"], device=args.device))
    mon.start(pool_size=len(models))
    print(f"corpus {len(windows)} windows, pool {len(models)}, "
          f"config {config_hash(cfg_dict)}", flush=True)

    # Clusters, in the same geometry the warm start used.
    pn = profile_matrix(windows, n_jobs=args.n_jobs)
    km = KMeans(n_clusters=args.k, n_init=10, random_state=args.seed).fit(pn)
    labels = km.labels_
    cent = km.cluster_centers_
    cent = cent / np.maximum(np.linalg.norm(cent, axis=1, keepdims=True), 1e-12)
    mapping, merged, sizes = merge_tail_clusters(labels, cent)
    mon.beat("clusters", done=1, total=6)

    # Warm start from the fixed policy's history on the training split only.
    ws = ws_peek
    clip = ws["config"]["reward_clip"]
    cfg = SPOConfig(reward_clip=clip)
    tables = ValueTables(n_clusters=args.k, cfg=cfg, cluster_map=mapping)
    for name, arr in ws["tables"]["Q"].items():
        tables.Q[name] = np.array(arr, dtype=np.float64)
        tables.N[name] = np.array(ws["tables"]["N"][name], dtype=np.int64)
        tables.optimistic[name] = np.array(ws["tables"]["optimistic"][name], dtype=bool)
    policy = SPOPolicy(tables, cfg, p_inject=args.p_inject)
    print(f"warm start loaded, reward clip {clip:.4f}, "
          f"p_inject {args.p_inject}", flush=True)

    tr_w, ev_w, tr_i, ev_i = split_windows(windows)
    print(f"train {len(tr_w)} windows, eval {len(ev_w)} windows", flush=True)

    agent = IntroActAgent(models, AgentConfig())
    t0 = time.time()
    states = agent.perceive(windows)
    print(f"perception {time.time() - t0:.0f}s", flush=True)
    mon.beat("perceive", done=2, total=6)

    # Budget allocation over the training split.
    tr_states = [states[i] for i in tr_i]
    tr_clusters = [int(labels[i]) for i in tr_i]
    skip = skip_mask(tr_states)
    costs = np.full(len(tr_i), DEFAULT_COST)
    total_budget = int(round(args.bpw * len(tr_i)))
    alloc = allocate_budget(tr_clusters, costs, tables, total_budget, skip_mask=skip)

    skipped = [(windows[i].stratum, windows[i].contamination)
               for i, s in zip(tr_i, skip) if s]
    print(f"budget {total_budget} probes over {len(tr_i)} windows, "
          f"skipped {int(skip.sum())}, allocated {int(alloc.sum())}", flush=True)
    mon.beat("budget", done=3, total=6)

    # Learning pass over the training split.
    t0 = time.time()
    traces, used = [], 0
    for n, (gi, w) in enumerate(zip(tr_i, tr_w)):
        b = int(alloc[n])
        if b <= 0:
            continue
        tr = agent.curate_window(w, states[gi], peer_idx=gi,
                                 policy=policy, cluster=int(labels[gi]), budget=b)
        traces.append(tr)
        used += tr.probe_calls
        if (n + 1) % 100 == 0:
            mon.beat("learning", done=n + 1, total=len(tr_i),
                     probes_used=used, decisions=tables.t)
    print(f"learning pass {time.time() - t0:.0f}s, {len(traces)} windows curated, "
          f"{used} probes, {tables.t} decisions", flush=True)
    mon.beat("learned", done=5, total=6)

    # Blind spot cells, reported whichever way they came out.
    blind = {}
    rep = policy.report()
    for c, arm in BLIND_SPOTS:
        j = tables.resolve(c)
        key = f"{FIRST}|{j}|{arm.value}"
        cell = rep.get(key)
        a = ARMS.index(arm)
        blind[f"cluster{c}_{arm.value}"] = {
            "cluster": c, "resolved_to": j, "cluster_size": int(sizes[c]),
            "visits": cell["visits"] if cell else 0,
            "accepts": cell["accepts"] if cell else 0,
            "accept_rate": cell["accept_rate"] if cell else None,
            "mean_reward": cell["mean_reward"] if cell else None,
            "q_start": float(ws["tables"]["Q"][FIRST][j][a]),
            "q_end": float(tables.Q[FIRST][j, a]),
            "q_trace": cell["q_trace"] if cell else [],
        }
    print("\nblind spot cells flagged by stage zero")
    for k_, v in blind.items():
        print(f"  {k_:22s} visits {v['visits']:4d} accepts {v['accepts']:3d} "
              f"rate {v['accept_rate'] if v['accept_rate'] is not None else float('nan'):.3f} "
              f"Q {v['q_start']:+.4f} -> {v['q_end']:+.4f}")

    payload = {
        "config": cfg_dict, "config_hash": config_hash(cfg_dict),
        "surrogate": bool(args.surrogate), "pool_size": len(models),
        "n_windows": len(windows), "n_train": len(tr_w), "n_eval": len(ev_w),
        "cluster_sizes": sizes.tolist(),
        "merged_clusters": {str(k_): v for k_, v in merged.items()},
        "budget": {"total": total_budget, "allocated": int(alloc.sum()),
                   "used": used, "skipped": int(skip.sum()),
                   "skipped_by_stratum": dict(Counter(s for s, _ in skipped)),
                   "skipped_by_contamination": dict(
                       Counter(c or "none" for _, c in skipped))},
        "decisions": tables.t,
        "p_inject": args.p_inject,
        "injections": policy.injection_report(),
        "n_injected": int(sum(policy.injected.values())),
        "blind_spots": blind,
        "cells": rep,
        "tables_after": tables.snapshot(),
    }
    Path(args.out).write_text(json.dumps(payload, indent=1, default=float),
                              encoding="utf-8")
    mon.finish(git_add=False)
    print("___SPO_LEARN_DONE___", flush=True)


if __name__ == "__main__":
    main()
