"""A declared rule set as the acceptance mechanism, the way a specification
based enforcement layer would do it.

The introduction argues that a safety predicate cannot be written for this
domain, because whether an edit harms a window is not a condition on the edit.
That has been an argument. This makes it a measurement.

The rules below are exactly what a domain expert can write down without
consulting any model and without any learned structural metric. Each is a
condition on the proposed edit alone.

  R1  the edit may change at most a fraction of the points
  R2  no single point may move by more than a multiple of the window's spread
  R3  the edit may only touch points that are already suspect, meaning missing
      or flagged by a plain robust outlier rule

These are the analogues of do not delete outside this directory and do not
exceed this speed. They are checkable, auditable and cheap, and a reviewer can
verify each by inspection.

Everything here is CPU only, because that is the point: a declared rule needs no
model, no probe and no calibration.

Threshold selection follows the pre registered rule, applied in the mechanism's
favour: the setting that maximises its discriminative power, with the discarded
settings printed. We do not perform an equivalent search for our own method, so
the comparison is tilted towards the rule set.

Usage:
    python -u experiments/spec_rules.py --seeds 42 1 2
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
from baselines import DEFECT_TO_ACTION  # noqa: E402
from corpus import CorpusSpec, build_corpus  # noqa: E402
from proposers_classic import (estimate_speed_bounds, imr_repair,  # noqa: E402
                               screen_repair)

from introact_ts.actions import apply_action, robust_scale  # noqa: E402
from introact_ts.risk import corpus_reference, statistical_evidence  # noqa: E402
from introact_ts.types import Action  # noqa: E402

#: The grid searched for the rule set, in its favour.
GRIDS = {
    "max_changed_fraction": [0.02, 0.05, 0.10, 0.20, 0.50],
    "max_point_move_scales": [0.5, 1.0, 2.0, 5.0],
    "require_suspect": [True, False],
}


def suspect_mask(x, k: float = 3.0):
    """Points a plain robust rule would call suspect, no model involved."""
    x = np.asarray(x, dtype=np.float64)
    miss = ~np.isfinite(x)
    finite = x[np.isfinite(x)]
    if len(finite) < 8:
        return miss
    med = float(np.median(finite))
    scale = max(robust_scale(x), 1e-9)
    out = miss.copy()
    out[np.isfinite(x)] = np.abs(finite - med) > k * scale
    return out


def rule_verdict(before, after, cfg):
    """Does the edit satisfy the declared rules. True means admitted."""
    b = np.asarray(before, dtype=np.float64)
    a = np.asarray(after, dtype=np.float64)
    if a.shape != b.shape:
        # A crop is a structural change no point wise rule can express, which is
        # itself part of the finding. Declared rules admit it by default since
        # they have nothing to say about it.
        return True
    changed = ~np.isclose(np.nan_to_num(a), np.nan_to_num(b), rtol=0, atol=1e-12)
    if changed.mean() > cfg["max_changed_fraction"]:
        return False
    scale = max(robust_scale(b), 1e-9)
    move = np.abs(np.nan_to_num(a) - np.nan_to_num(b))
    if changed.any() and move[changed].max() > cfg["max_point_move_scales"] * scale:
        return False
    if cfg["require_suspect"]:
        allowed = suspect_mask(b)
        if np.any(changed & ~allowed):
            return False
    return True


def candidates_for(windows, doms, props):
    """The same candidate edits every other mechanism is judged on."""
    out = {k: [] for k in ["stat_only", "always_clean", "screen", "imr"]}
    for w, d in zip(windows, doms):
        base = np.asarray(w.series, dtype=np.float64)
        if d != "none":
            o = apply_action(base, DEFECT_TO_ACTION[d])
            if o.applicable:
                out["stat_only"].append((w, base, o.series))
        cur = base
        for act, kw in [(Action.IMPUTE, {}), (Action.DESPIKE, {}),
                        (Action.DENOISE, {"strength": "medium"})]:
            o = apply_action(cur, act, **kw)
            if o.applicable and len(o.series) == len(cur):
                cur = o.series
        out["always_clean"].append((w, base, cur))
        for name in ["screen", "imr"]:
            c = props[name](w.series)
            if not np.allclose(np.nan_to_num(c), np.nan_to_num(base), atol=1e-12):
                out[name].append((w, base, c))
    return out


def evaluate(cands, cfg):
    """Apply the rules and score, with harm judged offline against the truth."""
    rows = []
    for name, items in cands.items():
        for w, before, after in items:
            ref = np.asarray(w.clean_series, dtype=np.float64)
            rv = float(np.var(ref - np.median(ref)))
            nb = _nmse(before, ref, rv)
            na = _nmse(after, ref[:len(after)] if len(after) != len(ref) else ref, rv)
            rows.append({"proposer": name, "stratum": w.stratum,
                         "vetoed": not rule_verdict(before, after, cfg),
                         "harmful": bool(na > nb + 1e-9)})
    return rows


def score_rows(rows):
    from scipy.stats import fisher_exact
    rs = [r for r in rows if r["stratum"] == "contaminated"]
    vh = sum(1 for r in rs if r["vetoed"] and r["harmful"])
    vn = sum(1 for r in rs if r["vetoed"] and not r["harmful"])
    ah = sum(1 for r in rs if not r["vetoed"] and r["harmful"])
    an = sum(1 for r in rs if not r["vetoed"] and not r["harmful"])
    odds, p = fisher_exact([[vh, vn], [ah, an]], alternative="greater")
    prot = [r for r in rows if r["stratum"] != "contaminated"]
    return {"n_contam": len(rs), "odds_ratio": float(odds), "p": float(p),
            "accept_harm": ah / max(ah + an, 1),
            "reject_harm": vh / max(vh + vn, 1),
            "baseline": (vh + ah) / max(len(rs), 1),
            "protected_recall": (sum(r["vetoed"] for r in prot) / max(len(prot), 1)),
            "overall_veto_rate": sum(r["vetoed"] for r in rows) / max(len(rows), 1),
            "table": [vh, vn, ah, an]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--seeds", type=int, nargs="+", default=[42, 1, 2])
    args = ap.parse_args()

    all_cands = {k: [] for k in ["stat_only", "always_clean", "screen", "imr"]}
    for seed in args.seeds:
        n = args.n
        spec = CorpusSpec(
            n_contaminated=int(n * 0.35), n_clean=int(n * 0.20),
            n_hard=int(n * 0.1125), n_rare_valid=int(n * 0.1125),
            n_changepoint=int(n * 0.1125), n_clean_ood=int(n * 0.1125), seed=seed)
        w = build_corpus(spec, source="ett")
        ev = [statistical_evidence(x.series) for x in w]
        ref = corpus_reference(ev, np.zeros(len(w)), np.zeros(len(w)))

        def dom(e):
            u = ref.units(e)
            above = [k for k in u if u[k] >= 1.0]
            return max(above, key=lambda k: u[k]) if above else "none"

        doms = [dom(e) for e in ev]
        smin, smax = estimate_speed_bounds([x.series for x in w])
        props = {"screen": lambda s: screen_repair(s, smin, smax, window=5),
                 "imr": lambda s: imr_repair(s, p=5, max_iter=40)}
        c = candidates_for(w, doms, props)
        for k in all_cands:
            all_cands[k].extend(c[k])
        print(f"[seed {seed}] candidates "
              f"{ {k: len(v) for k, v in c.items()} }", flush=True)

    print(f"\ngrid search for the rule set, in its favour, "
          f"selecting on contaminated odds ratio")
    print(f"{'frac':>6s}{'move':>6s}{'suspect':>9s}{'odds':>9s}{'p':>11s}"
          f"{'accept harm':>13s}{'veto rate':>11s}")
    best, best_cfg, table = None, None, []
    for f in GRIDS["max_changed_fraction"]:
        for m in GRIDS["max_point_move_scales"]:
            for s in GRIDS["require_suspect"]:
                cfg = {"max_changed_fraction": f, "max_point_move_scales": m,
                       "require_suspect": s}
                r = score_rows(evaluate(all_cands, cfg))
                table.append({"cfg": cfg, **{k: v for k, v in r.items()
                                             if k != "table"}})
                print(f"{f:6.2f}{m:6.1f}{str(s):>9s}{r['odds_ratio']:9.3f}"
                      f"{r['p']:11.2e}{r['accept_harm']:13.3f}"
                      f"{r['overall_veto_rate']:11.3f}", flush=True)
                if best is None or r["odds_ratio"] > best["odds_ratio"]:
                    best, best_cfg = r, cfg

    print(f"\nselected {best_cfg}")
    print(f"  contaminated odds ratio {best['odds_ratio']:.3f} p {best['p']:.2e}")
    print(f"  accepted harm {best['accept_harm']:.3f} against baseline "
          f"{best['baseline']:.3f}, rejected harm {best['reject_harm']:.3f}")
    print(f"  protected recall {best['protected_recall']:.3f} against overall "
          f"veto rate {best['overall_veto_rate']:.3f}")
    print(f"  contingency [veto_harm, veto_benign, accept_harm, accept_benign] "
          f"{best['table']}")

    print(f"\nper proposer at the selected setting")
    print(f"{'proposer':16s}{'n':>6s}{'odds':>9s}{'accept harm':>13s}{'baseline':>10s}")
    per = {}
    for name, items in all_cands.items():
        r = score_rows(evaluate({name: items}, best_cfg))
        per[name] = r
        print(f"{name:16s}{r['n_contam']:6d}{r['odds_ratio']:9.3f}"
              f"{r['accept_harm']:13.3f}{r['baseline']:10.3f}")

    (ROOT / "results" / "spec_rules.json").write_text(
        json.dumps({"grid": table, "selected": best_cfg, "best": best,
                    "per_proposer": per, "seeds": args.seeds},
                   indent=1, default=float), encoding="utf-8")
    print("___SPEC_RULES_DONE___", flush=True)


if __name__ == "__main__":
    main()
