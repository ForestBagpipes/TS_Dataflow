"""Fourth local prototype: why does removing the KEEP option help on Bolt?

Hypothesis: the bank mixes 10/30/50 % severities, the evaluation is at 10 %,
and standardised Euclidean retrieval lets a 10 % request borrow neighbours from
harsher severities whose utilities are more negative, which biases the local
mean downward and makes the act-or-keep threshold abstain on requests that
would have benefited.  Test: severity-sliced retrieval and relevance-weighted
features, each with and without the KEEP option, beta = 0, merged bank.
"""
from __future__ import annotations

import sys
import time

import numpy as np

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
from proto_v46_selector_variants import Variant, evaluate, load_all, paired_boot, project  # noqa: E402
from introact_ts.v44 import protocol as P  # noqa: E402


class SevVariant(Variant):
    """Same-severity retrieval (bank records within +-0.05 of the request severity)."""

    def __init__(self, name, **kw):
        super().__init__(name, **kw)

    def prepare(self, cats_fit):
        super().prepare(cats_fit)
        sev = {}
        for a in P.ACTIONS:
            vals = []
            for c in cats_fit:
                e = c.actions.get(a)
                if e is None or not e.scored or e.utility is None or e.state_vector is None:
                    continue
                vals.append(c.severity)
            sev[a] = np.array(vals)
        self.sev = sev
        return self

    def score(self, cat, a, k, beta):
        b = self.bank[a]
        keep_idx = np.abs(self.sev[a] - cat.severity) < 0.05
        saved = {key: b[key] for key in ("Zs", "t", "g", "horizon", "source")}
        for key in saved:
            b[key] = saved[key][keep_idx]
        try:
            return super().score(cat, a, k, beta)
        finally:
            for key in saved:
                b[key] = saved[key]


def main():
    t0 = time.time()
    data = load_all()
    print("loaded", round(time.time() - t0, 1), "s", flush=True)
    variants = [
        ("kNN", Variant("kNN")),
        ("kNN FWcorr", Variant("fw", fw="corr")),
        ("kNN SEV-slice", SevVariant("sev")),
        ("kNN SEV+FWcorr", SevVariant("sevfw", fw="corr")),
        ("kNN H-slice", Variant("h", slice_h=True)),
        ("kNN SEV+H-slice", SevVariant("sevh", slice_h=True)),
    ]
    for bb in ("bolt", "timesfm"):
        bank_cats = data[(bb, "replay_fit")] + data[(bb, "gate")]
        ev = data[(bb, "train_eval")]
        keep = {c.episode: "KEEP" for c in ev}
        print(f"== {bb}: merged bank, train_eval, beta=0 ==")
        for name, v in variants:
            v.prepare(bank_cats)
            for k in (16, 32):
                e_keep = evaluate(ev, v.select(ev, k, 0.0), bb)
                e_act = evaluate(ev, v.select(ev, k, 0.0, gate=False), bb)
                e_b1 = evaluate(ev, v.select(ev, k, 1.0), bb)
                print(f"  {name:16s} k={k:2d} | act-or-keep: {e_keep['mase']:.4f} IR={e_keep['ir']:.2f} cHIR={e_keep['hir']:.2f}"
                      f" | always-act: {e_act['mase']:.4f} cHIR={e_act['hir']:.2f}"
                      f" | beta=1: {e_b1['mase']:.4f} IR={e_b1['ir']:.2f} cHIR={e_b1['hir']:.2f}", flush=True)
        # CI for the most promising against KEEP and against always-act
        v = dict(variants)["kNN SEV+FWcorr"]
        v.prepare(bank_cats)
        se = v.select(ev, 32, 0.0)
        sa = v.select(ev, 32, 0.0, gate=False)
        pt, lo, hi = paired_boot(ev, se, keep, bb, n=600)
        pt2, lo2, hi2 = paired_boot(ev, se, sa, bb, n=600)
        print(f"  SEV+FWcorr k=32 act-or-keep minus KEEP: {pt:+.4f} [{lo:+.4f},{hi:+.4f}]; minus always-act: {pt2:+.4f} [{lo2:+.4f},{hi2:+.4f}]", flush=True)


if __name__ == "__main__":
    main()
