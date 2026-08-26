"""Why the damage rate in the table and the damage rate from the traces differ.

Reconciling the main table against the flushed per window traces
(`reconcile_traces.py`) found every column agreeing to floating point except
the damage rate, which disagreed by up to 0.32. That is not a rounding
artefact, so this file finds the cause on a deterministic arm that can be
re run on a workstation with no GPU and no model pool.

The two quantities:

  the table    `audit._nmse`, which subtracts each series' own median, divides
               by the clean reference's variance, and replaces a non finite
               point with the median before measuring
  the traces   `run_main._dist`, a plain root mean square distance that drops
               non finite differences instead of filling them

Both are then used the same way, an edit is damaging when the distance to the
clean reference grew. They can still disagree in three places, and this script
separates them rather than guessing:

  centring     `_nmse` removes each series' median, so an edit that shifts the
               whole window is invisible to it and visible to `_dist`
  non finite   `_nmse` fills, `_dist` drops. An IMPUTE over a gap the clean
               reference also lacks changes the first and not the second
  cropping     after a RESEGMENT the two align the clean reference the same way
               but re centre on different spans

`L1_screen` is the probe because `repair_traces` reads only `state.utility`
from the perception state, and that value never reaches the series, so the arm
reproduces exactly on a stub state. The reproduction is asserted against the
table's own edit count before any conclusion is drawn.

Usage:
    python experiments/damage_metric_probe.py --seed 0 \
        --table results/main_table_seed0.json
"""

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from audit import _nmse  # noqa: E402
from corpus import build_corpus  # noqa: E402
from run_agent import SCALES  # noqa: E402
from run_main import _dist, repair_traces  # noqa: E402


@dataclass
class StubState:
    """`repair_traces` reads `utility` and nothing else. See the docstring."""
    utility: float = 0.0


def nmse_pair(w, t):
    """The table's before and after, exactly as `score_rows` computes them."""
    ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))
    a = _nmse(t.final_series, w.clean_series[t.crop_offset:], ref_var)
    b = _nmse(w.series, w.clean_series, ref_var)
    return b, a


def dist_pair(w, t):
    """The traces' before and after, exactly as `dump_window_traces` does."""
    b = _dist(np.asarray(w.series, dtype=np.float64), w.clean_series)
    a = _dist(t.final_series, w.clean_series, t.crop_offset)
    return b, a


def explain(w, t):
    """What could make the two verdicts differ on this window."""
    x = np.asarray(w.series, dtype=np.float64)
    y = np.asarray(t.final_series, dtype=np.float64)
    c = np.asarray(w.clean_series, dtype=np.float64)
    n = min(len(y), len(c) - t.crop_offset)
    return {
        "nonfinite_input": int((~np.isfinite(x)).sum()),
        "nonfinite_output": int((~np.isfinite(y)).sum()),
        "nonfinite_clean": int((~np.isfinite(c)).sum()),
        # How far the edit moved the window's level. `_nmse` cannot see this.
        "median_shift": float(abs(np.nanmedian(y) - np.nanmedian(x))),
        "median_shift_scaled": float(
            abs(np.nanmedian(y) - np.nanmedian(x))
            / max(float(np.nanstd(x)), 1e-9)),
        "crop_offset": int(t.crop_offset),
        "n_compared": int(max(n, 0)),
        "stratum": w.stratum,
        "contamination": w.contamination,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--scale", default="xl")
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--arm", default="L1_screen",
                    choices=["L1_screen", "L2_imr", "L3_mtcsc"])
    ap.add_argument("--table", default=None)
    ap.add_argument("--out", default=str(ROOT / "results" / "damage_metric_probe.json"))
    args = ap.parse_args()

    spec = SCALES[args.scale]
    spec.seed = args.seed
    windows = build_corpus(spec, source=args.source)
    print(f"{len(windows)} windows, seed {args.seed}", flush=True)

    states = [StubState() for _ in windows]
    traces = repair_traces(windows, states, args.arm.split("_", 1)[1])

    byid = {w.window_id: w for w in windows}
    rows = []
    for t in traces:
        w = byid[t.window_id]
        if w.clean_series is None or not t.content_modified(w.series):
            continue
        nb, na = nmse_pair(w, t)
        db, da = dist_pair(w, t)
        if not np.isfinite(nb) or not np.isfinite(na) or db is None or da is None:
            continue
        rows.append({
            "window_id": int(t.window_id),
            "nmse_before": nb, "nmse_after": na,
            "dist_before": db, "dist_after": da,
            "nmse_harmful": bool(na > nb + 1e-9),
            "dist_harmful": bool(da > db + 1e-9),
            **explain(w, t),
        })

    n = len(rows)
    nmse_h = sum(r["nmse_harmful"] for r in rows)
    dist_h = sum(r["dist_harmful"] for r in rows)
    print(f"edited windows with a clean reference: {n}")
    print(f"  damage rate, table definition  {nmse_h}/{n} = {nmse_h / n:.4f}")
    print(f"  damage rate, trace definition  {dist_h}/{n} = {dist_h / n:.4f}")

    if args.table:
        tab = json.loads(Path(args.table).read_text(encoding="utf-8"))["rows"]
        if args.arm in tab:
            want_edits = tab[args.arm]["committed_edits"]
            want_dmg = tab[args.arm]["damage_rate"]
            print(f"  the table says {want_edits} edits at {want_dmg:.4f}")
            if want_edits != n:
                print(f"  REPRODUCTION FAILED, {n} edits against {want_edits}, "
                      f"nothing below can be trusted")
            elif abs(want_dmg - nmse_h / n) > 1e-9:
                print(f"  REPRODUCTION FAILED, damage {nmse_h / n:.6f} against "
                      f"{want_dmg:.6f}")
            else:
                print("  reproduced exactly, so the split below is the real cause")

    disagree = [r for r in rows if r["nmse_harmful"] != r["dist_harmful"]]
    print()
    print(f"windows the two definitions judge differently: {len(disagree)} "
          f"of {n}")
    only_dist = [r for r in disagree if r["dist_harmful"]]
    only_nmse = [r for r in disagree if r["nmse_harmful"]]
    print(f"  damaging by distance only  {len(only_dist)}")
    print(f"  damaging by nmse only      {len(only_nmse)}")

    def profile(sub, label):
        if not sub:
            return {}
        shift = np.asarray([r["median_shift_scaled"] for r in sub])
        nf = np.asarray([r["nonfinite_input"] for r in sub])
        nfc = np.asarray([r["nonfinite_clean"] for r in sub])
        crop = np.asarray([r["crop_offset"] for r in sub])
        print(f"  {label}")
        print(f"    median level shift over input sd, median "
              f"{np.median(shift):.4f}  q90 {np.percentile(shift, 90):.4f}")
        print(f"    non finite in input, median {np.median(nf):.0f}  "
              f"share with any {float((nf > 0).mean()):.3f}")
        print(f"    non finite in clean reference, share with any "
              f"{float((nfc > 0).mean()):.3f}")
        print(f"    cropped windows {int((crop > 0).sum())}")
        print(f"    strata {dict(Counter(r['stratum'] for r in sub))}")
        return {"n": len(sub),
                "median_shift_scaled_median": float(np.median(shift)),
                "nonfinite_input_share": float((nf > 0).mean()),
                "nonfinite_clean_share": float((nfc > 0).mean()),
                "cropped": int((crop > 0).sum()),
                "strata": dict(Counter(r["stratum"] for r in sub))}

    print()
    agree = [r for r in rows if r["nmse_harmful"] == r["dist_harmful"]]
    prof = {"disagree_dist_only": profile(only_dist, "damaging by distance only"),
            "disagree_nmse_only": profile(only_nmse, "damaging by nmse only"),
            "agree": profile(agree, "agreed on")}

    # The decisive comparison. If centring is the cause, removing it from the
    # nmse side alone should move its verdict onto the distance side.
    both_centred = sum(
        1 for r in rows
        if (r["dist_after"] > r["dist_before"] + 1e-9) == r["nmse_harmful"])
    print()
    print(f"agreement rate {both_centred / n:.4f}")

    Path(args.out).write_text(json.dumps(
        {"seed": args.seed, "arm": args.arm, "n_edited": n,
         "damage_rate_nmse": nmse_h / n, "damage_rate_dist": dist_h / n,
         "n_disagree": len(disagree), "profiles": prof,
         "rows": rows[:200]}, indent=1, default=float), encoding="utf-8")
    print("___DAMAGE_PROBE_DONE___")


if __name__ == "__main__":
    main()
