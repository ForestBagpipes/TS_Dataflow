"""Does widening the candidate pool give the policy anything to choose between.

The ablation ladder found the learned policy changing the path and not the
destination: it opened with a different operator on 14 percent of windows and
reached a different endpoint on 0.17 percent. The diagnosis is in
`docs/number_selfchecks.md` and it is not the table size. The proposer is a
deterministic router, one dominant defect to one operator, so on 79.2 percent of
windows it offers zero or one operator and the upper confidence bound has
nothing to rank.

This probe asks whether widening the pool changes that, at a cost of minutes
rather than the four GPU hours a full rerun would take. Two knobs, swept
together:

  secondary_threshold   evidence a co-occurring defect must carry before its
                        operator joins the list. Default 1.6
  add_fallback          append a low strength DENOISE on any routed window, so
                        there is always a second arm

Three numbers decide it, and the third is a floor rather than a target:

  choice share    windows offering the policy two or more operators. Currently
                  0.208 on xl. Below about 0.4 the policy still cannot act
  endpoint gap    windows where the learned policy ends somewhere the fixed
                  rule does not. Currently 0.0017
  damage rate     must stay under 0.20. A wider pool means more attempts, and
                  if the extra attempts get committed rather than refused the
                  shield is not doing its job

Perception is computed once and shared by every configuration, which is what
makes the sweep cheap: the cost is one perception plus two short arms per cell.

Usage:
    python -u experiments/probe_candidate_pool.py --scale small --source mixed \
        --seed 0 --device cuda
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from corpus import build_corpus  # noqa: E402
from run_agent import SCALES  # noqa: E402
from run_ablations import cluster_labels  # noqa: E402
from run_main import score_rows  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.policy import PolicyConfig, propose_actions  # noqa: E402
from introact_ts.spo import ARMS, SPOConfig, SPOPolicy, ValueTables  # noqa: E402
from introact_ts.verify import VerifyConfig  # noqa: E402

#: The grid. Thresholds below the default, plus the fallback on and off.
THRESHOLDS = [1.6, 1.2, 1.0, 0.8, 0.6, 0.4]
FALLBACKS = [False, True]


def choice_share(states, pcfg):
    """Windows whose first step offers two or more distinct operators.

    Measured on the proposer directly rather than on a trace, so it is the pool
    the policy is handed rather than what survived execution. `history` is empty
    because this is the opening decision, which is the one the bound ranks.
    """
    n_multi = n_any = 0
    sizes = []
    for st in states:
        cands = propose_actions(st, [], pcfg)
        ops = {a for a, _ in cands if a in ARMS}
        sizes.append(len(ops))
        if ops:
            n_any += 1
        if len(ops) >= 2:
            n_multi += 1
    n = max(len(states), 1)
    return {"share_two_or_more": n_multi / n, "share_any": n_any / n,
            "mean_operators": sum(sizes) / n}


def run_arm(models, windows, states, reference, pcfg, tau, n_jobs,
            policy=None, clusters=None):
    agent = IntroActAgent(models, AgentConfig(
        verification=VerifyConfig(tau=tau), policy=pcfg, n_jobs=n_jobs))
    agent._calib = reference._calib
    agent._ood = reference._ood
    agent._reference = reference._reference
    return [agent.curate_window(
                w, s, peer_idx=i, policy=policy,
                cluster=int(clusters[i]) if policy is not None else None)
            for i, (w, s) in enumerate(zip(windows, states))]


def endpoint_gap(a, b, windows):
    """Windows where two arms finish in a different state."""
    import numpy as np
    byid = {w.window_id: w for w in windows}
    ta = {t.window_id: t for t in a}
    diff = 0
    for wid, t in ta.items():
        u = next((x for x in b if x.window_id == wid), None)
        if u is None:
            continue
        w = byid[wid]
        xa = np.asarray(t.final_series, dtype=np.float64)
        xb = np.asarray(u.final_series, dtype=np.float64)
        if (t.crop_offset != u.crop_offset or xa.shape != xb.shape
                or not np.allclose(xa, xb, atol=1e-12, equal_nan=True)):
            diff += 1
    return diff / max(len(ta), 1)


def evaluate(models, windows, states, reference, clusters, pcfg, args):
    """One configuration on one seed, the four criteria plus the diagnostics."""
    fixed = run_arm(models, windows, states, reference, pcfg, args.tau,
                    args.n_jobs)
    cfg = SPOConfig()
    tables = ValueTables(n_clusters=args.k, cfg=cfg)
    policy = SPOPolicy(tables, cfg, p_inject=args.p_inject, seed=args.seed)
    policy.shaped_reward = True
    learned = run_arm(models, windows, states, reference, pcfg, args.tau,
                      args.n_jobs, policy=policy, clusters=clusters)

    row_l = score_rows(learned, windows)
    row_f = score_rows(fixed, windows)
    # Did the retry loop actually run. A write to either non first table means
    # the policy made a second decision after a refusal, which is the thing the
    # ladder exists to create.
    import numpy as np
    from introact_ts.spo import AFTER_STRUCT, AFTER_UTIL, FIRST
    later = int(sum((tables.N[t] > cfg.optimistic_visits).sum()
                    for t in (AFTER_STRUCT, AFTER_UTIL)))
    first = int((tables.N[FIRST] > cfg.optimistic_visits).sum())
    verdicts = [r.verdict for t in learned for r in t.records]
    names = [getattr(v, "value", v) for v in verdicts]
    n_adj = sum(1 for n in names if n != "NO_OP")
    positive = sum(1 for n in names if n == "ACCEPTED")
    attempts = sum(1 for t in learned for r in t.records
                   if getattr(r.action, "value", r.action)
                   in ("IMPUTE", "DESPIKE", "DENOISE", "RESEGMENT"))
    return {
        "endpoint_gap": endpoint_gap(learned, fixed, windows),
        "damage_rate": row_l["damage_rate"],
        "damage_rate_fixed": row_f["damage_rate"],
        "committed_edits": row_l["committed_edits"],
        "protected_mis_edit_rate": row_l["protected_mis_edit_rate"],
        "repair_nrmsd": row_l["repair_nrmsd"],
        "repair_nrmsd_fixed": row_f["repair_nrmsd"],
        "cells_first": first, "cells_after_refusal": later,
        "positive_reward_share": positive / max(n_adj, 1),
        "attempts_per_window": attempts / max(len(windows), 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="small", choices=list(SCALES))
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--seeds", default="0,1,2,3,4")
    ap.add_argument("--tau", type=float, default=0.02)
    ap.add_argument("--k", type=int, default=12)
    ap.add_argument("--p-inject", dest="p_inject", type=float, default=0.05)
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=16)
    ap.add_argument("--thresholds", nargs="*", type=float,
                    default=[1.6, 1.0, 0.6])
    ap.add_argument("--ladder", nargs="*", type=int, default=[0, 1],
                    help="0 runs the routed proposer, 1 runs the ladder")
    ap.add_argument("--out", default=str(ROOT / "results" / "candidate_pool_probe.json"))
    args = ap.parse_args()

    seeds = [int(x) for x in args.seeds.replace(" ", "").split(",") if x]
    models = None
    rows = []

    print(f"{'ladder':>7s}{'thr':>6s}{'seed':>5s}{'choice':>8s}{'ops':>7s}"
          f"{'gap':>8s}{'damage':>8s}{'nrmsd L':>9s}{'nrmsd F':>9s}"
          f"{'cells2':>8s}{'pos rw':>8s}{'att/win':>8s}", flush=True)
    for seed in seeds:
        spec = SCALES[args.scale]
        spec.seed = seed
        windows = build_corpus(spec, source=args.source)
        if models is None:
            models = make_pool(PRESETS[args.preset]["curation"],
                               device=args.device)
        reference = IntroActAgent(models, AgentConfig(
            verification=VerifyConfig(tau=args.tau), n_jobs=args.n_jobs))
        t0 = time.time()
        states = reference.perceive(windows)
        clusters = cluster_labels(windows, args.k, seed=seed,
                                  n_jobs=args.n_jobs)
        print(f"seed {seed}, {len(windows)} windows, "
              f"perception {time.time() - t0:.0f}s", flush=True)
        args.seed = seed

        for lad in args.ladder:
            for thr in args.thresholds:
                pcfg = PolicyConfig(secondary_threshold=thr,
                                    enable_param_ladder=bool(lad))
                pool = choice_share(states, pcfg)
                rec = {"seed": seed, "ladder": bool(lad),
                       "secondary_threshold": thr, **pool}
                rec.update(evaluate(models, windows, states, reference,
                                    clusters, pcfg, args))
                rows.append(rec)
                nl = rec["repair_nrmsd"] or float("nan")
                nf = rec["repair_nrmsd_fixed"] or float("nan")
                print(f"{lad:7d}{thr:6.1f}{seed:5d}"
                      f"{pool['share_two_or_more']:8.3f}"
                      f"{pool['mean_operators']:7.2f}"
                      f"{rec['endpoint_gap']:8.4f}"
                      f"{rec['damage_rate']:8.4f}{nl:9.4f}{nf:9.4f}"
                      f"{rec['cells_after_refusal']:8d}"
                      f"{rec['positive_reward_share']:8.3f}"
                      f"{rec['attempts_per_window']:8.3f}", flush=True)

    # The four criteria, evaluated per configuration across seeds.
    print()
    print("criteria per configuration, across seeds")
    print(f"{'ladder':>7s}{'thr':>6s}{'gap mean':>10s}{'damage mean':>13s}"
          f"{'nrmsd L':>9s}{'nrmsd F':>9s}{'L wins':>8s}{'verdict':>9s}")
    import numpy as np
    summary = []
    keys = sorted({(r["ladder"], r["secondary_threshold"]) for r in rows})
    for lad, thr in keys:
        sub = [r for r in rows if r["ladder"] == lad
               and r["secondary_threshold"] == thr]
        gap = float(np.mean([r["endpoint_gap"] for r in sub]))
        dmg = float(np.mean([r["damage_rate"] for r in sub]))
        nl = [r["repair_nrmsd"] for r in sub if r["repair_nrmsd"]]
        nf = [r["repair_nrmsd_fixed"] for r in sub if r["repair_nrmsd_fixed"]]
        wins = sum(1 for r in sub
                   if r["repair_nrmsd"] is not None
                   and r["repair_nrmsd_fixed"] is not None
                   and r["repair_nrmsd"] < r["repair_nrmsd_fixed"] - 1e-12)
        ties = sum(1 for r in sub
                   if r["repair_nrmsd"] is not None
                   and r["repair_nrmsd_fixed"] is not None
                   and abs(r["repair_nrmsd"] - r["repair_nrmsd_fixed"]) <= 1e-12)
        ok = (gap > 0.05 and dmg <= 0.15
              and np.mean(nl) < np.mean(nf) and wins + ties >= len(sub) - 1
              and wins >= 1)
        summary.append({"ladder": lad, "secondary_threshold": thr,
                        "gap": gap, "damage": dmg,
                        "nrmsd_learned": float(np.mean(nl)) if nl else None,
                        "nrmsd_fixed": float(np.mean(nf)) if nf else None,
                        "wins": wins, "ties": ties, "n": len(sub),
                        "passes": bool(ok)})
        print(f"{int(lad):7d}{thr:6.1f}{gap:10.4f}{dmg:13.4f}"
              f"{np.mean(nl) if nl else float('nan'):9.4f}"
              f"{np.mean(nf) if nf else float('nan'):9.4f}"
              f"{wins:4d}/{len(sub):<3d}{'PASS' if ok else 'fail':>9s}")

    Path(args.out).write_text(json.dumps(
        {"scale": args.scale, "source": args.source, "seeds": seeds,
         "rows": rows, "summary": summary}, indent=1, default=float),
        encoding="utf-8")
    print()
    print("___POOL_PROBE_DONE___", flush=True)


if __name__ == "__main__":
    main()
