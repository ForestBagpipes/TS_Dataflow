"""Local CPU prototype: selector variants on the frozen v4.4 replay artefacts.

Reads only results/server_snapshot_20260917 (replay_fit / gate / train_eval on
bolt / timesfm).  No TEST data exists here.  Purpose: rank candidate
micro-changes to the selector before the v46 run, using the same catalog
prediction cache the paper's ablations read.  Nothing here touches the backbone.

Run from the repository root:  python scripts/proto_v46_selector_variants.py
"""
from __future__ import annotations

import collections
import sys
import time

import numpy as np

sys.path.insert(0, "src")
from introact_ts.v44 import catalog as C  # noqa: E402
from introact_ts.v44 import metrics as ME  # noqa: E402
from introact_ts.v44 import protocol as P  # noqa: E402
from introact_ts.v44.matching import STATE_SLICES  # noqa: E402

ROOT = "results/server_snapshot_20260917/unpacked"
ACTIONS = P.ACTIONS
NONREF = ACTIONS[1:]
RNG = np.random.default_rng(101)
ALL_BLOCKS = ("mask", "context", "intervention", "forecast")


def load_all():
    data = {}
    for bb in ("bolt", "timesfm"):
        for block in ("replay_fit", "gate", "train_eval"):
            data[(bb, block)] = C.load_catalog(ROOT, block, bb)
    return data


def project(vec, blocks):
    return np.concatenate([vec[STATE_SLICES[b]] for b in blocks])


def bank_arrays(cats, blocks):
    out = {}
    all_z = []
    for a in ACTIONS:
        Z, g, l0, par, src, hz = [], [], [], [], [], []
        for c in cats:
            e = c.actions.get(a)
            if e is None or not e.scored or e.utility is None or e.state_vector is None:
                continue
            Z.append(project(e.state_vector, blocks))
            g.append(e.utility)
            l0.append(c.reference_mase)
            par.append(c.parent)
            src.append(c.source)
            hz.append(c.horizon)
        out[a] = dict(Z=np.array(Z), g=np.array(g), l0=np.array(l0), parent=np.array(par),
                      source=np.array(src), horizon=np.array(hz))
        all_z.append(out[a]["Z"])
    all_z = np.vstack(all_z)
    mean = all_z.mean(0)
    std = all_z.std(0)
    std = np.where(std > 1e-12, std, 1.0)
    for a in ACTIONS:
        out[a]["Zs"] = (out[a]["Z"] - mean) / std
    return out, (mean, std)


def ridge_fit(X, y, alpha=1.0):
    Xb = np.hstack([X, np.ones((len(X), 1))])
    A = Xb.T @ Xb + alpha * np.eye(Xb.shape[1])
    A[-1, -1] -= alpha
    return np.linalg.solve(A, Xb.T @ y)


def ridge_pred(w, X):
    return np.hstack([X, np.ones((len(X), 1))]) @ w


class Variant:
    def __init__(self, name, *, blocks=ALL_BLOCKS, slice_h=False, slice_s=False,
                 target="abs", winsor=None, fw=None, hybrid=False, sign_gate=None,
                 local=True, kgrid=(8, 16, 32), bgrid=(0.0, 1.0, 1.64)):
        self.name = name
        self.blocks = blocks
        self.slice_h = slice_h
        self.slice_s = slice_s
        self.target = target
        self.winsor = winsor
        self.fw = fw
        self.hybrid = hybrid
        self.sign_gate = sign_gate
        self.local = local
        self.kgrid = kgrid
        self.bgrid = bgrid

    def prepare(self, cats_fit):
        bank, (mean, std) = bank_arrays(cats_fit, self.blocks)
        self.mean, self.std = mean, std
        self.bank = bank
        for a in NONREF:
            b = bank[a]
            t = b["g"].copy()
            if self.target == "rel":
                t = t / np.maximum(b["l0"], 1e-6)
            if self.winsor is not None:
                lo, hi = np.quantile(t, [self.winsor, 1 - self.winsor])
                t = np.clip(t, lo, hi)
            b["t"] = t
            w = np.ones(b["Zs"].shape[1])
            if self.fw == "corr":
                for j in range(len(w)):
                    x = b["Zs"][:, j]
                    w[j] = abs(np.corrcoef(x, t)[0, 1]) if x.std() > 1e-12 else 0.0
                w = w / max(w.mean(), 1e-12)
            elif self.fw == "ridge":
                coef = ridge_fit(b["Zs"], (t - t.mean()) / max(t.std(), 1e-12))[:-1]
                w = np.abs(coef)
                w = w / max(w.mean(), 1e-12)
            b["w"] = w
            if self.hybrid:
                b["ridge"] = ridge_fit(b["Zs"], t)
                b["resid"] = t - ridge_pred(b["ridge"], b["Zs"])
        return self

    def score(self, cat, a, k, beta):
        b = self.bank[a]
        z = (project(cat.actions[a].state_vector, self.blocks) - self.mean) / self.std
        idx = np.ones(len(b["g"]), bool)
        if self.slice_h:
            idx &= b["horizon"] == cat.horizon
        if self.slice_s:
            idx &= b["source"] == cat.source
        if idx.sum() == 0:
            return -np.inf, 0.0
        Zs = b["Zs"][idx]
        t = b["t"][idx]
        base = 0.0
        if self.hybrid:
            base = float(ridge_pred(b["ridge"], z[None])[0])
            t = b["resid"][idx]
        if not self.local:
            mu = float(t.mean())
            sig = float(t.std())
            neff = float(len(t))
            pos = float(((t + base) > 0).mean())
        else:
            d = np.sqrt(((Zs - z) ** 2 * b["w"]).sum(1))
            ke = min(k, len(d))
            order = np.argsort(d, kind="stable")[:ke]
            dd = d[order]
            tt = t[order]
            tau = np.median(dd) + 1e-12
            wts = np.exp(-dd / tau)
            if not np.isfinite(wts.sum()) or wts.sum() <= 0:
                wts = np.ones_like(dd)
            mu = float(wts @ tt / wts.sum())
            sig = float(np.sqrt(wts @ (tt - mu) ** 2 / wts.sum()))
            neff = float(np.clip(wts.sum() ** 2 / (wts @ wts), 1.0, ke))
            pos = float(wts @ ((tt + base) > 0) / wts.sum())
        mu += base
        S = mu - beta * sig / np.sqrt(max(neff, 1.0))
        if self.sign_gate is not None and pos < self.sign_gate:
            S = -np.inf
        return S, mu

    def select(self, cats, k, beta, gate=True):
        sel = {}
        for c in cats:
            legal = c.legal()
            best, best_s = P.REFERENCE_ACTION, (0.0 if gate else -np.inf)
            for a in NONREF:
                if a not in legal or c.actions[a].state_vector is None:
                    continue
                S, _ = self.score(c, a, k, beta)
                if S > best_s:
                    best, best_s = a, S
            sel[c.episode] = best
        return sel


def evaluate(cats, sel, backbone, name="M"):
    recs = C.to_records(cats, method=name, backbone=backbone, selected=sel)
    mase = ME.macro_headline(recs, "mase")
    n = len(cats)
    ir = harm = benef = 0
    hl = 0.0
    for c in cats:
        a = sel[c.episode]
        if a == P.REFERENCE_ACTION:
            continue
        ir += 1
        u = c.actions[a].utility or 0.0
        if u < 0:
            harm += 1
            hl += -u
        if u > 0:
            benef += 1
    return dict(mase=mase, ir=ir / n, hir=(harm / ir if ir else 0.0), hl=hl / n,
                bp=(benef / ir if ir else float("nan")))


def paired_boot(cats, sel_a, sel_b, backbone, n=1000):
    rec_a = C.to_records(cats, method="A", backbone=backbone, selected=sel_a)
    rec_b = C.to_records(cats, method="A", backbone=backbone, selected=sel_b)
    by_parent = collections.defaultdict(list)
    for ra, rb in zip(rec_a, rec_b):
        d = dict(ra)
        ok = ra["mase"] is not None and rb["mase"] is not None
        d["mase"] = (ra["mase"] - rb["mase"]) if ok else None
        by_parent[(ra["source"], ra["parent"])].append(d)
    src_par = collections.defaultdict(list)
    for (s, p) in by_parent:
        src_par[s].append((s, p))
    point = ME.macro_headline([r for v in by_parent.values() for r in v], "mase")
    vals = []
    for _ in range(n):
        rows = []
        for s, ps in src_par.items():
            pick = RNG.choice(len(ps), len(ps), replace=True)
            for j, i in enumerate(pick):
                for r in by_parent[ps[i]]:
                    d = dict(r)
                    d["parent"] = f"{r['parent']}#{j}"
                    rows.append(d)
        vals.append(ME.macro_headline(rows, "mase"))
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return point, lo, hi


def main():
    t0 = time.time()
    data = load_all()
    print("loaded", round(time.time() - t0, 1), "s", flush=True)
    variants = [
        Variant("BASE(v44 Full)"),
        Variant("A1 global", local=False),
        Variant("H-slice (paper: per horizon)", slice_h=True),
        Variant("S+H-slice (paper: source+horizon)", slice_h=True, slice_s=True),
        Variant("REL target", target="rel"),
        Variant("WIN 1%", winsor=0.01),
        Variant("REL+WIN", target="rel", winsor=0.01),
        Variant("FW corr", fw="corr"),
        Variant("FW ridge", fw="ridge"),
        Variant("REL+FW ridge", target="rel", fw="ridge"),
        Variant("HYB ridge+kNN", hybrid=True),
        Variant("REL+HYB", target="rel", hybrid=True),
        Variant("REL+FW+HYB", target="rel", fw="ridge", hybrid=True),
        Variant("REL+FW+HYB k64", target="rel", fw="ridge", hybrid=True, kgrid=(8, 16, 32, 64)),
        Variant("REL+FW+HYB+sign.5", target="rel", fw="ridge", hybrid=True, sign_gate=0.5,
                kgrid=(8, 16, 32, 64)),
        Variant("REL+FW+sign.5 k64", target="rel", fw="ridge", sign_gate=0.5, kgrid=(8, 16, 32, 64)),
        Variant("REL+HYB+H-slice", target="rel", hybrid=True, slice_h=True),
    ]
    harm_cap = 0.25
    results = {}
    for v in variants:
        row = {}
        for bb in ("bolt", "timesfm"):
            fit, gate, ev = data[(bb, "replay_fit")], data[(bb, "gate")], data[(bb, "train_eval")]
            v.prepare(fit)
            grid = []
            for k in v.kgrid:
                for beta in v.bgrid:
                    sg = v.select(gate, k, beta)
                    grid.append((k, beta, evaluate(gate, sg, bb)))
            ok = [x for x in grid if x[2]["hir"] <= harm_cap] or [max(grid, key=lambda x: x[1])]
            k, beta, g = min(ok, key=lambda x: x[2]["mase"])
            se = v.select(ev, k, beta)
            e = evaluate(ev, se, bb)
            ceil = min(evaluate(ev, v.select(ev, kk, bt), bb)["mase"]
                       for kk in v.kgrid for bt in v.bgrid)
            row[bb] = dict(k=k, beta=beta, gate=g, eval=e, ceil=ceil, sel=se)
        results[v.name] = row
        b, t = row["bolt"], row["timesfm"]
        print(f"{v.name:36s} | bolt k={b['k']:2d} b={b['beta']:.2f} gate={b['gate']['mase']:.4f} "
              f"eval={b['eval']['mase']:.4f} IR={b['eval']['ir']:.2f} HIR={b['eval']['hir']:.2f} "
              f"ceil={b['ceil']:.4f} | tf k={t['k']:2d} b={t['beta']:.2f} gate={t['gate']['mase']:.4f} "
              f"eval={t['eval']['mase']:.4f} IR={t['eval']['ir']:.2f} HIR={t['eval']['hir']:.2f} "
              f"ceil={t['ceil']:.4f}", flush=True)

    for bb in ("bolt", "timesfm"):
        ev = data[(bb, "train_eval")]
        gate = data[(bb, "gate")]
        keep = {c.episode: "KEEP" for c in ev}
        orc = {c.episode: (c.oracle()[0] or "KEEP") for c in ev}
        print(bb, "KEEP", round(evaluate(ev, keep, bb)["mase"], 6),
              "ORACLE", round(evaluate(ev, orc, bb)["mase"], 6))

        def mean_util(a):
            vals = [c.actions[a].utility for c in gate
                    if c.actions.get(a) and c.actions[a].utility is not None]
            return float(np.mean(vals)) if vals else 0.0

        bf = max(ACTIONS, key=mean_util)
        bfsel = {c.episode: (bf if bf in c.legal() else "KEEP") for c in ev}
        print(bb, "BEST_FIXED", bf, evaluate(ev, bfsel, bb))
        for name in ["BASE(v44 Full)", "REL+HYB", "REL+FW+HYB", "REL+FW+HYB+sign.5"]:
            se = results[name][bb]["sel"]
            for refname, ref in (("KEEP", keep), ("BEST_FIXED", bfsel)):
                pt, lo, hi = paired_boot(ev, se, ref, bb, n=1000)
                print(f"  {bb} {name} - {refname}: {pt:+.4f} [{lo:+.4f}, {hi:+.4f}]", flush=True)

    for bb in ("bolt", "timesfm"):
        ev = data[(bb, "train_eval")]
        cnt = collections.Counter(c.oracle()[0] for c in ev)
        pos = {a: np.mean([c.actions[a].utility > 0 for c in ev
                           if c.actions[a].utility is not None]) for a in NONREF}
        neg = {a: np.mean([c.actions[a].utility < 0 for c in ev
                           if c.actions[a].utility is not None]) for a in NONREF}
        print(bb, "oracle-best share", {a: round(cnt[a] / len(ev), 3) for a in ACTIONS},
              "P(g>0)", {a: round(v, 2) for a, v in pos.items()},
              "P(g<0)", {a: round(v, 2) for a, v in neg.items()})


if __name__ == "__main__":
    main()
