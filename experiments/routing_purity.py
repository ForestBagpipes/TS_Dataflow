"""Where the proposer sends each operator, against what the window actually has.

DESPIKE's family threshold calibrates to zero because its candidates average a
loss of 0.1951 on the contaminated layer, above the 0.03 target. The question
this answers is whether that average is carried by candidates the proposer
should never have made: a DESPIKE aimed at a window whose defect is a level
shift is a routing error, and its damage says nothing about despiking.

The same question applies to every family, so the table is a contingency of
routed family against the window's true contamination kind. That table is also
a measurement of the perception layer's second kind of error: not "is this
window damaged" but "damaged how", which is independent of the 58 percent
mislabelling rate already recorded.

**The ground truth is used here and must not be used anywhere else.** This is an
offline diagnosis. Any repair may only change the routing logic in
`propose_actions` using signals available at deployment. A deployment path that
filtered on the true contamination kind would be the sixth instance of
calibrating on a population that does not exist at run time.

Usage:
    python experiments/routing_purity.py
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

PROTECTED = ("clean", "hard", "rare_valid", "changepoint", "clean_ood")

#: Which contamination kind each operator is the intended answer to. Taken from
#: `policy._DEFECT_OPERATOR` and the corpus's injection kinds, not invented here.
INTENDED = {
    "DESPIKE": ("spike",),
    "IMPUTE": ("missing_block", "missing_scattered", "flatline"),
    "DENOISE": ("noise",),
    "RESEGMENT": ("level_shift",),
}
ALPHA = 0.03


def load(path):
    rows = []
    for line in Path(path).open(encoding="utf-8"):
        rec = json.loads(line)
        for c in rec["candidates"]:
            c["window_id"] = rec["window_id"]
            rows.append(c)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default=str(ROOT / "results" / "family_scores.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "results" / "routing_purity.json"))
    args = ap.parse_args()

    rows = load(args.scores)
    fams = sorted({r["family"] for r in rows})
    con = [r for r in rows if r["stratum"] == "contaminated"]
    prot = [r for r in rows if r["stratum"] in PROTECTED]
    print(f"{len(rows)} candidates: {len(con)} on contaminated windows, "
          f"{len(prot)} on protected ones")

    kinds = sorted({str(r["contamination"]) for r in con})
    print()
    print("routed family against the window's true contamination kind, "
          "contaminated layer only")
    print(f"{'family':11s}" + "".join(f"{k[:16]:>18s}" for k in kinds))
    counts = defaultdict(dict)
    losses = defaultdict(dict)
    for f in fams:
        sub = [r for r in con if r["family"] == f]
        cells = []
        for k in kinds:
            g = [r for r in sub if str(r["contamination"]) == k]
            counts[f][k] = len(g)
            losses[f][k] = float(np.mean([r["loss"] for r in g])) if g else None
            cells.append(f"{len(g):5d} L={losses[f][k]:.3f}" if g
                         else f"{0:5d}     -")
        print(f"{f:11s}" + "".join(f"{c:>18s}" for c in cells))

    print()
    print("on target against off target, per family, contaminated layer")
    print(f"{'family':11s}{'on n':>7s}{'on loss':>10s}{'off n':>7s}"
          f"{'off loss':>10s}{'family mean':>13s}{'on target below alpha':>23s}")
    verdict = {}
    for f in fams:
        sub = [r for r in con if r["family"] == f]
        want = INTENDED.get(f, ())
        on = [r for r in sub if str(r["contamination"]) in want]
        off = [r for r in sub if str(r["contamination"]) not in want]
        lon = float(np.mean([r["loss"] for r in on])) if on else float("nan")
        loff = float(np.mean([r["loss"] for r in off])) if off else float("nan")
        lall = float(np.mean([r["loss"] for r in sub])) if sub else float("nan")
        ok = bool(len(on) >= 30 and lon < ALPHA)
        verdict[f] = {"on_n": len(on), "on_loss": lon, "off_n": len(off),
                      "off_loss": loff, "family_mean": lall,
                      "on_target_below_alpha": ok,
                      "judgeable": bool(len(on) >= 30)}
        note = ("yes" if ok else
                ("no" if len(on) >= 30 else f"unjudgeable, n={len(on)}"))
        print(f"{f:11s}{len(on):7d}{lon:10.4f}{len(off):7d}{loff:10.4f}"
              f"{lall:13.4f}{note:>23s}")

    print()
    print("what the off target candidates are, per family")
    for f in fams:
        want = INTENDED.get(f, ())
        sub = [r for r in con if r["family"] == f
               and str(r["contamination"]) not in want]
        if not sub:
            continue
        c = defaultdict(lambda: [0, 0.0])
        for r in sub:
            k = str(r["contamination"])
            c[k][0] += 1
            c[k][1] += r["loss"]
        parts = ", ".join(f"{k} {v[0]} at {v[1] / v[0]:.3f}"
                          for k, v in sorted(c.items(), key=lambda kv: -kv[1][0]))
        print(f"  {f:11s}{parts}")

    print()
    print("protected layer candidates, by routed family")
    print(f"{'family':11s}{'n':>7s}{'share of family pool':>22s}{'mean loss':>11s}")
    for f in fams:
        sub = [r for r in prot if r["family"] == f]
        allf = [r for r in rows if r["family"] == f]
        if not allf:
            continue
        print(f"{f:11s}{len(sub):7d}{len(sub) / len(allf):22.4f}"
              f"{float(np.mean([r['loss'] for r in sub])) if sub else float('nan'):11.4f}")

    d = verdict.get("DESPIKE", {})
    print()
    print("the DESPIKE question")
    if not d.get("judgeable"):
        print(f"  unjudgeable: only {d.get('on_n', 0)} candidates land on a "
              f"true spike window")
    elif d["on_target_below_alpha"]:
        print(f"  on target loss {d['on_loss']:.4f} is below alpha {ALPHA}, "
              f"while off target is {d['off_loss']:.4f} over {d['off_n']} "
              f"candidates")
        print("  so the zero threshold is a consequence of routing error and a "
              "routing fix should be tried before accepting it")
    else:
        print(f"  on target loss {d['on_loss']:.4f} is at or above alpha "
              f"{ALPHA}, so the zero threshold is honest and not a routing "
              f"artefact")

    Path(args.out).write_text(json.dumps(
        {"alpha": ALPHA, "counts": counts, "losses": losses,
         "on_off": verdict}, indent=1, default=float), encoding="utf-8")
    print()
    print("___ROUTING_PURITY_DONE___")


if __name__ == "__main__":
    main()
