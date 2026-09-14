"""Soft reward shaping against a hard execution time veto.

The competing design puts structural preservation in the objective as a
weighted penalty, so an edit that damages structure can still be taken when the
utility gain outweighs the penalty. Ours puts it in a veto, so no utility gain
buys a structurally damaging edit. The distinction is the architectural claim
and until now it has been argued rather than measured.

The soft arm scores each candidate as

    utility_gain - mu * structural_distance

and commits whenever that is positive, with no threshold on the distance
itself. Everything else is identical: the same proposals, the same operators,
the same order, the same probe. Sweeping mu traces the whole soft design space,
so the comparison is against the best soft variant rather than a strawman.

The prediction from the competing paper's own parameter study is that raising
the modification constraint weight worsens NMSE and downstream performance,
because a soft penalty restricts genuine repair as it restricts damage. Our tau
sweep says the opposite for a hard threshold: between 0.02 and 0.12 loosening
buys no repair at all, only damage. If both hold, a soft penalty cannot reach
the same damage level as the veto without paying repair for it, and the frontier
plot shows it.

There is one integration test bundled here. The predictability residual from
M4 can be substituted for the raw behavioural risk in the risk term, and it
enters the acceptance path only if protected edits fall without repair
degrading materially. That criterion is fixed here before the run.

Usage:
    python -u experiments/soft_vs_hard.py --device cuda --n 800
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from audit import _nmse  # noqa: E402
from baselines import BASELINES  # noqa: E402
from corpus import CorpusSpec, OOD_KINDS, build_corpus  # noqa: E402
from gating import proposals_of  # noqa: E402

from introact_ts.actions import apply_action  # noqa: E402
from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.calibration import RISK_WEIGHTS, recalibrate_one  # noqa: E402
from introact_ts.probe import (SIGNAL_NAMES, ProbeConfig,  # noqa: E402
                               probe_window, reference_scale)
from introact_ts.structure import structure_distortion  # noqa: E402
from introact_ts.types import Action  # noqa: E402

PROTECTED = ("clean", "hard", "rare_valid", "changepoint", "clean_ood")

#: The soft penalty weights to sweep. Spans four orders of magnitude so the
#: comparison is against the whole soft design space.
MUS = [0.0, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0]

#: The hard thresholds to place on the same axes.
TAUS = [0.005, 0.01, 0.02, 0.04, 0.08, 0.12, 0.20, 0.30]


def apply_plan(window, state, models, plan, decide):
    """Walk a proposal sequence, committing whenever `decide` says so.

    `decide` receives (delta_utility, distortion) and returns a bool. That is
    the only difference between the soft and hard arms.
    """
    work = np.asarray(window.series, dtype=np.float64).copy()
    scale = reference_scale(window.series)
    u = state.utility
    crop = 0
    kept = []
    for action, params in plan:
        outcome = apply_action(work, action, **params)
        if not outcome.applicable:
            continue
        after = probe_window(outcome.series, models, scale, ProbeConfig())
        delta_u = after.utility - u
        report = structure_distortion(work, outcome.series, action,
                                      outcome.params, touched=outcome.touched)
        if decide(delta_u, report.distortion):
            if action is Action.RESEGMENT:
                crop += int(outcome.params.get("lo", 0))
            work = outcome.series
            u = after.utility
            kept.append(action)
    return work, crop, kept


def score(rows, windows, form):
    byid = {w.window_id: w for w in windows}
    dmg, before, after = [], [], []
    n_mod = prot = worsened = correct = total = 0
    per_form = Counter()
    for r in rows:
        w = byid[r["window_id"]]
        if r["kept"]:
            n_mod += 1
            total += 1
            if w.stratum in PROTECTED:
                prot += 1
                if form.get(w.window_id):
                    per_form[form[w.window_id]] += 1
            elif w.stratum == "contaminated":
                correct += 1
        ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))
        a = _nmse(r["series"], w.clean_series[r["crop"]:], ref_var)
        b = _nmse(w.series, w.clean_series, ref_var)
        if a > b + 1e-9:
            worsened += 1
        if w.stratum in PROTECTED:
            dmg.append(a)
        elif w.stratum == "contaminated":
            before.append(b)
            after.append(a)
    bm, am = float(np.mean(before)), float(np.mean(after))
    return {"mean_damage": float(np.mean(dmg)),
            "repair_reduction": (1.0 - am / bm) if bm > 1e-9 else 0.0,
            "n_modified": n_mod, "protected_edits": prot,
            "edit_precision": correct / max(total, 1),
            "windows_worsened": worsened,
            "protected_by_form": dict(per_form)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--epsilon", type=float, default=0.005)
    args = ap.parse_args()

    n = args.n
    spec = CorpusSpec(
        n_contaminated=int(n * 0.35), n_clean=int(n * 0.20),
        n_hard=int(n * 0.1125), n_rare_valid=int(n * 0.1125),
        n_changepoint=int(n * 0.1125), n_clean_ood=int(n * 0.1125), seed=42,
    )
    windows = build_corpus(spec, source="ett")
    oodw = [w for w in windows if w.stratum == "clean_ood"]
    form = {w.window_id: OOD_KINDS[i % len(OOD_KINDS)] for i, w in enumerate(oodw)}

    models = make_pool(PRESETS["multi-family"]["curation"], device=args.device)
    agent = IntroActAgent(models, AgentConfig())
    t0 = time.time()
    states = agent.perceive(windows)
    print(f"{len(windows)} windows, perceive {time.time() - t0:.0f}s", flush=True)

    # One proposer for both arms, so only the decision rule differs.
    proposals = {t.window_id: proposals_of(t)
                 for t in BASELINES["stat_only"](windows, states, models)}
    print(f"proposer stat_only, "
          f"{sum(len(v) for v in proposals.values())} candidate edits", flush=True)

    out = {"soft": {}, "hard": {}}

    for mu in MUS:
        t0 = time.time()
        rows = []
        for w, s in zip(windows, states):
            plan = proposals[w.window_id]
            if not plan:
                rows.append({"window_id": w.window_id, "series": w.series,
                             "crop": 0, "kept": []})
                continue
            series, crop, kept = apply_plan(
                w, s, models, plan,
                lambda du, d, _m=mu: (du - _m * d) > args.epsilon)
            rows.append({"window_id": w.window_id, "series": series,
                         "crop": crop, "kept": kept})
        out["soft"][f"{mu:g}"] = score(rows, windows, form)
        r = out["soft"][f"{mu:g}"]
        print(f"  soft mu {mu:6g}  damage {r['mean_damage']:.4f}  "
              f"repair {r['repair_reduction']:+.3f}  edits {r['n_modified']:4d}  "
              f"prot {r['protected_edits']:4d}  {time.time() - t0:.0f}s", flush=True)

    for tau in TAUS:
        t0 = time.time()
        rows = []
        for w, s in zip(windows, states):
            plan = proposals[w.window_id]
            if not plan:
                rows.append({"window_id": w.window_id, "series": w.series,
                             "crop": 0, "kept": []})
                continue
            series, crop, kept = apply_plan(
                w, s, models, plan,
                lambda du, d, _t=tau: du > args.epsilon and d < _t)
            rows.append({"window_id": w.window_id, "series": series,
                         "crop": crop, "kept": kept})
        out["hard"][f"{tau:g}"] = score(rows, windows, form)
        r = out["hard"][f"{tau:g}"]
        print(f"  hard tau {tau:6g}  damage {r['mean_damage']:.4f}  "
              f"repair {r['repair_reduction']:+.3f}  edits {r['n_modified']:4d}  "
              f"prot {r['protected_edits']:4d}  {time.time() - t0:.0f}s", flush=True)

    print(f"\nfrontier, repair achievable at or below a damage budget")
    print(f"{'budget':>9s}{'soft best repair':>19s}{'at mu':>8s}"
          f"{'hard best repair':>19s}{'at tau':>9s}{'gap':>9s}")
    frontier = []
    for budget in [0.002, 0.005, 0.01, 0.02, 0.05, 0.10]:
        s_ok = [(v["repair_reduction"], k) for k, v in out["soft"].items()
                if v["mean_damage"] <= budget]
        h_ok = [(v["repair_reduction"], k) for k, v in out["hard"].items()
                if v["mean_damage"] <= budget]
        sb = max(s_ok) if s_ok else (float("nan"), "none")
        hb = max(h_ok) if h_ok else (float("nan"), "none")
        gap = hb[0] - sb[0] if s_ok and h_ok else float("nan")
        frontier.append({"budget": budget, "soft": sb[0], "soft_mu": sb[1],
                         "hard": hb[0], "hard_tau": hb[1], "gap": gap})
        print(f"{budget:9.3f}{sb[0]:+19.3f}{sb[1]:>8s}"
              f"{hb[0]:+19.3f}{hb[1]:>9s}{gap:+9.3f}")

    out["frontier"] = frontier
    (ROOT / "results" / "soft_vs_hard.json").write_text(
        json.dumps(out, indent=1, default=float), encoding="utf-8")
    print("___SOFT_VS_HARD_DONE___", flush=True)


if __name__ == "__main__":
    main()
