"""Second local prototype: bank size trend, merged-bank LOPO selection, and the
harm-cap anchor.  Same frozen v4.4 artefacts as proto_v46_selector_variants.py.

Questions answered on CPU only:
  1. Does more replay history help?  (25 / 50 / 100 % of replay-fit parents.)
  2. Does selecting (k, beta) by leave-one-parent-out on a larger bank
     (replay-fit + gate) transfer to TRAIN-eval better than the 48-parent gate?
  3. What operating point does a harm cap anchored on the best fixed action give?
"""
from __future__ import annotations

import collections
import sys
import time

import numpy as np

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
from proto_v46_selector_variants import (  # noqa: E402
    ACTIONS, NONREF, Variant, evaluate, load_all, paired_boot,
)
from introact_ts.v44 import protocol as P  # noqa: E402

RNG = np.random.default_rng(7)


def subsample(cats, frac, seed):
    parents = sorted({c.parent for c in cats})
    rng = np.random.default_rng(seed)
    keep = set(rng.choice(parents, max(3, int(round(len(parents) * frac))), replace=False))
    return [c for c in cats if c.parent in keep]


def lopo_select(v, cats_bank, kgrid, bgrid, cap):
    """Leave-one-parent-out on the bank itself: every request is scored against
    a bank that excludes its own parent.  Returns the chosen (k, beta)."""
    parents = sorted({c.parent for c in cats_bank})
    by_parent = collections.defaultdict(list)
    for c in cats_bank:
        by_parent[c.parent].append(c)
    grid = {(k, b): {} for k in kgrid for b in bgrid}
    for p in parents:
        held = by_parent[p]
        rest = [c for c in cats_bank if c.parent != p]
        v.prepare(rest)
        for (k, b) in grid:
            grid[(k, b)].update(v.select(held, k, b))
    scored = []
    for (k, b), sel in grid.items():
        e = evaluate(cats_bank, sel, "x")
        scored.append((k, b, e))
    ok = [x for x in scored if x[2]["hir"] <= cap] or [max(scored, key=lambda x: x[1])]
    k, b, e = min(ok, key=lambda x: x[2]["mase"])
    return k, b, e, scored


def main():
    t0 = time.time()
    data = load_all()
    print("loaded", round(time.time() - t0, 1), "s", flush=True)
    kgrid, bgrid = (8, 16, 32, 64), (0.0, 1.0, 1.64)
    variants = {
        "BASE": Variant("BASE", kgrid=kgrid, bgrid=bgrid),
        "REL+FW+HYB": Variant("REL+FW+HYB", target="rel", fw="ridge", hybrid=True, kgrid=kgrid, bgrid=bgrid),
        "HYB": Variant("HYB", hybrid=True, kgrid=kgrid, bgrid=bgrid),
    }
    # 1. bank size trend at the v44 frozen point (k=8, beta=1.64) and at beta=0
    print("== bank size trend (train_eval MASE, mean over 3 subsample seeds) ==")
    for name, v in variants.items():
        for bb in ("bolt", "timesfm"):
            fit, ev = data[(bb, "replay_fit")], data[(bb, "train_eval")]
            row = []
            for frac in (0.25, 0.5, 1.0):
                vals = []
                for seed in (1, 2, 3) if frac < 1.0 else (1,):
                    v.prepare(subsample(fit, frac, seed))
                    for beta in (1.64, 0.0):
                        vals.append((beta, evaluate(ev, v.select(ev, 16, beta), bb)["mase"]))
                m164 = np.mean([x[1] for x in vals if x[0] == 1.64])
                m0 = np.mean([x[1] for x in vals if x[0] == 0.0])
                row.append(f"{int(frac*100):3d}%: b1.64={m164:.4f} b0={m0:.4f}")
            print(f"  {name:12s} {bb:8s} " + " | ".join(row), flush=True)

    # 2. merged bank (replay_fit + gate) with LOPO selection, cap on conditional HIR
    print("== merged bank + LOPO selection (cap = conditional HIR of best fixed non-reference action on the bank) ==")
    for name, v in variants.items():
        for bb in ("bolt", "timesfm"):
            fit, gate, ev = data[(bb, "replay_fit")], data[(bb, "gate")], data[(bb, "train_eval")]
            bank_cats = fit + gate
            # anchor: conditional harmful rate of the best fixed non-reference action on the bank
            def mean_util(a):
                vals = [c.actions[a].utility for c in bank_cats if c.actions.get(a) and c.actions[a].utility is not None]
                return float(np.mean(vals)) if vals else -1e9
            bf = max(NONREF, key=mean_util)
            bf_hir = float(np.mean([c.actions[bf].utility < 0 for c in bank_cats if c.actions[bf].utility is not None]))
            k, b, e_lopo, scored = lopo_select(v, bank_cats, kgrid, bgrid, cap=bf_hir)
            v.prepare(bank_cats)
            se = v.select(ev, k, b)
            e = evaluate(ev, se, bb)
            keep = {c.episode: "KEEP" for c in ev}
            bfsel = {c.episode: (bf if bf in c.legal() else "KEEP") for c in ev}
            pt_k, lo_k, hi_k = paired_boot(ev, se, keep, bb, n=600)
            pt_b, lo_b, hi_b = paired_boot(ev, se, bfsel, bb, n=600)
            print(f"  {name:12s} {bb:8s} anchor={bf}(cHIR={bf_hir:.2f}) chosen k={k} b={b:.2f} "
                  f"LOPO mase={e_lopo['mase']:.4f} IR={e_lopo['ir']:.2f} cHIR={e_lopo['hir']:.2f} || "
                  f"train_eval mase={e['mase']:.4f} IR={e['ir']:.2f} cHIR={e['hir']:.2f} "
                  f"dKEEP={pt_k:+.4f}[{lo_k:+.4f},{hi_k:+.4f}] dBF={pt_b:+.4f}[{lo_b:+.4f},{hi_b:+.4f}]", flush=True)
            top = sorted(scored, key=lambda x: x[2]["mase"])[:4]
            print("     LOPO top-4:", [(kk, bt, round(ee["mase"], 4), round(ee["hir"], 2), round(ee["ir"], 2)) for kk, bt, ee in top], flush=True)


if __name__ == "__main__":
    main()
