"""Route-conditioned level-shift replay.

Applies several level-shift repair strategies only to windows that the existing
proposer would route to RESEGMENT, then runs each candidate through the same
frozen TSFM, structure, risk and verify stack used by smoke350.

Ground-truth `true_kind` and `dataset` are used only for stratified reporting,
never for deciding whether to run an operator.

This script is intentionally experimental: it adds no new Action to
`src/introact_ts` and keeps the frozen TSFM and shield unchanged.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

# Pin the project cache before any backend imports try to reach the network.
os.environ.setdefault("HF_HOME", "/root/autodl-tmp/.cache/huggingface")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from build_calibration import build as build_calibration  # noqa: E402
from metrics_common import canonical_nmse, repair_rmsd, ref_var  # noqa: E402
from introact_ts.actions import Action, apply_action, changepoints, robust_scale  # noqa: E402
from introact_ts.agent import (  # noqa: E402
    AgentConfig,
    IntroActAgent,
    USE_DEPTH,
)
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.calibration import RISK_WEIGHTS, recalibrate_one  # noqa: E402
from introact_ts.policy import PolicyConfig, propose_actions  # noqa: E402
from introact_ts.probe import SIGNAL_NAMES, probe_window, reference_scale  # noqa: E402
from introact_ts.structure import structure_distortion  # noqa: E402
from introact_ts.types import Verdict  # noqa: E402
from introact_ts.verify import (  # noqa: E402
    VerifyConfig,
    action_risk,
    improvement_consistency,
    improvement_depth,
    verify,
)

PROTECTED_LEDGER = {"clean", "hard", "rare_valid", "changepoint"}
FAMILY_TARGET_KINDS = {"level_shift"}


def _choose_breakpoint(series, penalty=12.0, min_size=24):
    x = np.asarray(series, dtype=np.float64)
    bkps = changepoints(x, penalty=penalty, min_size=min_size)
    if not bkps:
        return None
    scale = robust_scale(x)
    best_b, best_score = None, -1.0
    for b in bkps:
        left = x[:b]
        right = x[b:]
        if len(left) < min_size or len(right) < min_size:
            continue
        jump = abs(float(np.nanmedian(right) - np.nanmedian(left))) / max(scale, 1e-8)
        if jump > best_score:
            best_score = jump
            best_b = b
    return best_b


def _local_medians(x, b, width):
    left = x[max(0, b - width):b]
    right = x[b:min(len(x), b + width)]
    if len(left) == 0 or len(right) == 0:
        return float(np.nanmedian(x)), float(np.nanmedian(x))
    return float(np.nanmedian(left)), float(np.nanmedian(right))


def op_robust_offset_local(series, penalty=12.0, min_size=24, local_width=24, **kw):
    x = np.asarray(series, dtype=np.float64).copy()
    b = _choose_breakpoint(x, penalty=penalty, min_size=min_size)
    if b is None:
        return None
    left_med, right_med = _local_medians(x, b, local_width)
    offset = right_med - left_med
    out = x.copy()
    if b <= len(x) - b:
        out[b:] = x[b:] - offset
    else:
        out[:b] = x[:b] + offset
    return {"series": out, "break": int(b), "offset": float(offset)}


def op_slope_preserving(series, penalty=12.0, min_size=24, local_width=24, **kw):
    x = np.asarray(series, dtype=np.float64).copy()
    b = _choose_breakpoint(x, penalty=penalty, min_size=min_size)
    if b is None:
        return None
    left = x[max(0, b - local_width):b]
    right = x[b:min(len(x), b + local_width)]
    if len(left) < 4 or len(right) < 4:
        return None
    tL = np.arange(len(left), dtype=np.float64)
    tR = np.arange(len(right), dtype=np.float64)
    mL, cL = np.polyfit(tL, left, 1)
    mR, cR = np.polyfit(tR, right, 1)
    val_left = cL + mL * (len(left) - 1)
    val_right = cR
    offset = val_right - val_left
    out = x.copy()
    if b <= len(x) - b:
        out[b:] = x[b:] - offset
    else:
        out[:b] = x[:b] + offset
    return {"series": out, "break": int(b), "offset": float(offset)}


def evaluate_variant(window, state, peer_idx, vname, vtype, params, agent, thresholds):
    """Run one shift-repair variant through the full shield once.

    ``vname`` is the human-readable variant key saved to the trace; ``vtype``
    selects the implementation branch.
    """
    models = agent.models
    cfg = agent.cfg
    original = np.asarray(window.series, dtype=np.float64).copy()
    scale = reference_scale(original)
    center = agent._calib.centers[peer_idx]
    spread = agent._calib.spreads[peer_idx]

    op_info = {}
    if vtype == "keep":
        y = original.copy()
        applicable = True
        cost = 0.0
        touched = None
        struct_action = Action.KEEP
        verify_action = Action.KEEP
        params_out = {}
    elif vtype == "resegment_crop":
        outcome = apply_action(original, Action.RESEGMENT, **params)
        applicable = outcome.applicable
        if not applicable:
            return {"variant": vname, "applicable": False, "note": outcome.note}
        y = np.asarray(outcome.series, dtype=np.float64)
        cost = outcome.cost
        touched = outcome.touched
        struct_action = Action.RESEGMENT
        verify_action = Action.RESEGMENT
        params_out = dict(outcome.params)
        op_info = {k: v for k, v in outcome.params.items() if k not in ("lo", "hi")}
    elif vtype in ("robust_offset_local", "slope_preserving"):
        fn = op_robust_offset_local if vtype == "robust_offset_local" else op_slope_preserving
        raw = fn(original, **params)
        if raw is None:
            return {"variant": vname, "applicable": False, "note": "no breakpoint"}
        y = raw["series"]
        applicable = True
        cost = 0.0
        touched = None
        struct_action = Action.KEEP  # global structural weights, no crop alignment
        verify_action = Action.RESEGMENT  # judged by RESEGMENT's lambda
        params_out = {k: v for k, v in raw.items() if k != "series"}
        op_info = params_out
    else:
        raise ValueError(vtype)

    # Frozen TSFM re-probe.
    after = probe_window(y, models, scale, cfg.probe)
    delta_u = after.utility - state.utility
    z_after, _ = recalibrate_one(after.vector, center, spread, SIGNAL_NAMES, RISK_WEIGHTS)

    # Structure: non-crop variants are treated as global edits for structural
    # scoring, but still checked against RESEGMENT's threshold in verify.
    report = structure_distortion(
        original, y, action=struct_action, params=params_out, touched=touched
    )

    consistency = improvement_consistency(state.z, z_after)
    depth = improvement_depth(state.z, z_after)
    risk = action_risk(depth if USE_DEPTH else state.confidence, cost, consistency)

    vcfg = VerifyConfig(tau=0.02, tau_by_family=thresholds)
    verdict = verify(delta_u, report.distortion, risk, vcfg, action=verify_action)

    # Damage / repair metrics against clean reference when available.
    c = np.asarray(window.clean_series, dtype=np.float64) if window.clean_series is not None else None
    before_nmse, after_nmse, worse, discard, loss, rmsd = None, None, None, None, None, None
    if c is not None:
        lo = int(params_out.get("lo", 0))
        hi = lo + len(y)
        rv = ref_var(c) if len(c) else 1.0

        before_nmse = canonical_nmse(original, c, rv)
        after_nmse = canonical_nmse(y, c[lo:hi], rv)
        worse = 1.0 if after_nmse > before_nmse + 1e-9 else 0.0
        discard = 1.0 - (hi - lo) / len(original)
        loss = max(worse, discard)
        rmsd = repair_rmsd(y, c[lo:hi])

    return {
        "variant": vname,
        "applicable": True,
        "delta_utility": float(delta_u),
        "struct_distortion": float(report.distortion),
        "risk": float(risk),
        "verdict": verdict.value if hasattr(verdict, "value") else str(verdict),
        "utility_before": float(state.utility),
        "utility_after": float(after.utility),
        "before_nmse": before_nmse,
        "after_nmse": after_nmse,
        "worse_binary": worse,
        "discard_share": discard,
        "loss": loss,
        "repair_rmsd": rmsd,
        "cost": float(cost),
        "struct_parts": report.parts,
        "op_info": op_info,
    }


def route_source(state, policy_cfg):
    """Return 'primary' if RESEGMENT is dominant, 'secondary' if secondary."""
    defect = state.dominant_defect
    units = dict(state.defect_units)
    if defect == "shift":
        return "primary"
    units.pop(defect, None)
    if units:
        best = max(units, key=units.get)
        if units[best] >= policy_cfg.secondary_threshold and best == "shift":
            return "secondary"
    return "other"


def aggregate(rows):
    rows = [r for r in rows if r.get("applicable")]
    if not rows:
        return {"n": 0}
    losses = [r["loss"] for r in rows if r.get("loss") is not None]
    rmsds = [r["repair_rmsd"] for r in rows if r.get("repair_rmsd") is not None and np.isfinite(r.get("repair_rmsd"))]
    accepted = sum(1 for r in rows if r.get("verdict") == "ACCEPTED")
    prot_mis = sum(1 for r in rows if r.get("verdict") == "ACCEPTED" and r.get("stratum") in PROTECTED_LEDGER)
    return {
        "n": len(rows),
        "accepted": accepted,
        "protected_mis_edits": prot_mis,
        "protected_mis_edit_rate": prot_mis / len(rows) if rows else 0.0,
        "mean_loss": float(np.mean(losses)) if losses else None,
        "mean_repair_rmsd": float(np.mean(rmsds)) if rmsds else None,
        "share_loss_le_0_03": float(np.mean([l <= 0.03 + 1e-12 for l in losses])) if losses else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1600)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=8)
    ap.add_argument("--families", default=str(ROOT / "results" / "conformal_family.json"))
    ap.add_argument("--partial", default=str(ROOT / "results" / "route_conditioned_shift_partial.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "results" / "route_conditioned_shift.json"))
    args = ap.parse_args()

    # Load thresholds.
    conformal = json.loads(Path(args.families).read_text(encoding="utf-8"))
    thresholds = {f: r["lambda_star"] for f, r in conformal["families"].items()}
    print(f"thresholds: {thresholds}")

    # Build windows and agent.
    print("building calibration windows", flush=True)
    windows, _ = build_calibration(n=args.n, seed=args.seed, source=args.source, verbose=False)
    byid = {w.window_id: w for w in windows}
    print(f"  {len(windows)} windows", flush=True)

    print("initialising frozen models and agent", flush=True)
    models = make_pool(PRESETS[args.preset]["curation"], device=args.device)
    agent = IntroActAgent(
        models,
        AgentConfig(
            verification=VerifyConfig(tau=0.02, tau_by_family=thresholds),
            policy=PolicyConfig(enable_param_ladder=True),
            n_jobs=args.n_jobs,
        ),
    )
    print("perceiving corpus", flush=True)
    states = agent.perceive(windows)
    print("  perception done", flush=True)

    policy_cfg = PolicyConfig(enable_param_ladder=True)

    variants = {
        "keep": ("keep", {}),
        "resegment_crop_default": ("resegment_crop", {"penalty": 12.0, "min_size": 24, "min_keep_frac": 0.5}),
        "resegment_crop_conservative": ("resegment_crop", {"penalty": 20.0, "min_size": 24, "min_keep_frac": 0.5}),
        "resegment_crop_aggressive": ("resegment_crop", {"penalty": 8.0, "min_size": 24, "min_keep_frac": 0.4}),
        "robust_offset_local": ("robust_offset_local", {"penalty": 12.0, "min_size": 24, "local_width": 24}),
        "slope_preserving": ("slope_preserving", {"penalty": 12.0, "min_size": 24, "local_width": 24}),
    }

    # Resume from partial log if present.
    done = set()
    partial_path = Path(args.partial)
    if partial_path.exists():
        with partial_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                done.add((rec["window_id"], rec["variant"]))
        print(f"  resuming: {len(done)} (window, variant) pairs already done")

    per_window = []
    with partial_path.open("a", encoding="utf-8") as partial_f:
        for peer_idx, (w, s) in enumerate(zip(windows, states)):
            # Only windows the proposer routes to RESEGMENT.
            cands = propose_actions(s, [], policy_cfg)
            routed_families = {a.value if hasattr(a, "value") else a for a, _ in cands}
            if "RESEGMENT" not in routed_families:
                continue

            src = route_source(s, policy_cfg)
            print(f"window {w.window_id} ({w.dataset}, {w.stratum}, {w.contamination}) "
                  f"route_source={src}", flush=True)

            for vname, (vtype, vparams) in variants.items():
                if (w.window_id, vname) in done:
                    continue
                rec = evaluate_variant(w, s, peer_idx, vname, vtype, vparams, agent, thresholds)
                rec["window_id"] = int(w.window_id)
                rec["dataset"] = w.dataset
                rec["stratum"] = w.stratum
                rec["true_kind"] = w.contamination
                rec["route_source"] = src
                partial_f.write(json.dumps(rec, default=float) + "\n")
                partial_f.flush()
                per_window.append(rec)
                print(f"  {vname}: applicable={rec.get('applicable')} verdict={rec.get('verdict')} "
                      f"loss={rec.get('loss')}", flush=True)

    # Also load any previously completed partial records.
    if partial_path.exists():
        with partial_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if not any(r["window_id"] == rec["window_id"] and r["variant"] == rec["variant"] for r in per_window):
                    per_window.append(rec)

    # Stratified summaries.
    summaries = {}
    for vname in variants:
        vrows = [r for r in per_window if r["variant"] == vname]
        # By route_source / stratum / true_kind.
        by_rss = defaultdict(list)
        for r in vrows:
            key = (r["route_source"], r["stratum"], r.get("true_kind") or "null")
            by_rss[key].append(r)

        # Level-shift coverage and nRMSD vs KEEP on the same windows.
        ls_rows = [r for r in vrows if r.get("true_kind") == "level_shift"]
        ls_accepted = [r for r in ls_rows if r.get("verdict") == "ACCEPTED"]
        keep_ls = [r for r in per_window if r["variant"] == "keep" and r.get("true_kind") == "level_shift"]
        keep_rmsd = np.mean([r["repair_rmsd"] for r in keep_ls if r.get("repair_rmsd") is not None and np.isfinite(r["repair_rmsd"])]) if keep_ls else None
        acc_rmsd = np.mean([r["repair_rmsd"] for r in ls_accepted if r.get("repair_rmsd") is not None and np.isfinite(r["repair_rmsd"])]) if ls_accepted else None

        # Protected mis-edit rate among accepted edits.
        accepted_all = [r for r in vrows if r.get("verdict") == "ACCEPTED"]
        prot_mis = [r for r in accepted_all if r["stratum"] in PROTECTED_LEDGER]

        summaries[vname] = {
            "n_routed": len(vrows),
            "by_route_source_stratum_true_kind": {
                "_".join(k): aggregate(v) for k, v in by_rss.items()
            },
            "level_shift_coverage": len(ls_accepted) / len(ls_rows) if ls_rows else 0.0,
            "level_shift_n_routed": len(ls_rows),
            "level_shift_n_accepted": len(ls_accepted),
            "mean_repair_rmsd_level_shift_accepted": acc_rmsd,
            "mean_repair_rmsd_keep_level_shift": keep_rmsd,
            "protected_mis_edit_rate": len(prot_mis) / len(accepted_all) if accepted_all else 0.0,
            "n_accepted_total": len(accepted_all),
            "n_protected_mis_edits": len(prot_mis),
        }

    out = {
        "n_windows_total": len(windows),
        "thresholds": thresholds,
        "variants": variants,
        "summaries": summaries,
        "per_window": per_window,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print(f"\nwrote {args.out}", flush=True)
    print("___ROUTE_CONDITIONED_SHIFT_DONE___", flush=True)


if __name__ == "__main__":
    main()
