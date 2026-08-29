"""Do the ladder's parameter rungs differ in the shield's eyes.

Before spending an hour widening the value table's action dimension, this asks
the question that decides whether widening it can possibly help: **on the same
window, does the same operator at three different parameter settings produce
three different verdicts, or three different repairs.**

If the rungs are indistinguishable to the shield, then letting the policy rank
them cannot change what gets committed, and the extension is wasted work. If
they differ, the policy has a real choice to learn and the extension is the way
to give it one.

Each rung is executed in the sandbox exactly as `Agent.curate_window` executes
a candidate: apply the operator to the untouched window, re probe, recalibrate
against the same peers, measure structural distortion, and put the three
numbers through `verify`. Nothing here is a proxy. The one difference from the
agent's loop is that every rung starts from the pristine window rather than
from whatever an earlier accepted edit left, which is what makes the three
comparable to each other.

Three tables come out, and the three criteria are read off them:

  a  acceptance rate differs across rungs by at least 5 points on some operator
  b  on windows where more than one rung is accepted, their repairs differ
  c  windows where an aggressive rung is refused and a gentler one is accepted
     are more than 10 percent

Criterion c is the one that matters most. It counts windows the current design
loses outright and the ladder would recover, and it is also the only one of the
three that produces a different endpoint rather than a different path.

Usage:
    python -u experiments/tier_discrimination.py --scale small --source mixed \
        --seed 0 --device cuda
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from corpus import build_corpus  # noqa: E402
from run_ablations import cluster_labels  # noqa: E402
from run_agent import SCALES  # noqa: E402

from introact_ts.actions import apply_action, robust_scale  # noqa: E402
from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.calibration import RISK_WEIGHTS, recalibrate_one  # noqa: E402
from introact_ts.policy import LADDER, _at_rung  # noqa: E402
from introact_ts.probe import (SIGNAL_NAMES, ProbeConfig,  # noqa: E402
                               probe_window, reference_scale)
from introact_ts.structure import structure_distortion  # noqa: E402
from introact_ts.types import Action, Verdict  # noqa: E402
from introact_ts.verify import (VerifyConfig, action_risk,  # noqa: E402
                                improvement_consistency, improvement_depth,
                                verify)

RUNGS = ("aggressive", "default", "conservative")


def nrmsd(series, clean, crop, scale):
    if clean is None:
        return None
    a = np.asarray(series, dtype=np.float64)
    b = np.asarray(clean, dtype=np.float64)[crop:crop + len(a)]
    n = min(len(a), len(b))
    if n == 0:
        return None
    d = a[:n] - b[:n]
    d = d[np.isfinite(d)]
    if d.size == 0:
        return None
    return float(np.sqrt(np.mean(d ** 2))) / max(scale, 1e-9)


def measure(window, state, models, agent, peer_idx, action, params):
    """Execute one candidate in the sandbox and return the shield's inputs.

    Split from the verdict on purpose. The three signals do not depend on tau,
    so a tau sweep re judges these numbers instead of re executing, which turns
    four sweeps into one execution pass.
    """
    work = np.asarray(window.series, dtype=np.float64)
    scale = reference_scale(window.series)
    center = agent._calib.centers[peer_idx]
    spread = agent._calib.spreads[peer_idx]

    outcome = apply_action(work, action, **params)
    if not outcome.applicable:
        return {"applicable": False, "note": outcome.note}

    after = probe_window(outcome.series, models, scale, ProbeConfig())
    delta_u = after.utility - state.utility
    z_after, _ = recalibrate_one(after.vector, center, spread, SIGNAL_NAMES,
                                 RISK_WEIGHTS)
    report = structure_distortion(work, outcome.series, action, outcome.params,
                                  touched=outcome.touched)
    consistency = improvement_consistency(state.z, z_after)
    depth = improvement_depth(state.z, z_after)
    risk = action_risk(depth, outcome.cost, consistency)
    crop = int(outcome.params.get("lo", 0)) if action is Action.RESEGMENT else 0
    sc = max(float(robust_scale(work)), 1e-9)
    return {
        "applicable": True,
        "delta_utility": float(delta_u),
        "struct_distortion": float(report.distortion),
        "risk": float(risk),
        "nrmsd": nrmsd(outcome.series, window.clean_series, crop, sc),
        # How far this rung moved the window at all, so a rung that changed
        # nothing is distinguishable from one that changed something the shield
        # happened to refuse.
        "moved": float(np.nanmax(np.abs(
            np.asarray(outcome.series, dtype=np.float64)[:len(work)]
            - work[:len(outcome.series)]))) if len(outcome.series) else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="small", choices=list(SCALES))
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--taus", nargs="*", type=float,
                    default=[0.02, 0.03, 0.05, 0.08])
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=16)
    ap.add_argument("--k", type=int, default=12)
    ap.add_argument("--out", default=str(ROOT / "results" / "tier_discrimination.json"))
    args = ap.parse_args()

    spec = SCALES[args.scale]
    spec.seed = args.seed
    windows = build_corpus(spec, source=args.source)
    models = make_pool(PRESETS[args.preset]["curation"], device=args.device)
    base = VerifyConfig(tau=args.taus[0])
    agent = IntroActAgent(models, AgentConfig(verification=base,
                                              n_jobs=args.n_jobs))
    states = agent.perceive(windows)
    clusters = cluster_labels(windows, args.k, seed=args.seed,
                              n_jobs=args.n_jobs)
    print(f"{len(windows)} windows, taus {args.taus}, {args.k} clusters",
          flush=True)

    # One execution pass. The three signals do not depend on tau.
    rows = []
    for i, (w, st) in enumerate(zip(windows, states)):
        for action in LADDER:
            per = {r: measure(w, st, models, agent, i, action,
                              _at_rung(action, r)) for r in RUNGS}
            rows.append({"window_id": int(w.window_id), "stratum": w.stratum,
                         "contamination": w.contamination,
                         "cluster": int(clusters[i]),
                         "action": action.value, "rungs": per})
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(windows)} windows", flush=True)

    # Operators that never executed at all, which no tau can rescue.
    print()
    print("applicability, independent of tau")
    print(f"{'operator':12s}{'rows':>7s}{'all rungs ran':>15s}"
          f"{'none ran':>11s}{'top reason':>34s}")
    applic = {}
    for action in sorted({r["action"] for r in rows}):
        sub = [r for r in rows if r["action"] == action]
        ran = [r for r in sub if all(r["rungs"][k]["applicable"] for k in RUNGS)]
        none = [r for r in sub
                if not any(r["rungs"][k]["applicable"] for k in RUNGS)]
        notes = Counter(r["rungs"][k].get("note", "")
                        for r in none for k in RUNGS
                        if not r["rungs"][k]["applicable"])
        top = notes.most_common(1)[0][0] if notes else ""
        applic[action] = {"rows": len(sub), "all_ran": len(ran),
                          "none_ran": len(none), "notes": dict(notes)}
        print(f"{action:12s}{len(sub):7d}{len(ran):15d}{len(none):11d}"
              f"{top[:33]:>34s}")

    def judge_at(rec, tau):
        if not rec["applicable"]:
            return None
        cfg = VerifyConfig(tau=tau)
        return verify(rec["delta_utility"], rec["struct_distortion"],
                      rec["risk"], cfg)

    print()
    print("tau sweep")
    print(f"{'tau':>6s}{'all refused':>13s}{'two or more ok':>16s}"
          f"{'aggr no, soft yes':>19s}"
          + "".join(f"{a[:9]:>11s}" for a in sorted(applic)))
    sweep = []
    for tau in args.taus:
        combos = Counter()
        per_action = defaultdict(lambda: Counter())
        reasons = Counter()
        for r in rows:
            if not all(r["rungs"][k]["applicable"] for k in RUNGS):
                continue
            pat = []
            for k in RUNGS:
                v = judge_at(r["rungs"][k], tau)
                pat.append(v is Verdict.ACCEPTED)
                if v is not None and v is not Verdict.ACCEPTED:
                    reasons[v.value] += 1
                per_action[r["action"]][k] += int(v is Verdict.ACCEPTED)
            per_action[r["action"]]["n"] += 1
            combos[tuple(pat)] += 1
        total = max(sum(combos.values()), 1)
        allref = combos[(False, False, False)] / total
        two_plus = sum(n for pat, n in combos.items() if sum(pat) >= 2) / total
        recover = sum(n for pat, n in combos.items()
                      if not pat[0] and (pat[1] or pat[2])) / total
        rates = {}
        for a in sorted(applic):
            c = per_action[a]
            rates[a] = (c["conservative"] / c["n"]) if c["n"] else float("nan")
        sweep.append({"tau": tau, "all_refused": allref,
                      "two_or_more": two_plus, "recoverable": recover,
                      "conservative_rate": rates,
                      "refusal_reasons": dict(reasons),
                      "combos": {str(k): v for k, v in combos.items()}})
        print(f"{tau:6.3f}{allref:13.4f}{two_plus:16.4f}{recover:19.4f}"
              + "".join(f"{rates[a]:11.4f}" for a in sorted(applic)))
    print("the per operator columns are the conservative rung's acceptance rate")

    print()
    print("why a candidate was refused, by tau")
    print(f"{'tau':>6s}{'utility':>10s}{'structure':>11s}{'risk':>8s}")
    for rec in sweep:
        r = rec["refusal_reasons"]
        tot = max(sum(r.values()), 1)
        print(f"{rec['tau']:6.3f}"
              f"{r.get('ROLLED_BACK_UTILITY', 0) / tot:10.4f}"
              f"{r.get('ROLLED_BACK_STRUCTURE', 0) / tot:11.4f}"
              f"{r.get('ROLLED_BACK_RISK', 0) / tot:8.4f}")

    # The cluster level reading. If the rung that works best depends on which
    # cluster a window belongs to, then a policy over clusters has something to
    # learn that a policy over a single window's candidate list does not.
    ref_tau = args.taus[0]
    print()
    print(f"best rung per cluster and operator at tau {ref_tau:g}, "
          f"by acceptance then by repair")
    print(f"{'cluster':>8s}{'n':>5s}" + "".join(f"{a[:11]:>13s}"
                                                for a in sorted(applic)))
    per_cluster = {}
    for cl in sorted({r["cluster"] for r in rows}):
        sub = [r for r in rows if r["cluster"] == cl]
        n_win = len({r["window_id"] for r in sub})
        cells = {}
        for action in sorted(applic):
            rs = [r for r in sub if r["action"] == action]
            scored = {}
            for rung in RUNGS:
                ok = [r for r in rs if r["rungs"][rung]["applicable"]
                      and judge_at(r["rungs"][rung], ref_tau) is Verdict.ACCEPTED]
                if not ok:
                    continue
                vals = [r["rungs"][rung]["nrmsd"] for r in ok
                        if r["rungs"][rung]["nrmsd"] is not None]
                scored[rung] = (len(ok), -float(np.mean(vals)) if vals else 0.0)
            cells[action] = (max(scored, key=scored.get) if scored else "none")
        per_cluster[cl] = {"n_windows": n_win, "best": cells}
        print(f"{cl:8d}{n_win:5d}"
              + "".join(f"{cells[a][:11]:>13s}" for a in sorted(applic)))

    # How many operators have a cluster dependent answer.
    varies = {}
    for action in sorted(applic):
        picks = {per_cluster[c]["best"][action] for c in per_cluster
                 if per_cluster[c]["best"][action] != "none"}
        varies[action] = sorted(picks)
    print()
    print("distinct best rungs across clusters, per operator")
    for a, v in varies.items():
        print(f"  {a:12s}{len(v)} distinct  {v}")
    n_varying = sum(1 for v in varies.values() if len(v) >= 2)
    print(f"operators whose best rung depends on the cluster: {n_varying} "
          f"of {len(varies)}")

    best = [s for s in sweep if s["two_or_more"] > 0.15]
    print()
    if best:
        b = min(best, key=lambda x: x["tau"])
        print(f"criterion met at tau {b['tau']:g}: two or more rungs "
              f"acceptable on {b['two_or_more']:.4f} of windows")
    else:
        top = max(sweep, key=lambda x: x["two_or_more"])
        print(f"no tau reaches 0.15. Best is {top['two_or_more']:.4f} at tau "
              f"{top['tau']:g}, so the structural threshold is not the binding "
              f"constraint")

    Path(args.out).write_text(json.dumps(
        {"scale": args.scale, "seed": args.seed, "taus": args.taus,
         "applicability": applic, "sweep": sweep,
         "per_cluster": per_cluster, "best_rung_varies": varies}, indent=1,
        default=float),
        encoding="utf-8")
    print()
    print("___TIER_DISCRIMINATION_DONE___", flush=True)


if __name__ == "__main__":
    main()
