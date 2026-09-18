"""Third local prototype: kNN versus the parametric ablation on the merged bank,
their bank-size trends, the always-act ablation, and the beta curve.

Same frozen v4.4 artefacts.  CPU only.  Run from the repository root.
"""
from __future__ import annotations

import sys
import time

import numpy as np

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
from proto_v46_selector_variants import (  # noqa: E402
    ACTIONS, NONREF, Variant, evaluate, load_all, paired_boot, project, ridge_fit, ridge_pred,
)
from proto_v46_selector_variants2 import subsample  # noqa: E402
from introact_ts.v44 import protocol as P  # noqa: E402


class Parametric(Variant):
    """A5 as implemented in v44 methods.parametric: one ridge (or depth-3 CART)
    per action on the raw state, score = prediction, act if positive."""

    def __init__(self, name, kind="ridge"):
        super().__init__(name)
        self.kind = kind

    def prepare(self, cats_fit):
        super().prepare(cats_fit)
        self.models = {}
        for a in NONREF:
            b = self.bank[a]
            if self.kind == "ridge":
                self.models[a] = ridge_fit(b["Z"], b["g"], alpha=1.0)
            else:
                from sklearn.tree import DecisionTreeRegressor
                self.models[a] = DecisionTreeRegressor(max_depth=3, min_samples_leaf=96,
                                                       random_state=101).fit(b["Z"], b["g"])
        return self

    def score(self, cat, a, k, beta):
        z = project(cat.actions[a].state_vector, self.blocks)[None]
        m = self.models[a]
        mu = float(ridge_pred(m, z)[0]) if self.kind == "ridge" else float(m.predict(z)[0])
        return mu, mu


def always_act(v, cats, k, beta):
    """Ablation: remove the KEEP option, execute the top-scored action regardless of sign."""
    return v.select(cats, k, beta, gate=False)


def main():
    t0 = time.time()
    data = load_all()
    print("loaded", round(time.time() - t0, 1), "s", flush=True)
    knn = Variant("kNN", kgrid=(8, 16, 32, 64))
    ridge = Parametric("A5 ridge", "ridge")
    cart = Parametric("A5 cart", "cart")

    print("== bank size trend, merged bank (replay_fit+gate) subsampled, train_eval MASE, beta=0 ==")
    for bb in ("bolt", "timesfm"):
        bank_cats = data[(bb, "replay_fit")] + data[(bb, "gate")]
        ev = data[(bb, "train_eval")]
        for name, v, k in (("kNN k=16", knn, 16), ("kNN k=32", knn, 32), ("A5 ridge", ridge, 0), ("A5 cart", cart, 0)):
            row = []
            for frac in (0.125, 0.25, 0.5, 1.0):
                vals = []
                for seed in ((1, 2, 3) if frac < 1.0 else (1,)):
                    v.prepare(subsample(bank_cats, frac, seed))
                    vals.append(evaluate(ev, v.select(ev, k, 0.0), bb)["mase"])
                row.append(f"{int(frac*100):3d}%={np.mean(vals):.4f}")
            print(f"  {bb:8s} {name:10s} " + " | ".join(row), flush=True)

    print("== merged bank, train_eval: kNN(beta=0) vs A5, always-act, beta curve ==")
    for bb in ("bolt", "timesfm"):
        bank_cats = data[(bb, "replay_fit")] + data[(bb, "gate")]
        ev = data[(bb, "train_eval")]
        keep = {c.episode: "KEEP" for c in ev}
        knn.prepare(bank_cats)
        ridge.prepare(bank_cats)
        cart.prepare(bank_cats)
        k_best = 8 if bb == "bolt" else 16
        se = knn.select(ev, k_best, 0.0)
        e = evaluate(ev, se, bb)
        er = evaluate(ev, ridge.select(ev, 0, 0.0), bb)
        ec = evaluate(ev, cart.select(ev, 0, 0.0), bb)
        ea = evaluate(ev, always_act(knn, ev, k_best, 0.0), bb)
        print(f"  {bb:8s} kNN k={k_best} b=0: {e['mase']:.4f} IR={e['ir']:.2f} cHIR={e['hir']:.2f} | A5 ridge {er['mase']:.4f} IR={er['ir']:.2f} cHIR={er['hir']:.2f}"
              f" | A5 cart {ec['mase']:.4f} IR={ec['ir']:.2f} cHIR={ec['hir']:.2f} | always-act {ea['mase']:.4f} IR={ea['ir']:.2f} cHIR={ea['hir']:.2f}", flush=True)
        for refname, ref in (("A5 ridge", ridge.select(ev, 0, 0.0)), ("A5 cart", cart.select(ev, 0, 0.0))):
            pt, lo, hi = paired_boot(ev, se, ref, bb, n=600)
            print(f"     kNN - {refname}: {pt:+.4f} [{lo:+.4f}, {hi:+.4f}]", flush=True)
        print("     beta curve (train_eval):", end=" ")
        for beta in (0.0, 0.5, 1.0, 1.64, 2.5):
            knn.bgrid = (beta,)
            eb = evaluate(ev, knn.select(ev, k_best, beta), bb)
            print(f"b={beta}: {eb['mase']:.4f}/IR{eb['ir']:.2f}/cHIR{eb['hir']:.2f}", end="  ")
        print(flush=True)
        # per-source paired difference sign check versus KEEP for the kNN operating point
        import collections
        from introact_ts.v44 import catalog as C
        ra = C.to_records(ev, method="x", backbone=bb, selected=se)
        rk = C.to_records(ev, method="x", backbone=bb, selected=keep)
        by_src = collections.defaultdict(list)
        for a, kk in zip(ra, rk):
            if a["mase"] is not None and kk["mase"] is not None:
                by_src[a["source"]].append(a["mase"] - kk["mase"])
        print("     per-source mean(kNN - KEEP):", {s: round(float(np.mean(v)), 4) for s, v in sorted(by_src.items())}, flush=True)


if __name__ == "__main__":
    main()
