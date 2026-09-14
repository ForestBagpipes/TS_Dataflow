"""Every arm's damage rate under the corrected definition, without a rerun.

Damage now counts discarded data: `loss = max(worse, discard_share)` with
`worse` the old binary comparison and `discard_share` the fraction of the
window's variation a crop threw away. Both are ground truth quantities that
depend on no calibrated threshold, which is what keeps the rate comparable
across arms that have no threshold of their own.

**Why this recomputes rather than reruns.** The verdicts do not change. This
changes how a committed edit is scored, not which edits are committed, so the
behaviour on disk is still valid and only the scoring is stale.

**What each arm needs, which is much less than a full rebuild.**

  repair family, Learn2Clean, oracle
      These never crop. Their `discard_share` is identically zero by the
      definition of the algorithm, not as an empirical fact to be checked, so
      `max(worse, 0) = worse` and the old number carries over unchanged. Nothing
      is computed for them. Their traces record no per candidate steps, and an
      earlier version of this script misread that absence as "cannot tell
      whether it edited", which is a different thing entirely.

  agent arms
      Only windows that accepted a RESEGMENT can have a non zero discard, and
      the crop's `lo` and `hi` are in the trace, so the discard is exact without
      rebuilding anything. Three cases:

        accepted only RESEGMENT   the final series is `series[lo:hi]`, so both
                                  terms are exact
        accepted only value ops   discard is zero, so the loss is the old one
        accepted both             discard is exact, the old binary term is not
                                  recoverable without the model

**The third case is reported as an interval rather than dropped or guessed.**
For those windows the loss lies in `[discard, 1]`, so the arm's damage sum lies
in `[S, S + sum of their discards]` where `S` assumes every one of them was
already counted as damage. Both ends go in the ledger with the interval's width
and the number of windows behind it.

Usage:
    python experiments/recount_damage.py --results results/xl --seeds 0,1,2
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from audit import _nmse  # noqa: E402
from corpus import build_corpus  # noqa: E402
from run_agent import SCALES  # noqa: E402

from introact_ts.structure import _discard_distortion  # noqa: E402

OPS = ("IMPUTE", "DESPIKE", "DENOISE", "RESEGMENT")
VALUE_OPS = ("IMPUTE", "DESPIKE", "DENOISE")

#: Arms that never crop, so the corrected definition returns their old number.
#: This is a property of the algorithms, not a measurement.
NON_CROPPING = ("L0_no_action", "L1_screen", "L2_imr", "L3_mtcsc",
                "L7_learn2clean", "oracle")

#: Arms that commit no edit at all, so they have no damage rate to correct.
SELECTION = ("L4_data_oob", "L5_timeinf", "L6_ltsv", "L8_tsrating")


def crop_bounds(trace):
    """Cumulative [lo, hi) of every accepted crop, or None if a param is absent."""
    lo, hi = None, None
    for st in trace["steps"]:
        if st["verdict"] != "ACCEPTED" or st["action"] != "RESEGMENT":
            continue
        p = st["params"]
        if "lo" not in p or "hi" not in p:
            return None
        a, b = int(p["lo"]), int(p["hi"])
        if lo is None:
            lo, hi = a, b
        else:
            lo, hi = lo + a, lo + b
    return None if lo is None else (lo, hi)


def classify(trace):
    acc = [s for s in trace["steps"]
           if s["verdict"] == "ACCEPTED" and s["action"] in OPS]
    has_r = any(s["action"] == "RESEGMENT" for s in acc)
    has_v = any(s["action"] in VALUE_OPS for s in acc)
    if not acc:
        return "none"
    if has_r and not has_v:
        return "crop_only"
    if has_v and not has_r:
        return "value_only"
    return "both"


def score_arm(traces, byid, old_damage_rate):
    """Corrected damage as an interval, using the old rate for what it cannot see."""
    committed = 0
    exact_new = 0.0      # sum of max(worse, disc) over rebuildable windows
    exact_worse = 0      # sum of worse over the same windows
    both_disc = []       # discards of windows whose old term is unrecoverable
    counts = {"none": 0, "crop_only": 0, "value_only": 0, "both": 0,
              "no_params": 0}
    for t in traces:
        w = byid.get(int(t["window_id"]))
        if w is None or w.clean_series is None or not t["modified"]:
            continue
        committed += 1
        kind = classify(t)
        counts[kind] += 1
        if kind in ("none", "value_only"):
            continue                      # discard is zero, loss is unchanged
        bounds = crop_bounds(t)
        if bounds is None:
            counts["no_params"] += 1
            continue
        lo, hi = bounds
        x = np.asarray(w.series, dtype=np.float64)
        disc = _discard_distortion(x, {"lo": lo, "hi": hi})
        if kind == "both":
            both_disc.append(disc)
            continue
        c = np.asarray(w.clean_series, dtype=np.float64)
        ref_var = float(np.var(c - np.median(c)))
        b = _nmse(x, c, ref_var)
        a = _nmse(x[lo:hi], c[lo:], ref_var)
        worse = 1.0 if a > b + 1e-9 else 0.0
        exact_worse += worse
        exact_new += max(worse, disc)

    if committed == 0:
        return None
    # The old damage sum over every committed window, from the recorded rate.
    old_sum = old_damage_rate * committed
    # What the unrebuildable windows contributed under the old definition.
    rest = old_sum - exact_worse
    lower = (exact_new + rest) / committed
    upper = (exact_new + rest + float(sum(both_disc))) / committed
    return {"committed": committed, "counts": counts,
            "old_rate": old_damage_rate,
            "new_lower": float(lower), "new_upper": float(upper),
            "interval_width": float(upper - lower),
            "n_uncertain": len(both_disc),
            "uncertain_discard_sum": float(sum(both_disc)),
            "exact_new": float(exact_new), "exact_worse": float(exact_worse)}


def load_old_rates(results_dir):
    """Damage rate per arm per seed, from the result files already written."""
    out = {}
    for p in Path(results_dir).glob("ablation_*_seed*.json"):
        b = json.loads(p.read_text(encoding="utf-8"))
        lvl = p.stem.replace("ablation_", "").rsplit("_seed", 1)[0]
        out.setdefault(lvl, {})[int(b["seed"])] = b["damage_rate"]
    for p in Path(results_dir).parent.glob("main_table_seed*.json"):
        b = json.loads(p.read_text(encoding="utf-8"))
        s = int(b["seed"])
        for arm, row in b["rows"].items():
            if isinstance(row.get("damage_rate"), (int, float)):
                out.setdefault(arm, {})[s] = row["damage_rate"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "results" / "xl"))
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--scale", default="xl")
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--out", default=str(ROOT / "results" / "damage_recount.json"))
    args = ap.parse_args()

    seeds = [int(x) for x in args.seeds.replace(" ", "").split(",") if x]
    old = load_old_rates(args.results)
    print(f"old damage rates found for {len(old)} arms")

    corpora = {}
    for s in seeds:
        spec = SCALES[args.scale]
        spec.seed = s
        corpora[s] = {w.window_id: w for w in build_corpus(spec, args.source)}

    # Group every trace file by arm and seed.
    per = {}
    for f in sorted(Path(args.results).glob("*_traces.jsonl")):
        seed = next((s for s in seeds
                     if f"seed{s}_" in f.name or f"seed_{s}_" in f.name), None)
        if seed is None:
            continue
        for line in f.open(encoding="utf-8"):
            r = json.loads(line)
            per.setdefault(r["arm"], {}).setdefault(seed, []).append(r)

    print()
    print("arms that never crop, old value carries over unchanged")
    carried = {}
    for arm in NON_CROPPING:
        if arm in old and old[arm]:
            v = np.array(list(old[arm].values()))
            carried[arm] = {"mean": float(v.mean()),
                            "std": float(v.std(ddof=1)) if len(v) > 1 else 0.0,
                            "reason": "algorithm never discards time points, "
                                      "discard_share is identically zero"}
            print(f"  {arm:16s}{v.mean():.4f} +- "
                  f"{(v.std(ddof=1) if len(v) > 1 else 0.0):.4f}   unchanged")

    print()
    print("agent arms, corrected damage as an interval")
    print(f"{'arm':18s}{'old':>9s}{'new lower':>11s}{'new upper':>11s}"
          f"{'width':>8s}{'uncertain':>11s}{'no params':>11s}")
    out = {}
    for arm in sorted(per):
        if arm in NON_CROPPING or arm in SELECTION:
            continue
        rows = []
        for s in seeds:
            if s not in per[arm] or arm not in old or s not in old[arm]:
                continue
            r = score_arm(per[arm][s], corpora[s], old[arm][s])
            if r:
                rows.append(r)
        if not rows:
            continue
        lo = np.array([r["new_lower"] for r in rows])
        up = np.array([r["new_upper"] for r in rows])
        od = np.array([r["old_rate"] for r in rows])
        nun = sum(r["n_uncertain"] for r in rows)
        nnp = sum(r["counts"]["no_params"] for r in rows)
        out[arm] = {
            "n_seeds": len(rows),
            "old_mean": float(od.mean()),
            "new_lower_mean": float(lo.mean()),
            "new_lower_std": float(lo.std(ddof=1)) if len(lo) > 1 else 0.0,
            "new_upper_mean": float(up.mean()),
            "new_upper_std": float(up.std(ddof=1)) if len(up) > 1 else 0.0,
            "interval_width_mean": float((up - lo).mean()),
            "n_uncertain_total": nun, "n_no_params_total": nnp,
            "per_seed": rows,
        }
        print(f"{arm:18s}{od.mean():9.4f}{lo.mean():11.4f}{up.mean():11.4f}"
              f"{(up - lo).mean():8.4f}{nun:11d}{nnp:11d}")

    wide = {a: v for a, v in out.items() if v["interval_width_mean"] > 0.01}
    print()
    if wide:
        print("arms whose interval is wider than 0.01, listed rather than "
              "collapsed to a midpoint")
        for a, v in sorted(wide.items(),
                           key=lambda kv: -kv[1]["interval_width_mean"]):
            print(f"  {a:18s}width {v['interval_width_mean']:.4f} from "
                  f"{v['n_uncertain_total']} windows that both cropped and "
                  f"rewrote values")
    else:
        print("every interval is narrower than 0.01")

    Path(args.out).write_text(json.dumps(
        {"seeds": seeds, "carried_over": carried, "agent_arms": out},
        indent=1, default=float), encoding="utf-8")
    print()
    print("___DAMAGE_RECOUNT_DONE___")


if __name__ == "__main__":
    main()
