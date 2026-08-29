"""Phase 0. Check the three diagnoses before touching any operator or threshold.

The playbook's order is configuration fault, then artefact, then method. Three
findings from the trajectory analysis look like method problems and two of them
are almost certainly measurement artefacts, so they are checked here first. A
fourth check recomputes the acceptance table from the raw traces without
reusing any function from the script that produced the first version, because a
number that decides a method change has to come from two independent paths.

Everything here reads flushed traces. No GPU, no model, no rerun.

  check 1  structural distortion under an operator that changes length
  check 2  what the probe feeds the model where the series has gaps
  check 3  the distortion distribution of DENOISE against tau
  check 4  the acceptance table, recomputed independently

Usage:
    python experiments/verify_diagnoses.py --results results/xl --seeds 0,1,2
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent

OPERATORS = ("IMPUTE", "DESPIKE", "DENOISE", "RESEGMENT")
PROTECTED = ("clean", "hard", "rare_valid", "changepoint")
TAU = 0.02


def read(results_dir, arm, seeds, pattern):
    for s in seeds:
        p = Path(results_dir) / pattern.format(seed=s)
        if not p.exists():
            continue
        for line in p.open(encoding="utf-8"):
            r = json.loads(line)
            if r.get("arm") == arm:
                r["seed"] = s
                yield r


def check1(rows):
    """Does the structural condition ever see an operator that crops.

    `structure.align_for_action` slices the original down to `[lo, hi)` before
    comparing, so the discarded span is not an input to the measurement, and the
    retained span is point wise identical because RESEGMENT crops without
    rewriting. The prediction is therefore not merely that distortion is small
    but that it is identically zero and that no candidate is ever refused on
    structural grounds.
    """
    print("check 1, structural distortion under a length changing operator")
    print("  code: src/introact_ts/structure.py:258 align_for_action slices the")
    print("        original to [lo, hi) so the discarded span is not compared")
    out = {}
    for op in OPERATORS:
        vals, structural = [], 0
        for r in rows:
            for st in r["steps"]:
                if st["action"] != op:
                    continue
                vals.append(st["struct_distortion"])
                structural += int(st["verdict"] == "ROLLED_BACK_STRUCTURE")
        a = np.asarray(vals, dtype=np.float64)
        out[op] = {"n": len(a),
                   "max": float(a.max()) if len(a) else None,
                   "all_zero": bool(len(a) and np.all(a == 0.0)),
                   "structural_rollbacks": structural}
        print(f"  {op:12s}n={len(a):5d}  max distortion "
              f"{(a.max() if len(a) else float('nan')):.6f}  "
              f"structural rollbacks {structural:5d}"
              + ("   <-- never judged on structure" if structural == 0 else ""))
    ok = out["RESEGMENT"]["structural_rollbacks"] == 0
    print(f"  verdict: the measurement is {'BROKEN' if ok else 'sound'} for "
          f"cropping operators")
    return out


def check1_detail(rows, n=20):
    """The windows the fault matters on: cropping accepted inside a protected
    layer. Reports how much was discarded and what distortion was reported."""
    print()
    print("  20 accepted RESEGMENT commits inside a protected stratum")
    print(f"  {'window':>8s}{'stratum':>13s}{'kept':>7s}{'of':>6s}"
          f"{'discarded':>11s}{'distortion':>12s}{'gain':>10s}")
    picked = []
    for r in rows:
        if r["stratum"] not in PROTECTED:
            continue
        for st in r["steps"]:
            if st["action"] != "RESEGMENT" or st["verdict"] != "ACCEPTED":
                continue
            lo = int(st["params"].get("lo", 0))
            hi = int(st["params"].get("hi", 0))
            kept = hi - lo
            gain = None
            if r["dist_before"] is not None and r["dist_after"] is not None:
                gain = r["dist_before"] - r["dist_after"]
            picked.append({"window_id": r["window_id"], "stratum": r["stratum"],
                           "kept": kept, "lo": lo, "hi": hi,
                           "distortion": st["struct_distortion"], "gain": gain})
    picked.sort(key=lambda d: d["kept"])
    for d in picked[:n]:
        total = 512
        disc = 1.0 - d["kept"] / total
        g = d["gain"] if d["gain"] is not None else float("nan")
        print(f"  {d['window_id']:8d}{d['stratum']:>13s}{d['kept']:7d}"
              f"{total:6d}{disc:11.3f}{d['distortion']:12.6f}{g:10.4f}")
    if picked:
        disc = np.asarray([1.0 - d["kept"] / 512 for d in picked])
        print(f"  {len(picked)} such commits, median discarded "
              f"{np.median(disc):.3f}, max discarded {disc.max():.3f}, "
              f"distortion max {max(d['distortion'] for d in picked):.6f}")
    return picked[:n]


def check2():
    """What the probe feeds the model where the series has gaps."""
    print()
    print("check 2, what the probe feeds the model on a window with gaps")
    print("  code: src/introact_ts/probe.py:104 _naive_fill carries the last")
    print("        valid observation forward and back fills a leading gap")
    print("  so a gap reaches the model as a frozen plateau, not as a hole,")
    print("  and the docstring states this is deliberate: a zero fill would")
    print("  make every imputation unmeasurable")
    print("  consequence: IMPUTE competes against forward fill rather than")
    print("  against a hole, so its utility gain is the difference between two")
    print("  plausible reconstructions and is small by construction")
    return {"fill": "forward fill with leading back fill",
            "deliberate": True, "location": "src/introact_ts/probe.py:104"}


def check3(rows):
    """DENOISE's distortion distribution against tau."""
    print()
    print("check 3, DENOISE distortion against tau")
    vals = [st["struct_distortion"] for r in rows for st in r["steps"]
            if st["action"] == "DENOISE"]
    a = np.asarray(vals, dtype=np.float64)
    if not len(a):
        print("  no DENOISE attempts")
        return {}
    q = {f"q{p:02d}": float(np.percentile(a, p)) for p in (5, 25, 50, 75, 95)}
    print(f"  n={len(a)}  " + "  ".join(f"{k}={v:.4f}" for k, v in q.items()))
    print(f"  share below tau {TAU}: {float((a < TAU).mean()):.4f}")
    verdict = ("structurally impossible at this tau" if q["q50"] > 0.1
               else "close to the threshold, a calibration question")
    print(f"  median {q['q50']:.4f} against tau {TAU}, so this is {verdict}")
    return {"n": len(a), **q, "share_below_tau": float((a < TAU).mean()),
            "verdict": verdict}


def check4(rows):
    """The acceptance table, recomputed from raw traces independently."""
    print()
    print("check 4, acceptance recomputed from the raw traces")
    att = Counter()
    acc = Counter()
    prot = Counter()
    by_layer = defaultdict(Counter)
    for r in rows:
        for st in r["steps"]:
            op = st["action"]
            if op not in OPERATORS:
                continue
            att[op] += 1
            if st["verdict"] == "ACCEPTED":
                acc[op] += 1
                by_layer[op][r["stratum"]] += 1
                if r["stratum"] in PROTECTED:
                    prot[op] += 1
    print(f"  {'operator':12s}{'attempts':>10s}{'accepted':>10s}"
          f"{'rate':>9s}{'on protected':>14s}")
    out = {}
    for op in OPERATORS:
        rate = acc[op] / att[op] if att[op] else float("nan")
        out[op] = {"attempts": att[op], "accepted": acc[op],
                   "rate": rate, "on_protected": prot[op],
                   "by_stratum": dict(by_layer[op])}
        print(f"  {op:12s}{att[op]:10d}{acc[op]:10d}{rate:9.4f}{prot[op]:14d}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "results" / "xl"))
    ap.add_argument("--arm", default="f_full")
    ap.add_argument("--pattern", default="ablation_f_full_seed{seed}_traces.jsonl")
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--out", default=str(ROOT / "results" / "phase0_diagnoses.json"))
    args = ap.parse_args()

    seeds = [int(x) for x in args.seeds.replace(" ", "").split(",") if x]
    rows = list(read(args.results, args.arm, seeds, args.pattern))
    print(f"{len(rows)} window traces, arm {args.arm}, seeds {seeds}")
    print()

    c1 = check1(rows)
    d1 = check1_detail(rows)
    c2 = check2()
    c3 = check3(rows)
    c4 = check4(rows)

    Path(args.out).write_text(json.dumps(
        {"seeds": seeds, "check1_structure": c1, "check1_examples": d1,
         "check2_probe_fill": c2, "check3_denoise": c3,
         "check4_acceptance": c4}, indent=1, default=float), encoding="utf-8")
    print()
    print("___PHASE0_DONE___")


if __name__ == "__main__":
    main()
