"""The published proposers, through the same acceptance layer.

Symmetric with `gating.py` in every respect that matters: the same corpus, the
same acceptance rule, the same thresholds, the same metrics, and the same
manifest. The only difference is where the candidate edits come from.

These two proposers rewrite values in place rather than selecting from an
operator vocabulary, so a candidate edit is the whole repaired series rather
than a named operator with parameters. The acceptance layer does not care: it
scores a candidate against the working copy and commits or rolls back. The
structural distance is computed with the global weight profile, which is the
correct choice for an operator that touches every point, and is the same
profile the denoising operator receives.

Parameters follow the rule fixed in docs/classic_proposers.md before any
selection was made: take the setting that maximises the proposer's repair.

Usage:
    python -u experiments/gating_classic.py --device cuda --n 800
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from audit import _nmse  # noqa: E402
from corpus import CorpusSpec, OOD_KINDS, build_corpus  # noqa: E402
from proposers_classic import (estimate_speed_bounds, imr_repair,  # noqa: E402
                               imr_repair_supervised, screen_repair)

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.calibration import RISK_WEIGHTS, recalibrate_one  # noqa: E402
from introact_ts.probe import (SIGNAL_NAMES, ProbeConfig,  # noqa: E402
                               probe_window, reference_scale)
from introact_ts.structure import GLOBAL_WEIGHTS, structure_distortion  # noqa: E402
from introact_ts.types import Action, Verdict  # noqa: E402
from introact_ts.verify import (VerifyConfig, action_risk,  # noqa: E402
                                improvement_consistency, improvement_depth,
                                verify)

PROTECTED = ("clean", "hard", "rare_valid", "changepoint", "clean_ood")

#: Settings chosen by the pre registered rule, maximise repair. The discarded
#: settings are recorded in docs/classic_proposers.md with their numbers.
SELECTED = {
    "screen": dict(window=5),
    "imr": dict(p=5, max_iter=40),
    "imr_seeded": dict(p=5, max_iter=40, clean_prefix_frac=0.1),
}


def build_proposers(windows):
    s_min, s_max = estimate_speed_bounds([w.series for w in windows])
    return {
        "screen": lambda s: screen_repair(s, s_min, s_max, **SELECTED["screen"]),
        "imr": lambda s: imr_repair(s, **SELECTED["imr"]),
        "imr_seeded": lambda s: imr_repair_supervised(s, **SELECTED["imr_seeded"]),
    }, (s_min, s_max)


def gate_whole_series(window, state, models, candidate, agent, peer_idx, cfg):
    """Score one whole series candidate and accept or reject it.

    Returns (series, accepted, record). The candidate is treated as a single
    global edit, which it is.
    """
    work = np.asarray(window.series, dtype=np.float64)
    cand = np.asarray(candidate, dtype=np.float64)
    if cand.shape != work.shape or np.allclose(
            np.nan_to_num(cand), np.nan_to_num(work), rtol=0, atol=1e-12):
        return work.copy(), False, {"verdict": "NO_OP"}

    scale = reference_scale(window.series)
    center = agent._calib.centers[peer_idx]
    spread = agent._calib.spreads[peer_idx]
    z_now = agent._calib.z[peer_idx]

    after = probe_window(cand, models, scale, ProbeConfig())
    delta_u = after.utility - state.utility
    z_after, _ = recalibrate_one(after.vector, center, spread,
                                 SIGNAL_NAMES, RISK_WEIGHTS)
    report = structure_distortion(work, cand, Action.DENOISE, {},
                                  weights=GLOBAL_WEIGHTS)
    consistency = improvement_consistency(z_now, z_after)
    depth = improvement_depth(z_now, z_after)
    # Cost is the fraction of points the proposer rewrote, which is the same
    # quantity our own operators report.
    changed = float(np.mean(~np.isclose(np.nan_to_num(cand),
                                        np.nan_to_num(work), atol=1e-12)))
    risk = action_risk(depth, changed, consistency)
    verdict = verify(delta_u, report.distortion, risk, cfg)
    rec = {"verdict": str(verdict).split(".")[-1],
           "delta_utility": float(delta_u),
           "distortion": float(report.distortion), "risk": float(risk),
           "fraction_changed": changed}
    if verdict is Verdict.ACCEPTED:
        return cand.copy(), True, rec
    return work.copy(), False, rec


def score(rows, windows, form):
    from collections import Counter
    byid = {w.window_id: w for w in windows}
    dmg, before, after = [], [], []
    n_mod = prot = worsened = correct = total = 0
    per_form = Counter()
    for r in rows:
        w = byid[r["window_id"]]
        if r["changed"]:
            n_mod += 1
            total += 1
            if w.stratum in PROTECTED:
                prot += 1
                if form.get(w.window_id):
                    per_form[form[w.window_id]] += 1
            elif w.stratum == "contaminated":
                correct += 1
        rv = float(np.var(w.clean_series - np.median(w.clean_series)))
        a = _nmse(r["series"], w.clean_series, rv)
        b = _nmse(w.series, w.clean_series, rv)
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
    ap.add_argument("--tau", type=float, default=0.02)
    args = ap.parse_args()

    n = args.n
    spec = CorpusSpec(
        n_contaminated=int(n * 0.35), n_clean=int(n * 0.20),
        n_hard=int(n * 0.1125), n_rare_valid=int(n * 0.1125),
        n_changepoint=int(n * 0.1125), n_clean_ood=int(n * 0.1125), seed=42)
    windows = build_corpus(spec, source="ett")
    oodw = [w for w in windows if w.stratum == "clean_ood"]
    form = {w.window_id: OOD_KINDS[i % len(OOD_KINDS)] for i, w in enumerate(oodw)}

    models = make_pool(PRESETS["multi-family"]["curation"], device=args.device)
    cfg = VerifyConfig(tau=args.tau)
    agent = IntroActAgent(models, AgentConfig(verification=cfg))
    t0 = time.time()
    states = agent.perceive(windows)
    print(f"{len(windows)} windows, perceive {time.time() - t0:.0f}s", flush=True)

    proposers, bounds = build_proposers(windows)
    print(f"speed bounds estimated at 1st and 99th percentile: "
          f"{bounds[0]:.4f} to {bounds[1]:.4f}", flush=True)

    results, decisions, audit = {}, {}, {}
    for name, fn in proposers.items():
        t0 = time.time()
        raw_rows, gated_rows, recs = [], [], []
        for i, (w, s) in enumerate(zip(windows, states)):
            cand = fn(w.series)
            changed_raw = not np.allclose(np.nan_to_num(cand),
                                          np.nan_to_num(w.series), atol=1e-12)
            raw_rows.append({"window_id": w.window_id, "series": cand,
                             "changed": changed_raw})
            series, acc, rec = gate_whole_series(w, s, models, cand, agent, i, cfg)
            gated_rows.append({"window_id": w.window_id, "series": series,
                               "changed": acc})
            recs.append(rec)
        results[name] = score(raw_rows, windows, form)
        results[f"{name}_gated"] = score(gated_rows, windows, form)
        from collections import Counter
        decisions[name] = dict(Counter(r["verdict"] for r in recs))
        # Per window record, so a veto can be audited offline against the
        # pristine series without occupying the card again.
        audit[name] = [
            {"window_id": int(w.window_id), "stratum": w.stratum,
             "contamination": w.contamination,
             "verdict": rec["verdict"],
             "delta_utility": rec.get("delta_utility"),
             "distortion": rec.get("distortion"),
             "risk": rec.get("risk"),
             "nmse_before": float(_nmse(w.series, w.clean_series,
                                        float(np.var(w.clean_series
                                              - np.median(w.clean_series))))),
             "nmse_candidate": float(_nmse(cand_row["series"], w.clean_series,
                                           float(np.var(w.clean_series
                                                 - np.median(w.clean_series)))))}
            for w, rec, cand_row in zip(windows, recs, raw_rows)
        ]
        print(f"  {name:12s} {time.time() - t0:.0f}s  verdicts {decisions[name]}",
              flush=True)

    print()
    print(f"{'method':22s}{'damage':>9s}{'repair':>9s}{'edits':>7s}"
          f"{'prot.edits':>12s}{'precision':>11s}{'worsened':>10s}")
    order = ["screen", "screen_gated", "imr", "imr_gated",
             "imr_seeded", "imr_seeded_gated"]
    for k in order:
        if k not in results:
            continue
        r = results[k]
        print(f"{k:22s}{r['mean_damage']:9.4f}{r['repair_reduction']:+9.3f}"
              f"{r['n_modified']:7d}{r['protected_edits']:12d}"
              f"{r['edit_precision']:11.3f}{r['windows_worsened']:10d}")

    payload = {"results": results, "decisions": decisions, "audit": audit,
               "speed_bounds": list(bounds), "selected_parameters": SELECTED,
               "selection_rule": "maximise the proposer's repair, damage ignored"}
    (ROOT / "results" / "gating_classic.json").write_text(
        json.dumps(payload, indent=1, default=float), encoding="utf-8")
    print("___GATING_CLASSIC_DONE___", flush=True)


if __name__ == "__main__":
    main()
