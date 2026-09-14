"""Bolting the acceptance rule onto someone else's proposer.

The claim under test is that the acceptance rule is a module rather than a part
of our agent. If it is, wrapping it around a different proposer should cut the
damage that proposer does to protected data while keeping most of its repair.

The gated arm runs the same operators the baseline chose, in the same order,
with the same parameters. The only difference is that each edit is applied to a
sandbox copy, scored, and kept only if it passes the same three conditions the
full agent uses, with the same calibration, the same tau and the same epsilon.
Nothing is re proposed and no operator is substituted, so any difference is
attributable to the gate and not to a different search.

AegisTS is the proposer this was built for. Its public repository is missing the
`Datasets` module that all four of its core modules import, so it cannot be run
as published, and the request to its authors is in
`researched_papers/aegists/ISSUE_TO_SEND.md`. Until that is resolved the
proposers here are our own baselines, which is enough to test the modularity
claim itself.

Usage:
    python -u experiments/gating.py --device cuda --n 800
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
from baselines import BASELINES, DEFECT_TO_ACTION  # noqa: E402
from corpus import CorpusSpec, OOD_KINDS, build_corpus  # noqa: E402

from introact_ts.actions import apply_action  # noqa: E402
from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.calibration import RISK_WEIGHTS, recalibrate_one  # noqa: E402
from introact_ts.probe import (SIGNAL_NAMES, ProbeConfig,  # noqa: E402
                                probe_window, reference_scale)
from introact_ts.structure import structure_distortion  # noqa: E402
from introact_ts.types import Action, Verdict  # noqa: E402
from introact_ts.verify import (VerifyConfig, action_risk,  # noqa: E402
                                improvement_consistency, improvement_depth,
                                verify)

PROTECTED = ("clean", "hard", "rare_valid", "changepoint", "clean_ood")


def proposals_of(trace) -> list:
    """The operator sequence a baseline committed, as (action, params)."""
    return [(r.action, dict(r.params)) for r in trace.records]


def gate(window, state, models, plan, agent, peer_idx, cfg, audit=None):
    """Run one proposal sequence through the acceptance rule.

    Returns the curated series, the crop offset, and one record per proposal
    saying whether it survived.
    """
    work = np.asarray(window.series, dtype=np.float64).copy()
    scale = reference_scale(window.series)
    center = agent._calib.centers[peer_idx]
    spread = agent._calib.spreads[peer_idx]
    z_now = agent._calib.z[peer_idx]
    u = state.utility
    crop_offset = 0
    kept, decisions = [], []

    for action, params in plan:
        outcome = apply_action(work, action, **params)
        if not outcome.applicable:
            decisions.append({"action": str(action), "verdict": "NOT_APPLICABLE"})
            continue
        after = probe_window(outcome.series, models, scale, ProbeConfig())
        delta_u = after.utility - u
        z_after, _ = recalibrate_one(after.vector, center, spread,
                                     SIGNAL_NAMES, RISK_WEIGHTS)
        report = structure_distortion(work, outcome.series, action,
                                      outcome.params, touched=outcome.touched)
        consistency = improvement_consistency(z_now, z_after)
        depth = improvement_depth(z_now, z_after)
        risk = action_risk(depth, outcome.cost, consistency)
        verdict = verify(delta_u, report.distortion, risk, cfg)
        decisions.append({
            "action": str(action).split(".")[-1], "verdict": str(verdict).split(".")[-1],
            "delta_utility": float(delta_u), "distortion": float(report.distortion),
            "risk": float(risk),
        })
        if audit is not None and window.clean_series is not None:
            # Incremental harm: would committing this candidate leave the window
            # worse than the working copy it would replace. Judged against the
            # pristine series, aligned on the span each side actually covers.
            ref = np.asarray(window.clean_series, dtype=np.float64)
            rv = float(np.var(ref - np.median(ref)))
            base_off = crop_offset
            cand_off = crop_offset + (int(outcome.params.get("lo", 0))
                                      if action is Action.RESEGMENT else 0)
            nb = _nmse(work, ref[base_off:base_off + len(work)], rv)
            na = _nmse(outcome.series,
                       ref[cand_off:cand_off + len(outcome.series)], rv)
            audit.append({
                "window_id": int(window.window_id), "stratum": window.stratum,
                "contamination": window.contamination,
                "action": str(action).split(".")[-1],
                "verdict": str(verdict).split(".")[-1],
                "nmse_before": float(nb), "nmse_candidate": float(na),
                "harmful": bool(na > nb + 1e-9),
            })
        if verdict is Verdict.ACCEPTED:
            if action is Action.RESEGMENT:
                crop_offset += int(outcome.params.get("lo", 0))
            work = outcome.series
            u = after.utility
            z_now = z_after
            kept.append(action)
    return work, crop_offset, kept, decisions


def score(rows, windows):
    """Damage, repair, and the columns the competitor never measured."""
    byid = {w.window_id: w for w in windows}
    dmg, before, after = [], [], []
    n_mod = 0
    prot_edits = 0
    worsened = 0
    correct_edits = 0
    total_edits = 0
    per_form = Counter()

    for r in rows:
        w = byid[r["window_id"]]
        if r["kept"]:
            n_mod += 1
            total_edits += 1
            if w.stratum in PROTECTED:
                prot_edits += 1
                if r.get("form"):
                    per_form[r["form"]] += 1
            elif w.stratum == "contaminated":
                correct_edits += 1
        if w.clean_series is None:
            continue
        ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))
        a = _nmse(r["series"], w.clean_series[r["crop_offset"]:], ref_var)
        b = _nmse(w.series, w.clean_series, ref_var)
        if a > b + 1e-9:
            worsened += 1
        if w.stratum in PROTECTED:
            dmg.append(a)
        elif w.stratum == "contaminated":
            before.append(b)
            after.append(a)

    bm, am = float(np.mean(before)), float(np.mean(after))
    return {
        "mean_damage": float(np.mean(dmg)) if dmg else 0.0,
        "repair_reduction": (1.0 - am / bm) if bm > 1e-9 else 0.0,
        "n_modified": n_mod,
        "protected_edits": prot_edits,
        "edit_precision": correct_edits / max(total_edits, 1),
        "windows_worsened": worsened,
        "protected_edits_by_ood_form": dict(per_form),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--tau", type=float, default=0.02)
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
    cfg = VerifyConfig(tau=args.tau)
    agent = IntroActAgent(models, AgentConfig(verification=cfg))
    t0 = time.time()
    states = agent.perceive(windows)
    print(f"{len(windows)} windows, perceive {time.time() - t0:.0f}s, "
          f"tau {args.tau}", flush=True)

    results, all_decisions, audit_all = {}, {}, {}

    def rows_from(traces):
        return [{"window_id": t.window_id, "series": t.final_series,
                 "crop_offset": t.crop_offset,
                 "kept": [r.action for r in t.records if r.accepted],
                 "form": form.get(t.window_id)}
                for t in traces]

    # no_action, the reference bound
    results["no_action"] = score(rows_from(BASELINES["no_action"](windows, states, models)),
                                 windows)
    print(f"  no_action done", flush=True)

    for name in ["stat_only", "always_clean"]:
        t0 = time.time()
        traces = BASELINES[name](windows, states, models)
        rows = [{"window_id": t.window_id, "series": t.final_series,
                 "crop_offset": t.crop_offset,
                 "kept": [r.action for r in t.records],
                 "form": form.get(t.window_id)} for t in traces]
        results[name] = score(rows, windows)
        print(f"  {name} {time.time() - t0:.0f}s", flush=True)

        # gated arm: same proposals, filtered
        t0 = time.time()
        grows, decs, audit_rows = [], [], []
        byid = {w.window_id: (w, s, i)
                for i, (w, s) in enumerate(zip(windows, states))}
        for t in traces:
            w, s, idx = byid[t.window_id]
            plan = proposals_of(t)
            if not plan:
                grows.append({"window_id": w.window_id, "series": w.series,
                              "crop_offset": 0, "kept": [], "form": form.get(w.window_id)})
                continue
            series, crop, kept, d = gate(w, s, models, plan, agent, idx, cfg,
                                         audit=audit_rows)
            grows.append({"window_id": w.window_id, "series": series,
                          "crop_offset": crop, "kept": kept,
                          "form": form.get(w.window_id)})
            decs.extend(d)
        results[f"{name}_gated"] = score(grows, windows)
        all_decisions[name] = Counter(x["verdict"] for x in decs)
        audit_all[name] = audit_rows
        print(f"  {name}_gated {time.time() - t0:.0f}s  "
              f"verdicts {dict(all_decisions[name])}", flush=True)

    t0 = time.time()
    traces = [agent.curate_window(w, s, peer_idx=i)
              for i, (w, s) in enumerate(zip(windows, states))]
    results["introact_full"] = score(rows_from(traces), windows)
    print(f"  introact_full {time.time() - t0:.0f}s", flush=True)

    print()
    print(f"{'method':22s}{'damage':>9s}{'repair':>9s}{'edits':>7s}"
          f"{'prot.edits':>12s}{'precision':>11s}{'worsened':>10s}")
    order = ["no_action", "stat_only", "stat_only_gated", "always_clean",
             "always_clean_gated", "introact_full"]
    for k in order:
        if k not in results:
            continue
        r = results[k]
        if k == "no_action":
            print("-- reference bound, does not curate")
        print(f"{k:22s}{r['mean_damage']:9.4f}{r['repair_reduction']:+9.3f}"
              f"{r['n_modified']:7d}{r['protected_edits']:12d}"
              f"{r['edit_precision']:11.3f}{r['windows_worsened']:10d}")
        if k == "no_action":
            print("-- methods that edit")

    print("\nprotected edits landing on clean_ood, by form")
    for k in order:
        if k in results and results[k]["protected_edits_by_ood_form"]:
            print(f"  {k:22s}{results[k]['protected_edits_by_ood_form']}")

    (ROOT / "results" / "gating.json").write_text(
        json.dumps({"results": {k: dict(v) for k, v in results.items()},
                    "audit": audit_all},
                   indent=1, default=float), encoding="utf-8")
    print("___GATING_DONE___", flush=True)


if __name__ == "__main__":
    main()
