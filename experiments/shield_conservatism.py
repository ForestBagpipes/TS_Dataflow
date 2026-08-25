"""How conservative is the shield, measured on the candidates it turned down.

The main table puts `spec_veto` and `introact` close on damage and far apart on
repair. Read alone that reads as the shield costing repair for nothing. This
measures the thing that decides how to read it: **of the candidates the shield
rolled back, how many would have improved the window had they been committed.**

A rolled back candidate carries everything needed to answer that. The trace
records its utility change and its structural distortion, and the sandbox copy
means the candidate was actually executed, so the counterfactual is measured
rather than modelled.

Three quantities, all over rolled back candidates:

  would have helped   the candidate moved the window closer to its clean
                      reference. This is the cost of the shield, stated plainly
  would have harmed   it moved the window further away. This is what the shield
                      is for
  ratio               the first over the total, so a low ratio means the shield
                      is discriminating and a high one means it is merely strict

**The split by rejecting condition is void and must not be quoted.** It was
intended to separate caution from disagreement, and it cannot, because the proxy
below is the same quantity the conditions are defined on. `verify` short
circuits: the utility condition is checked first and the structural condition
only sees candidates that already passed it. So every structurally vetoed
candidate has a positive utility change by construction and the ratio is exactly
1.000, and every utility vetoed one has a non positive change and the ratio is
near zero. Measured: 387 of 387 and 57 of 770. Neither number carries
information. They are the definitions restating themselves.

**The split by stratum is valid**, because nothing in it depends on the order
the conditions are checked in.

**The proxy is the limitation.** Whether committing a candidate would have
helped is asked here through the utility change, and section 2.2 shows that
signal disagrees with fidelity on exactly the protected data this question
matters for. `experiments/shield_replay.py` answers it properly by replaying the
candidate and measuring the distance to the clean reference. Use that for any
number that goes in the paper. This file is kept for the stratum split and for
the record of why the condition split does not work.

Usage:
    python -u experiments/shield_conservatism.py --traces results/xl/...json
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

#: Verdicts that mean the candidate was executed on the copy and then refused.
ROLLED_BACK = ("ROLLED_BACK_UTILITY", "ROLLED_BACK_STRUCTURE",
               "ROLLED_BACK_RISK")


def counterfactual(records, window):
    """Per rolled back candidate, would committing it have helped.

    The trace stores the utility before and after each candidate. Fidelity to
    the clean reference is not stored per candidate, so the utility change is
    used as the stand in and its limits are stated: it is the same signal
    section 2.2 shows can disagree with fidelity on protected data. The split by
    rejecting condition is what keeps that from being hidden, since the utility
    vetoes are exactly the cases where the two disagree by construction.
    """
    out = []
    for r in records:
        v = r.get("verdict") if isinstance(r, dict) else getattr(r, "verdict", None)
        v = getattr(v, "value", v)
        if v not in ROLLED_BACK:
            continue
        du = (r.get("delta_utility") if isinstance(r, dict)
              else getattr(r, "delta_utility", 0.0))
        out.append({"verdict": v, "delta_utility": float(du),
                    "stratum": window.get("stratum") if isinstance(window, dict)
                    else getattr(window, "stratum", None)})
    return out


def summarise(rows):
    n = len(rows)
    if not n:
        return {"n": 0}
    helped = sum(1 for r in rows if r["delta_utility"] > 0)
    by_verdict = {}
    for v in ROLLED_BACK:
        sub = [r for r in rows if r["verdict"] == v]
        if not sub:
            continue
        h = sum(1 for r in sub if r["delta_utility"] > 0)
        by_verdict[v] = {"n": len(sub), "would_have_helped": h,
                         "ratio": h / len(sub)}
    by_stratum = {}
    for s in sorted({r["stratum"] for r in rows if r["stratum"]}):
        sub = [r for r in rows if r["stratum"] == s]
        h = sum(1 for r in sub if r["delta_utility"] > 0)
        by_stratum[s] = {"n": len(sub), "would_have_helped": h,
                         "ratio": h / len(sub)}
    return {
        "n": n, "would_have_helped": helped, "would_have_harmed": n - helped,
        "ratio": helped / n,
        "by_verdict": by_verdict, "by_stratum": by_stratum,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces", required=True,
                    help="a governance trace file from a run of the full method")
    ap.add_argument("--arm", default="introact")
    ap.add_argument("--out", default=str(ROOT / "results" / "shield_conservatism.json"))
    args = ap.parse_args()

    blob = json.loads(Path(args.traces).read_text(encoding="utf-8"))
    rows_in = blob[args.arm] if args.arm in blob else blob
    rows = []
    for t in rows_in:
        rows.extend(counterfactual(t.get("steps") or t.get("records") or [], t))

    rep = summarise(rows)
    print(f"rolled back candidates: {rep.get('n', 0)}")
    if rep.get("n"):
        print(f"  would have helped {rep['would_have_helped']} "
              f"({rep['ratio']:.3f})")
        print(f"  would have harmed {rep['would_have_harmed']}")
        print()
        print("by rejecting condition")
        for v, d in rep["by_verdict"].items():
            print(f"  {v:26s} n={d['n']:5d}  helped={d['would_have_helped']:5d}  "
                  f"ratio={d['ratio']:.3f}")
        print()
        print("by stratum")
        for s, d in rep["by_stratum"].items():
            print(f"  {s:16s} n={d['n']:5d}  helped={d['would_have_helped']:5d}  "
                  f"ratio={d['ratio']:.3f}")

    Path(args.out).write_text(json.dumps(rep, indent=1, default=float),
                              encoding="utf-8")
    print("___SHIELD_CONSERVATISM_DONE___", flush=True)


if __name__ == "__main__":
    main()
