"""Prototype non-destructive level-shift operators and compare them to crop/KEEP.

Tests four strategies on windows whose true contamination is level_shift:
  keep                  no change
  resegment_crop        current RESEGMENT (keeps the longer segment)
  robust_offset_global  align segments by their global medians
  robust_offset_local   align segments by medians in a window around the break
                        (preserves the slope outside the neighbourhood)

A fifth arm, slope_preserving, is also reported: it estimates an offset by
matching linear fits at the breakpoint while leaving slopes intact, which for a
pure level shift reduces to a local robust offset.

Metrics per window:
  loss = max(worse_binary, discard_share) with discard_share = 0 for non-crop
  repair nRMSD = RMS distance to the clean reference, normalised by the
                 reference's own scale
  applicable, offset magnitude, break index

The probe evaluates every operator on every calibration window so that off-target
mis-application (e.g. on protected or noise windows) is visible as well.

Usage:
    python -u experiments/level_shift_operator_probe.py \
        --out results/level_shift_probe.json
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from build_calibration import build as build_calibration  # noqa: E402
from metrics_common import canonical_nmse, repair_rmsd, ref_var  # noqa: E402
from introact_ts.actions import (  # noqa: E402
    Action,
    apply_action,
    changepoints,
    robust_scale,
)

DELTA = 1e-9


def _choose_breakpoint(series, penalty=12.0, min_size=24):
    """Return the breakpoint most likely to be a level shift.

    Among PELT changepoints that respect min_size, pick the one with the largest
    robust median jump.
    """
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
    """Median of the `width` points immediately before and after breakpoint b."""
    left = x[max(0, b - width):b]
    right = x[b:min(len(x), b + width)]
    if len(left) == 0 or len(right) == 0:
        return float(np.nanmedian(x)), float(np.nanmedian(x))
    return float(np.nanmedian(left)), float(np.nanmedian(right))


def op_robust_offset_global(series, penalty=12.0, min_size=24, **kw):
    """Align the shorter segment to the longer using full-segment medians."""
    x = np.asarray(series, dtype=np.float64).copy()
    b = _choose_breakpoint(x, penalty=penalty, min_size=min_size)
    if b is None:
        return None
    left_med = float(np.nanmedian(x[:b]))
    right_med = float(np.nanmedian(x[b:]))
    offset = right_med - left_med
    out = x.copy()
    if b <= len(x) - b:  # right segment shorter or equal -> move right
        out[b:] = x[b:] - offset
    else:
        out[:b] = x[:b] + offset
    return {"series": out, "break": int(b), "offset": float(offset)}


def op_robust_offset_local(series, penalty=12.0, min_size=24, local_width=24, **kw):
    """Align using local medians around the break, preserving global slope."""
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
    """Estimate offset with linear fits at the breakpoint, leave slopes intact."""
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


def evaluate_on_window(window, operator_name, op_func, **params):
    """Return a metric dict for one operator on one window."""
    x = np.asarray(window.series, dtype=np.float64)
    c = np.asarray(window.clean_series, dtype=np.float64)
    rv = ref_var(c)

    before = canonical_nmse(x, c, rv)
    if operator_name == "keep":
        y = x.copy()
        applicable = True
        op_info = {"offset": 0.0}
        lo, hi = 0, len(x)
    elif operator_name == "resegment_crop":
        outcome = apply_action(x, Action.RESEGMENT, **params)
        applicable = outcome.applicable
        y = np.asarray(outcome.series, dtype=np.float64)
        lo = int(outcome.params.get("lo", 0))
        hi = lo + len(y)
        op_info = {k: v for k, v in outcome.params.items() if k not in ("lo", "hi")}
    else:
        raw = op_func(x, **params)
        applicable = raw is not None
        if not applicable:
            return {"applicable": False}
        y = raw["series"]
        lo, hi = 0, len(y)
        op_info = {k: v for k, v in raw.items() if k != "series"}

    after = canonical_nmse(y, c[lo:hi], rv) if applicable else before
    worse = 1.0 if after > before + DELTA else 0.0
    discard = 1.0 - (hi - lo) / len(x)
    loss = max(worse, discard)

    rmsd = repair_rmsd(y if applicable else x, c[lo:hi] if applicable else c)

    return {
        "applicable": applicable,
        "before_nmse": float(before),
        "after_nmse": float(after),
        "worse_binary": float(worse),
        "discard_share": float(discard),
        "loss": float(loss),
        "repair_rmsd": rmsd,
        **op_info,
    }


def aggregate(rows):
    """Summary statistics over a list of per-window metric dicts."""
    rows = [r for r in rows if r.get("applicable")]
    if not rows:
        return {"n": 0}
    losses = [r["loss"] for r in rows]
    rmsds = [r["repair_rmsd"] for r in rows]
    return {
        "n": len(rows),
        "applicable_rate": len(rows) / max(len(rows) + sum(1 for r in rows if not r.get("applicable")), 1),
        "mean_loss": float(np.mean(losses)),
        "median_loss": float(np.median(losses)),
        "share_loss_le_0_03": float(np.mean([l <= 0.03 + 1e-12 for l in losses])),
        "mean_repair_rmsd": float(np.mean(rmsds)),
        "median_repair_rmsd": float(np.median(rmsds)),
        "max_loss": float(np.max(losses)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1600)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--out", default=str(ROOT / "results" / "level_shift_probe.json"))
    args = ap.parse_args()

    print("building calibration windows", flush=True)
    windows, _ = build_calibration(n=args.n, seed=args.seed,
                                   source=args.source, verbose=False)
    level_windows = [w for w in windows if w.contamination == "level_shift"]
    print(f"  {len(windows)} total windows, {len(level_windows)} level_shift", flush=True)

    operators = {
        "keep": ("keep", {}),
        "resegment_crop_default": ("resegment_crop", {"penalty": 12.0, "min_size": 24, "min_keep_frac": 0.5}),
        "resegment_crop_conservative": ("resegment_crop", {"penalty": 20.0, "min_size": 24, "min_keep_frac": 0.5}),
        "resegment_crop_aggressive": ("resegment_crop", {"penalty": 8.0, "min_size": 24, "min_keep_frac": 0.4}),
        "robust_offset_global": ("robust_offset_global", {"penalty": 12.0, "min_size": 24}),
        "robust_offset_local": ("robust_offset_local", {"penalty": 12.0, "min_size": 24, "local_width": 24}),
        "slope_preserving": ("slope_preserving", {"penalty": 12.0, "min_size": 24, "local_width": 24}),
    }

    func_map = {
        "robust_offset_global": op_robust_offset_global,
        "robust_offset_local": op_robust_offset_local,
        "slope_preserving": op_slope_preserving,
    }

    per_window = defaultdict(list)

    for w in windows:
        for name, (op_name, params) in operators.items():
            fn = func_map.get(op_name)
            rec = evaluate_on_window(w, op_name, fn, **params)
            rec["window_id"] = int(w.window_id)
            rec["dataset"] = w.dataset
            rec["stratum"] = w.stratum
            rec["true_kind"] = w.contamination
            per_window[name].append(rec)

    # Summaries on the target class.
    target_summaries = {}
    print("\noperator performance on level_shift windows")
    print(f"{'operator':28s}{'n':>5s}{'mean loss':>11s}{'loss<=0.03':>12s}{'mean rmsd':>11s}{'max loss':>10s}")
    for name in operators:
        rows = [r for r in per_window[name] if r["true_kind"] == "level_shift"]
        summ = aggregate(rows)
        target_summaries[name] = summ
        print(f"{name:28s}{summ['n']:5d}{summ['mean_loss']:11.4f}"
              f"{summ.get('share_loss_le_0_03', 0.0):12.4f}"
              f"{summ.get('mean_repair_rmsd', 0.0):11.4f}{summ.get('max_loss', 0.0):10.4f}")

    # Off-target and protected-stratum diagnostics for the best non-destructive arms.
    protected_strata = {"clean", "hard", "rare_valid", "changepoint"}
    off_target_summaries = {}
    for name in ["robust_offset_local", "slope_preserving", "resegment_crop_conservative"]:
        protected_rows = [r for r in per_window[name] if r["stratum"] in protected_strata]
        non_target_contaminated = [r for r in per_window[name]
                                   if r["stratum"] == "contaminated" and r["true_kind"] != "level_shift"]
        off_target_summaries[name] = {
            "protected": aggregate(protected_rows),
            "non_target_contaminated": aggregate(non_target_contaminated),
        }

    # Per-dataset breakdown for the target class.
    by_dataset = defaultdict(dict)
    for name in ["robust_offset_local", "slope_preserving", "robust_offset_global"]:
        groups = defaultdict(list)
        for r in per_window[name]:
            if r["true_kind"] == "level_shift":
                groups[r["dataset"]].append(r)
        by_dataset[name] = {ds: aggregate(rows) for ds, rows in groups.items()}

    # Per-true-kind breakdown for the best non-destructive arm.
    true_kind_groups = defaultdict(list)
    for r in per_window["robust_offset_local"]:
        true_kind_groups[r["true_kind"]].append(r)
    by_true_kind = {k: aggregate(v) for k, v in true_kind_groups.items()}

    out = {
        "n_windows": len(windows),
        "n_level_shift_windows": len(level_windows),
        "operators": operators,
        "target_summaries": target_summaries,
        "off_target_summaries": off_target_summaries,
        "per_window": {k: v for k, v in per_window.items()},
        "by_dataset": by_dataset,
        "by_true_kind": by_true_kind,
    }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print(f"\nwrote {args.out}", flush=True)
    print("___LEVEL_SHIFT_PROBE_DONE___", flush=True)


if __name__ == "__main__":
    main()
