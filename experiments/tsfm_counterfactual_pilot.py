"""Candidate-level TSFM counterfactual pilot (50 samples).

Stratified by source dataset, this script computes six TSFM-based signals for
candidates drawn from the routed pool and compares them side-by-side with the
existing shield signals.  It is a small-sample implementation check: no claim
about final effect is made, and true_kind is used only for reporting.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

os.environ.setdefault("HF_HOME", "/root/autodl-tmp/.cache/huggingface")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

from audit import _nmse  # noqa: E402
from build_calibration import build as build_calibration  # noqa: E402
from introact_ts.actions import Action, apply_action  # noqa: E402
from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.calibration import RISK_WEIGHTS, recalibrate_one  # noqa: E402
from introact_ts.policy import LADDER, PolicyConfig, propose_actions  # noqa: E402
from introact_ts.probe import SIGNAL_NAMES, probe_window, reference_scale  # noqa: E402
from introact_ts.structure import structure_distortion  # noqa: E402
from introact_ts.verify import VerifyConfig, action_risk, improvement_consistency, improvement_depth, verify  # noqa: E402


#: Existing shield signals carried alongside the new TSFM signals.
SHIELD_SIGNALS = (
    "delta_utility",
    "struct_distortion",
    "risk",
    "confidence",
    "posterior_entropy",
)


def params_for_candidate(cand):
    """Reconstruct operator params from family + rung exactly as the ladder does."""
    family = cand["family"]
    rung = cand.get("rung", "default")
    table = LADDER.get(getattr(Action, family), {})
    return dict(table.get(rung, table.get("default", {})))


def apply_candidate_operator(window, cand):
    """Apply the operator described by a family_scores candidate record."""
    x = np.asarray(window.series, dtype=np.float64).copy()
    family = cand["family"]
    params = params_for_candidate(cand)
    action = getattr(Action, family)
    outcome = apply_action(x, action, **params)
    return outcome, params


def _random_spans(T, n_masks, mask_len, rng, exclude=None):
    """Non-overlapping random spans, optionally excluding a region."""
    exclude = exclude or (None, None)
    ex_lo, ex_hi = exclude
    spans = []
    attempts = 0
    while len(spans) < n_masks and attempts < n_masks * 20:
        attempts += 1
        lo = rng.randint(mask_len, T - mask_len)
        hi = lo + mask_len
        if ex_lo is not None and not (hi <= ex_lo or lo >= ex_hi):
            continue
        if any(not (hi <= s[0] or lo >= s[1]) for s in spans):
            continue
        spans.append((lo, hi))
    return spans


def _touched_spans(touched):
    """Boolean touched mask -> list of (lo, hi) half-open spans."""
    if touched is None:
        return []
    t = np.asarray(touched, dtype=bool)
    spans = []
    i, T = 0, len(t)
    while i < T:
        if t[i]:
            j = i
            while j < T and t[j]:
                j += 1
            spans.append((i, j))
            i = j
        else:
            i += 1
    return spans


def _region_from_touched(touched, T):
    """Single representative touched span, expanded slightly for probing."""
    spans = _touched_spans(touched)
    if not spans:
        return None
    lo = min(s[0] for s in spans)
    hi = max(s[1] for s in spans)
    # Expand to a modest context so forecasts/reconstructions have anchors.
    pad = max(8, (hi - lo) // 4)
    lo = max(0, lo - pad)
    hi = min(T, hi + pad)
    return (lo, hi)


def _rmse_aligned(segment, recon):
    """Return RMSE only if the reconstruction has the expected length."""
    segment = np.asarray(segment)
    recon = np.asarray(recon)
    if recon.shape != segment.shape:
        return None
    if len(segment) == 0:
        return None
    return float(np.sqrt(np.mean((segment - recon) ** 2)))


def _forecast_len(judge, ctx, H):
    """Forecast and enforce the requested horizon length."""
    try:
        pred = judge.forecast_batch([ctx], H)[0]
    except Exception:
        return None
    pred = np.asarray(pred)
    if len(pred) != H or not np.isfinite(pred).all():
        return None
    return pred


def compute_tsfm_signals(window, cand, outcome, models, cfg_probe, rng):
    """Compute the six TSFM counterfactual signals for one candidate."""
    judge = models[0]
    peer = models[1] if len(models) > 1 else None
    original = np.asarray(window.series, dtype=np.float64)
    edited = np.asarray(outcome.series, dtype=np.float64) if outcome.applicable else original.copy()
    T = len(original)
    scale = max(reference_scale(original), 1e-6)

    touched = outcome.touched
    region = _region_from_touched(touched, T)
    if region is None:
        # Global operators (DENOISE) have no footprint; probe the last quarter.
        region = (max(0, T - 128), T)

    lo, hi = region
    signals = {}

    # 1. Masked reconstruction preference ------------------------------------
    #    Reconstruction error when the mask sits on the operator's region
    #    versus random masks elsewhere.
    if "reconstruct" in judge.capabilities:
        n_masks = 4
        mask_len = min(24, hi - lo)
        touched_spans = [(max(lo, hi - mask_len), hi)] if hi - lo >= 8 else []
        random_spans = _random_spans(T, n_masks, mask_len, rng, exclude=(lo, hi))
        all_spans = touched_spans + random_spans
        if len(all_spans) >= 2:
            recs_orig = judge.reconstruct_batch(original, all_spans)
            recs_edit = judge.reconstruct_batch(edited, all_spans)
            errs_orig = [_rmse_aligned(original[a:b], r) for (a, b), r in zip(all_spans, recs_orig)]
            errs_edit = [_rmse_aligned(edited[a:b], r) for (a, b), r in zip(all_spans, recs_edit)]
            n_touched = len(touched_spans)
            # Only keep spans where *both* original and edited reconstructions aligned.
            touched_pairs = [(eo, ee) for eo, ee in zip(errs_orig[:n_touched], errs_edit[:n_touched]) if eo is not None and ee is not None]
            random_pairs = [(eo, ee) for eo, ee in zip(errs_orig[n_touched:], errs_edit[n_touched:]) if eo is not None and ee is not None]
            if touched_pairs and random_pairs:
                pref_touched = np.mean([ee - eo for eo, ee in touched_pairs])
                pref_random = np.mean([ee - eo for eo, ee in random_pairs])
                signals["masked_reconstruction_preference"] = float(pref_random - pref_touched)
            else:
                signals["masked_reconstruction_preference"] = None
        else:
            signals["masked_reconstruction_preference"] = None
    else:
        signals["masked_reconstruction_preference"] = None

    # 2. Forecast/backcast agreement on the region ---------------------------
    H = min(32, hi - lo)
    if H >= 8:
        # Forward forecast from the left context ending at lo.
        fwd = _forecast_len(judge, original[:lo], H)
        # Backcast from the right context starting at hi.
        bwd_ctx = original[hi:][::-1]
        bwd_pred = _forecast_len(judge, bwd_ctx, H)
        bwd = bwd_pred[::-1] if bwd_pred is not None else None
        if fwd is not None and bwd is not None:
            signals["forecast_backcast_agreement"] = float(
                np.sqrt(np.mean((fwd - bwd) ** 2)) / scale
            )
        else:
            signals["forecast_backcast_agreement"] = None
    else:
        signals["forecast_backcast_agreement"] = None

    # 3. Mask/context stability ---------------------------------------------
    #    Std of forecasts under two context lengths.
    if H >= 8:
        preds = []
        for frac in (0.5, 1.0):
            ctx_len = max(32, int(frac * lo))
            ctx = original[max(0, lo - ctx_len):lo]
            pred = _forecast_len(judge, ctx, H)
            if pred is not None:
                preds.append(pred)
        std = float(np.mean(np.std(np.stack(preds), axis=0)) / scale) if len(preds) >= 2 else None
        signals["mask_context_stability"] = std
    else:
        signals["mask_context_stability"] = None

    # 4. Cross-model agreement -----------------------------------------------
    if peer is not None and H >= 8:
        try:
            p1 = _forecast_len(judge, original[:lo], H)
            p2 = _forecast_len(peer, original[:lo], H)
            tgt = original[lo:lo + H]
            if p1 is not None and p2 is not None and len(tgt) == H:
                e1 = p1 - tgt
                e2 = p2 - tgt
                if np.std(e1) > 1e-12 and np.std(e2) > 1e-12:
                    corr = float(np.corrcoef(e1, e2)[0, 1])
                    signals["cross_model_agreement"] = float(1.0 - np.clip(corr, -1.0, 1.0))
                else:
                    signals["cross_model_agreement"] = None
            else:
                signals["cross_model_agreement"] = None
        except Exception:
            signals["cross_model_agreement"] = None
    else:
        signals["cross_model_agreement"] = None

    # 5. Seam error ----------------------------------------------------------
    spans = _touched_spans(touched)
    if spans:
        jumps = []
        for slo, shi in spans:
            if slo > 0:
                jumps.append(abs(edited[slo] - edited[slo - 1]))
            if shi < T:
                jumps.append(abs(edited[shi - 1] - edited[shi]))
        signals["seam_error"] = float(np.max(jumps) / scale) if jumps else None
    else:
        signals["seam_error"] = None

    # 6. Outside-support drift -----------------------------------------------
    #    Change in model forecast error on untouched points after the edit.
    untouched = np.ones(T, dtype=bool)
    if touched is not None:
        untouched &= ~np.asarray(touched, dtype=bool)[:T]
    if untouched.sum() >= H + 8:
        ctx_before = original[:lo]
        ctx_after = edited[:lo]
        tgt = original[lo:lo + H]
        pred_before = _forecast_len(judge, ctx_before, H)
        pred_after = _forecast_len(judge, ctx_after, H)
        if pred_before is not None and pred_after is not None and len(tgt) == H:
            err_before = float(np.sqrt(np.mean((pred_before - tgt) ** 2)) / scale)
            err_after = float(np.sqrt(np.mean((pred_after - tgt) ** 2)) / scale)
            signals["outside_support_drift"] = err_after - err_before
        else:
            signals["outside_support_drift"] = None
    else:
        signals["outside_support_drift"] = None

    return signals


def compute_shield_signals(window, state, cand, outcome, models, agent, peer_idx):
    """Recompute the existing shield signals for the same candidate."""
    if not outcome.applicable:
        return {k: None for k in SHIELD_SIGNALS}

    original = np.asarray(window.series, dtype=np.float64)
    edited = np.asarray(outcome.series, dtype=np.float64)
    scale = reference_scale(original)
    center = agent._calib.centers[peer_idx]
    spread = agent._calib.spreads[peer_idx]

    after = probe_window(edited, models, scale, agent.cfg.probe)
    delta_u = after.utility - state.utility
    z_after, _ = recalibrate_one(after.vector, center, spread, SIGNAL_NAMES, RISK_WEIGHTS)

    family = cand["family"]
    action = getattr(Action, family)
    # Use the operator's actual runtime params (e.g. RESEGMENT's lo/hi),
    # falling back to the ladder defaults only when the operator did not set any.
    params = outcome.params if outcome.params else params_for_candidate(cand)
    report = structure_distortion(original, edited, action=action, params=params, touched=outcome.touched)

    consistency = improvement_consistency(state.z, z_after)
    depth = improvement_depth(state.z, z_after)
    risk = action_risk(depth, outcome.cost, consistency)

    # Confidence and posterior entropy from the pre-action risk state.
    conf = float(state.confidence)
    post = state.posterior if hasattr(state, "posterior") and state.posterior is not None else {}
    entropy = 0.0
    if post:
        probs = np.asarray(list(post.values()), dtype=np.float64)
        probs = probs[probs > 0]
        entropy = float(-np.sum(probs * np.log(probs)))

    return {
        "delta_utility": float(delta_u),
        "struct_distortion": float(report.distortion),
        "risk": float(risk),
        "confidence": conf,
        "posterior_entropy": entropy,
    }


def stratified_sample(candidates, n_total=50, rng=None):
    """Sample candidates stratified by dataset, then spread across families."""
    rng = rng or np.random.RandomState(42)
    by_ds = defaultdict(list)
    for c in candidates:
        by_ds[c["dataset"]].append(c)

    datasets = sorted(by_ds)
    n_real = sum(1 for d in datasets if not d.startswith("ood:"))
    n_ood = len(datasets) - n_real

    # Aim for roughly equal per real dataset; pool synthetic OOD.
    if n_real > 0:
        per_real = max(1, n_total // (n_real + 1))
    else:
        per_real = 0
    ood_budget = max(5, n_total - per_real * n_real)

    chosen = []
    for ds in datasets:
        pool = by_ds[ds]
        budget = ood_budget if ds.startswith("ood:") else per_real
        # Try to cover multiple families within the dataset budget.
        by_fam = defaultdict(list)
        for c in pool:
            by_fam[c["family"]].append(c)
        fams = sorted(by_fam, key=lambda f: len(by_fam[f]), reverse=True)
        ds_chosen = []
        while len(ds_chosen) < budget and any(by_fam.values()):
            for fam in fams:
                if len(ds_chosen) >= budget:
                    break
                if by_fam[fam]:
                    idx = rng.randint(0, len(by_fam[fam]))
                    ds_chosen.append(by_fam[fam].pop(idx))
        chosen.extend(ds_chosen)

    # Trim / pad to exactly n_total without replacement.
    if len(chosen) > n_total:
        chosen = rng.choice(chosen, n_total, replace=False).tolist()
    elif len(chosen) < n_total:
        extra = rng.choice(candidates, n_total - len(chosen), replace=False)
        chosen.extend(extra.tolist())
    return chosen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1600)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=8)
    ap.add_argument("--scores", default=str(ROOT / "results" / "family_scores.jsonl"))
    ap.add_argument("--sample-seed", dest="sample_seed", type=int, default=42)
    ap.add_argument("--n-sample", dest="n_sample", type=int, default=50)
    ap.add_argument("--partial", default=str(ROOT / "results" / "tsfm_counterfactual_pilot.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "results" / "tsfm_counterfactual_pilot.json"))
    args = ap.parse_args()

    rng = np.random.RandomState(args.sample_seed)

    # Load candidate records.
    print("loading family_scores", flush=True)
    all_candidates = []
    with Path(args.scores).open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            for c in row.get("candidates", []):
                c = dict(c)
                c["window_id"] = row["window_id"]
                all_candidates.append(c)
    print(f"  {len(all_candidates)} candidates")

    # Build windows and agent.
    print("building calibration windows", flush=True)
    windows, _ = build_calibration(n=args.n, seed=args.seed, source=args.source, verbose=False)
    byid = {w.window_id: w for w in windows}
    print(f"  {len(windows)} windows", flush=True)

    # Annotate candidates with dataset from the window metadata.
    for c in all_candidates:
        w = byid.get(c["window_id"])
        c["dataset"] = w.dataset if w is not None else "unknown"

    sample = stratified_sample(all_candidates, n_total=args.n_sample, rng=rng)
    sample_ids = set((c["window_id"], c["family"], c.get("rung", "default")) for c in sample)
    sample_wids = sorted(set(c["window_id"] for c in sample))
    print(f"stratified sample: {len(sample)} candidates from {len(set(c['dataset'] for c in sample))} datasets, {len(sample_wids)} unique windows")

    # Perceive only the windows that the sample actually needs.
    # build_calibration may emit the same window_id more than once, so dedupe
    # while preserving order.
    windows_subset = []
    seen_wid = set()
    for w in windows:
        if w.window_id in sample_wids and w.window_id not in seen_wid:
            windows_subset.append(w)
            seen_wid.add(w.window_id)
    windows_subset_byid = {w.window_id: w for w in windows_subset}

    print("initialising frozen models and agent", flush=True)
    models = make_pool(PRESETS[args.preset]["curation"], device=args.device)
    agent = IntroActAgent(
        models,
        AgentConfig(
            verification=VerifyConfig(tau=0.02),
            policy=PolicyConfig(enable_param_ladder=True),
            n_jobs=args.n_jobs,
        ),
    )
    print("perceiving sample windows", flush=True)
    states = agent.perceive(windows_subset)
    print("  perception done", flush=True)

    # Resume from partial log.
    done = set()
    partial_path = Path(args.partial)
    if partial_path.exists():
        with partial_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                done.add((rec["window_id"], rec["family"], rec["rung"]))
        print(f"  resuming: {len(done)} candidates already done")

    records = []
    with partial_path.open("a", encoding="utf-8") as partial_f:
        for peer_idx, (w, s) in enumerate(zip(windows_subset, states)):
            for cand in sample:
                wid = cand["window_id"]
                if wid != w.window_id:
                    continue
                key = (wid, cand["family"], cand.get("rung", "default"))
                if key in done:
                    continue

                outcome, _ = apply_candidate_operator(w, cand)
                tsfm_signals = compute_tsfm_signals(w, cand, outcome, models, agent.cfg.probe, rng)
                shield_signals = compute_shield_signals(w, s, cand, outcome, models, agent, peer_idx)

                rec = {
                    "window_id": int(wid),
                    "dataset": w.dataset,
                    "stratum": w.stratum,
                    "true_kind": w.contamination,
                    "family": cand["family"],
                    "rung": cand.get("rung", "default"),
                    "distortion": cand.get("distortion"),
                    "delta_utility_ledger": cand.get("delta_utility"),
                    "loss": cand.get("loss"),
                    "applicable": outcome.applicable,
                    "note": outcome.note if not outcome.applicable else "",
                    "tsfm_signals": tsfm_signals,
                    "shield_signals": shield_signals,
                }
                partial_f.write(json.dumps(rec, default=float) + "\n")
                partial_f.flush()
                records.append(rec)
                done.add(key)  # prevent the end-of-run loader from re-adding it
                print(f"  window {wid} {cand['family']}/{cand.get('rung','default')}: "
                      f"applicable={outcome.applicable} signals={ {k: v for k, v in tsfm_signals.items() if v is not None} }",
                      flush=True)

    # Load any previous partial records not in this run.
    if partial_path.exists():
        with partial_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                key = (rec["window_id"], rec["family"], rec["rung"])
                if key not in done:
                    records.append(rec)

    # Summaries: correlation / AUROC-style separation is intentionally NOT
    # reported because n=50 is too small.  We report mean signal values by
    # accepted-vs-rejected and level_shift-vs-protected to verify directionality.
    def mean_by(key_fn):
        groups = defaultdict(list)
        for r in records:
            groups[key_fn(r)].append(r)
        out = {}
        for k, rows in groups.items():
            sigs = defaultdict(list)
            for row in rows:
                for name, val in row["tsfm_signals"].items():
                    if val is not None and np.isfinite(val):
                        sigs[name].append(val)
            out[str(k)] = {name: float(np.mean(v)) for name, v in sigs.items() if v}
        return out

    def accepted(r):
        du = r["shield_signals"].get("delta_utility")
        return du is not None and du > 0.005
    summaries = {
        "n_records": len(records),
        "by_accepted": mean_by(accepted),
        "by_level_shift": mean_by(lambda r: r["true_kind"] == "level_shift"),
        "by_protected": mean_by(lambda r: r["stratum"] in {"clean", "hard", "rare_valid", "changepoint"}),
    }

    out = {
        "meta": {
            "sample_seed": args.sample_seed,
            "n_sample": args.n_sample,
            "n_records": len(records),
            "models": [getattr(m, "name", type(m).__name__) for m in models],
        },
        "summaries": summaries,
        "records": records,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print(f"\nwrote {args.out}", flush=True)
    print("___TSFM_COUNTERFACTUAL_PILOT_DONE___", flush=True)


if __name__ == "__main__":
    main()
