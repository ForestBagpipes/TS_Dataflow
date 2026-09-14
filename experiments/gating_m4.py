"""Does the decorrelated score earn a place in the acceptance path?

M4 showed that regressing a predictability proxy out of the behavioural risk
raises corpus AUROC from 0.468 to 0.551 and removes the systematic false alarm
on clean unpredictable windows, at the cost of three contamination types. That
was a measurement on the score. Whether it improves the system is a different
question and this answers it by substitution.

The criterion is fixed here, before the run:

    the residual score enters the acceptance path only if protected stratum
    edits fall AND repair does not degrade materially, taken as no worse than
    a 10 percent relative drop

Anything else and it stays a diagnostic module in the analysis section.

The regression coefficients are fitted on the calibration corpus, seed 123, and
applied to the reporting corpus, seed 42. Fitting them on the corpus being
scored would be transductive and would flatter the method.

Everything downstream of the substitution is unchanged: same proposals, same
operators, same thresholds, same probe. Only the scalar fed to
`build_risk_state` as `behav_risk` differs, which in turn moves the hypothesis
posterior and the risk term.

Usage:
    python -u experiments/gating_m4.py --device cuda --n 800
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from audit import _nmse  # noqa: E402
from corpus import CorpusSpec, OOD_KINDS, build_corpus  # noqa: E402
from decorrelate import PROXIES  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.probe import SIGNAL_NAMES  # noqa: E402
from introact_ts.risk import build_risk_state, corpus_reference  # noqa: E402
from introact_ts.verify import VerifyConfig  # noqa: E402

PROTECTED = ("clean", "hard", "rare_valid", "changepoint", "clean_ood")
REPAIR_TOLERANCE = 0.10


def proxy_matrix(windows):
    keys = list(PROXIES)
    X = np.array([[PROXIES[k](w.series) for k in keys] for w in windows], float)
    return X, keys


def fit_residual(behav, X):
    ok = np.isfinite(behav) & np.isfinite(X).all(axis=1)
    A = np.column_stack([np.ones(ok.sum()), X[ok]])
    coef, *_ = np.linalg.lstsq(A, behav[ok], rcond=None)
    return coef


def apply_residual(behav, X, coef):
    out = np.array(behav, float, copy=True)
    ok = np.isfinite(behav) & np.isfinite(X).all(axis=1)
    A = np.column_stack([np.ones(ok.sum()), X[ok]])
    out[ok] = behav[ok] - A @ coef
    return out


def rebuild_states(agent, windows, scores):
    """Risk states with a substituted behavioural score, no re probing."""
    ref = corpus_reference(agent._evidences, np.asarray(scores, float), agent._ood)
    return [
        build_risk_state(
            window_id=w.window_id, series=w.series, profile=agent._profiles[i],
            probe_result=agent._probes[i], z_row=agent._calib.z[i],
            behav_risk=float(scores[i]), ood=float(agent._ood[i]),
            reference=ref, signal_names=SIGNAL_NAMES,
            evidence=agent._evidences[i],
        )
        for i, w in enumerate(windows)
    ]


def score_traces(traces, windows, form):
    byid = {w.window_id: w for w in windows}
    dmg, before, after = [], [], []
    n_mod = prot = worsened = correct = total = 0
    per_form = Counter()
    ls_missed = ls_total = 0
    for t in traces:
        w = byid[t.window_id]
        if t.modified:
            n_mod += 1
            total += 1
            if w.stratum in PROTECTED:
                prot += 1
                if form.get(w.window_id):
                    per_form[form[w.window_id]] += 1
            elif w.stratum == "contaminated":
                correct += 1
        if w.contamination == "level_shift":
            ls_total += 1
            if not t.modified:
                ls_missed += 1
        ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))
        a = _nmse(t.final_series, w.clean_series[t.crop_offset:], ref_var)
        b = _nmse(w.series, w.clean_series, ref_var)
        if a > b + 1e-9:
            worsened += 1
        if w.stratum in PROTECTED:
            dmg.append(a)
        elif w.stratum == "contaminated":
            before.append(b)
            after.append(a)
    bm, am = float(np.mean(before)), float(np.mean(after))
    return {
        "mean_damage": float(np.mean(dmg)),
        "repair_reduction": (1.0 - am / bm) if bm > 1e-9 else 0.0,
        "n_modified": n_mod, "protected_edits": prot,
        "edit_precision": correct / max(total, 1),
        "windows_worsened": worsened,
        "protected_by_form": dict(per_form),
        "level_shift_missed": ls_missed, "level_shift_total": ls_total,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--tau", type=float, default=0.02)
    args = ap.parse_args()

    def spec(seed):
        n = args.n
        return CorpusSpec(
            n_contaminated=int(n * 0.35), n_clean=int(n * 0.20),
            n_hard=int(n * 0.1125), n_rare_valid=int(n * 0.1125),
            n_changepoint=int(n * 0.1125), n_clean_ood=int(n * 0.1125), seed=seed)

    models = make_pool(PRESETS["multi-family"]["curation"], device=args.device)
    cfg = VerifyConfig(tau=args.tau)

    cal_w = build_corpus(spec(123), source="ett")
    cal_agent = IntroActAgent(models, AgentConfig(verification=cfg))
    t0 = time.time()
    cal_agent.perceive(cal_w)
    Xc, keys = proxy_matrix(cal_w)
    coef = fit_residual(np.asarray(cal_agent._calib.risk, float), Xc)
    print(f"coefficients fitted on seed 123 in {time.time() - t0:.0f}s", flush=True)
    for k, cv in zip(["intercept"] + keys, coef):
        print(f"  {k:20s}{cv:+.4f}", flush=True)

    rep_w = build_corpus(spec(42), source="ett")
    oodw = [w for w in rep_w if w.stratum == "clean_ood"]
    form = {w.window_id: OOD_KINDS[i % len(OOD_KINDS)] for i, w in enumerate(oodw)}
    agent = IntroActAgent(models, AgentConfig(verification=cfg))
    t0 = time.time()
    base_states = agent.perceive(rep_w)
    print(f"reporting perceive {time.time() - t0:.0f}s", flush=True)

    Xr, _ = proxy_matrix(rep_w)
    resid = apply_residual(np.asarray(agent._calib.risk, float), Xr, coef)
    res_states = rebuild_states(agent, rep_w, resid)

    out = {}
    for label, states in [("behavioural", base_states), ("residual", res_states)]:
        t0 = time.time()
        traces = [agent.curate_window(w, s, peer_idx=i)
                  for i, (w, s) in enumerate(zip(rep_w, states))]
        out[label] = score_traces(traces, rep_w, form)
        r = out[label]
        print(f"{label:13s} damage {r['mean_damage']:.4f}  "
              f"repair {r['repair_reduction']:+.3f}  edits {r['n_modified']:4d}  "
              f"prot {r['protected_edits']:4d}  {time.time() - t0:.0f}s", flush=True)

    b, m = out["behavioural"], out["residual"]
    print()
    print(f"{'metric':26s}{'behavioural':>14s}{'residual':>12s}{'change':>12s}")
    for k, fmt in [("mean_damage", "{:.4f}"), ("repair_reduction", "{:+.3f}"),
                   ("n_modified", "{:d}"), ("protected_edits", "{:d}"),
                   ("edit_precision", "{:.3f}"), ("windows_worsened", "{:d}"),
                   ("level_shift_missed", "{:d}")]:
        bv, mv = b[k], m[k]
        ch = f"{mv - bv:+.4f}" if isinstance(bv, float) else f"{mv - bv:+d}"
        print(f"{k:26s}{fmt.format(bv):>14s}{fmt.format(mv):>12s}{ch:>12s}")
    print(f"{'level_shift_total':26s}{b['level_shift_total']:>14d}"
          f"{m['level_shift_total']:>12d}")

    print(f"\nprotected edits on clean_ood by form")
    print(f"{'form':16s}{'behavioural':>14s}{'residual':>12s}")
    for k in OOD_KINDS:
        print(f"{k:16s}{b['protected_by_form'].get(k, 0):>14d}"
              f"{m['protected_by_form'].get(k, 0):>12d}")

    prot_down = m["protected_edits"] < b["protected_edits"]
    rel_drop = (b["repair_reduction"] - m["repair_reduction"]) / max(
        abs(b["repair_reduction"]), 1e-9)
    repair_ok = rel_drop <= REPAIR_TOLERANCE
    verdict = ("integrate" if (prot_down and repair_ok)
               else "keep as diagnostic only")
    print(f"\ncriterion fixed before the run: protected edits must fall and "
          f"repair must not drop more than {REPAIR_TOLERANCE:.0%} relative")
    print(f"  protected edits fell: {prot_down} "
          f"({b['protected_edits']} to {m['protected_edits']})")
    print(f"  repair relative change: {-rel_drop:+.1%}, within tolerance: {repair_ok}")
    print(f"  VERDICT: {verdict}")

    out["verdict"] = verdict
    out["coefficients"] = dict(zip(["intercept"] + keys, coef.tolist()))
    (ROOT / "results" / "gating_m4.json").write_text(
        json.dumps(out, indent=1, default=float), encoding="utf-8")
    print("___GATING_M4_DONE___", flush=True)


if __name__ == "__main__":
    main()
