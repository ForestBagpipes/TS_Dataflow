"""Calibrate the structural threshold with a finite sample guarantee.

The loss is fixed here before the experiment runs and is not revisited
afterwards. Changing it after seeing the curve would be tuning.

    L_i(lambda) = 1 if nmse_after > nmse_before + DELTA, else 0

DELTA is 1e-9. That is not a tuned quantity, it is floating point noise, so the
loss reads as "did this window come out measurably worse than it went in". It
has no free parameter to choose, which is why it is the primary criterion. For
protected windows nmse_before is 0, so any measurable departure counts; for
contaminated windows only a net worsening counts, so a partial repair is not
penalised. Every stratum carries a pristine reference, verified: all six have
clean_series set.

A sensitivity scan over larger DELTA is reported after the fact, to show what
the guarantee looks like when only substantive damage is counted. The primary
number is the one at 1e-9.

Monotonicity is checked, not assumed. If the empirical risk is not monotone in
the threshold, the nested family assumption behind the single parameter
calibration fails, and the run says so rather than proceeding as if it held.

Stage 1 writes the calibration curve and prints it, stage 2 adds the stability
table across contamination rates. Stage 1 output is usable on its own.

Usage:
    python -u experiments/run_conformal.py --device cuda
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from audit import _nmse  # noqa: E402
from corpus import CorpusSpec, build_corpus  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.conformal import (calibrate, check_monotone,  # noqa: E402
                                   fixed_sequence_select, risk_curve)
from introact_ts.verify import VerifyConfig  # noqa: E402

DELTA = 1e-9
TAU_GRID = [0.005, 0.01, 0.015, 0.02, 0.03, 0.04, 0.06, 0.08,
            0.10, 0.12, 0.16, 0.20, 0.25, 0.30]
ALPHAS = [0.001, 0.002, 0.005, 0.01, 0.015, 0.02, 0.03, 0.04, 0.05]
RATES = [5, 10, 20, 35, 50, 67]
#: Same pool split, pre registered in docs/conformal_threshold.md before this
#: code was written. The first design calibrated on one corpus and reported on
#: another, which breaks exchangeability: two independent samples of ETT windows
#: differ in difficulty, and the realised risk overshot the target by 20 to 50
#: percent as a result. Splitting one pool at random makes the assumption hold
#: by construction.
POOL_SEED = 42
SPLIT_SEED = 7
POOL_N = 1600


def spec_for(rate_pct: int, seed: int, n: int = 800) -> CorpusSpec:
    n_contam = int(round(n * rate_pct / 100.0))
    rest = n - n_contam
    per = rest // 5
    return CorpusSpec(
        n_contaminated=n_contam, n_clean=rest - 4 * per, n_hard=per,
        n_rare_valid=per, n_changepoint=per, n_clean_ood=per, seed=seed,
    )


def split_pool(n, seed=SPLIT_SEED):
    """One random split of the pool into calibration and reporting halves."""
    rng = np.random.RandomState(seed)
    order = rng.permutation(n)
    cut = n // 2
    return order[:cut], order[cut:]


def losses_over_grid(windows, models, seed, label, deltas=(DELTA,)):
    """Per window 0/1 loss at every threshold, one curate pass each."""
    agent = IntroActAgent(models, AgentConfig())
    t0 = time.time()
    states = agent.perceive(windows)
    print(f"  [{label}] perceive {time.time() - t0:.0f}s on {len(windows)}",
          flush=True)

    byid = {w.window_id: w for w in windows}
    out = {d: {} for d in deltas}
    for tau in TAU_GRID:
        agent.cfg.verification.tau = tau
        t0 = time.time()
        before, after = [], []
        for i, (w, s) in enumerate(zip(windows, states)):
            t = agent.curate_window(w, s, peer_idx=i)
            ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))
            before.append(_nmse(w.series, w.clean_series, ref_var))
            after.append(_nmse(t.final_series,
                               w.clean_series[t.crop_offset:], ref_var))
        b, a = np.asarray(before), np.asarray(after)
        for d in deltas:
            out[d][tau] = (a > b + d).astype(np.float64)
        print(f"  [{label}] tau {tau:.3f}  risk {float(out[DELTA][tau].mean()):.4f}"
              f"  {time.time() - t0:.0f}s", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--stage2", action="store_true",
                    help="also run the contamination rate stability table")
    args = ap.parse_args()

    models = make_pool(PRESETS["multi-family"]["curation"], device=args.device)
    deltas = (DELTA, 1e-4, 1e-2, 5e-2)

    print(f"loss: nmse_after > nmse_before + {DELTA:g}, bounded in [0,1]",
          flush=True)
    print(f"same pool split, seed {SPLIT_SEED}, exchangeable by construction\n",
          flush=True)

    pool = build_corpus(spec_for(35, POOL_SEED, POOL_N), source="ett")
    cal_idx, rep_idx = split_pool(len(pool))
    print(f"pool {len(pool)} windows, split seed {SPLIT_SEED}: "
          f"{len(cal_idx)} calibration, {len(rep_idx)} reporting", flush=True)
    # One perception pass and one curate pass per threshold over the whole
    # pool, then the halves are read off. Curating each half separately would
    # change the peer calibration each window sees and make the two halves
    # incomparable for a reason unrelated to the split.
    allo = losses_over_grid(pool, models, POOL_SEED, "pool", deltas)
    cal = {d: {t: v[cal_idx] for t, v in allo[d].items()} for d in deltas}
    rep = {d: {t: v[rep_idx] for t, v in allo[d].items()} for d in deltas}

    # Persist the raw per window losses. Every selection rule, any alpha and
    # any future correction can then be evaluated without touching the GPU
    # again, which is the expensive half of this experiment.
    np.savez_compressed(
        ROOT / "results" / "conformal_losses.npz",
        cal_idx=cal_idx, rep_idx=rep_idx,
        **{f"d{di}_t{t}": allo[d][t]
           for di, d in enumerate(deltas) for t in TAU_GRID},
        deltas=np.array(deltas), tau_grid=np.array(TAU_GRID))
    print(f"  raw losses saved to results/conformal_losses.npz", flush=True)

    grid, cal_curve = risk_curve(cal[DELTA])
    _, rep_curve = risk_curve(rep[DELTA])
    mono_cal = check_monotone(cal_curve)
    mono_rep = check_monotone(rep_curve)

    print(f"\nempirical risk against threshold")
    print(f"{'tau':>8s}{'calibration':>14s}{'reporting':>12s}")
    for g, c, r in zip(grid, cal_curve, rep_curve):
        print(f"{g:8.3f}{c:14.4f}{r:12.4f}")
    print(f"\nmonotone in tau: calibration {mono_cal}, reporting {mono_rep}")
    if not (mono_cal and mono_rep):
        print("  WARNING the nested family assumption fails, a single parameter")
        print("  calibration without correction is not licensed here")

    print(f"\ncalibration curve, target against realised on held out data")
    print(f"{'alpha':>8s}{'lambda*':>10s}{'cal risk':>10s}{'corrected':>11s}"
          f"{'realised':>10s}{'holds':>7s}{'edits':>8s}")
    # If the risk curve is not monotone the nested family assumption behind
    # the single parameter calibration fails, so the run falls back to fixed
    # sequence testing rather than reporting a number the derivation does not
    # license. The fallback is chosen by the data, not by preference.
    use_ltt = not mono_cal
    if use_ltt:
        print("  falling back to fixed sequence testing with Bentkus p values",
              flush=True)

    rows = []
    violations = 0
    for a in ALPHAS:
        if use_ltt:
            sel = fixed_sequence_select(cal[DELTA], a)
            lam = sel["lambda_star"]
            emp = float(cal[DELTA][lam].mean())
            corrected = float("nan")
            ct = type("T", (), {"lambda_star": lam, "empirical_risk": emp,
                                "corrected_risk": corrected})()
        else:
            ct = calibrate(cal[DELTA], a)
        realised = float(rep[DELTA][ct.lambda_star].mean())
        holds = realised <= a
        violations += 0 if holds else 1
        rows.append({"alpha": a, "lambda_star": ct.lambda_star,
                     "cal_risk": ct.empirical_risk,
                     "corrected": ct.corrected_risk,
                     "realised": realised, "holds": bool(holds)})
        print(f"{a:8.3f}{ct.lambda_star:10.3f}{ct.empirical_risk:10.4f}"
              f"{ct.corrected_risk:11.4f}{realised:10.4f}{str(holds):>7s}"
              f"{'':>8s}")

    print(f"\nviolations {violations} of {len(ALPHAS)}")
    if violations:
        worst = max((r["realised"] - r["alpha"]) for r in rows if not r["holds"])
        print(f"  worst overshoot {worst:+.4f} in absolute risk")

    print(f"\nthe hand set values, for comparison, realised risk on reporting data")
    for t in (0.02, 0.12, 0.20):
        if t in rep[DELTA]:
            print(f"  tau {t:.2f}  realised risk {float(rep[DELTA][t].mean()):.4f}"
                  f"  no guarantee attached")

    print(f"\nsensitivity to the loss threshold, alpha 0.02")
    print(f"{'delta':>10s}{'lambda*':>10s}{'realised':>10s}{'holds':>7s}")
    sens = []
    for d in deltas:
        ct = calibrate(cal[d], 0.02)
        realised = float(rep[d][ct.lambda_star].mean())
        sens.append({"delta": d, "lambda_star": ct.lambda_star,
                     "realised": realised, "holds": bool(realised <= 0.02)})
        print(f"{d:10.0e}{ct.lambda_star:10.3f}{realised:10.4f}"
              f"{str(realised <= 0.02):>7s}")

    payload = {
        "selection_method": ("fixed_sequence_testing" if use_ltt
                             else "conformal_risk_control"),
        "delta": DELTA, "tau_grid": TAU_GRID, "alphas": ALPHAS,
        "pool_seed": POOL_SEED, "split_seed": SPLIT_SEED, "pool_n": POOL_N,
        "risk_curve_calibration": dict(zip(map(str, grid), cal_curve)),
        "risk_curve_reporting": dict(zip(map(str, grid), rep_curve)),
        "monotone": {"calibration": mono_cal, "reporting": mono_rep},
        "calibration_table": rows, "violations": violations,
        "sensitivity": sens,
    }
    (ROOT / "results" / "conformal.json").write_text(
        json.dumps(payload, indent=1, default=float), encoding="utf-8")
    print("\n___CONFORMAL_STAGE1_DONE___", flush=True)

    if not args.stage2:
        return

    print(f"\nstability across contamination rates, alpha fixed at 0.02")
    if use_ltt:
        ct = type("T", (), {"lambda_star":
                            fixed_sequence_select(cal[DELTA], 0.02)["lambda_star"]})()
    else:
        ct = calibrate(cal[DELTA], 0.02)
    print(f"lambda* {ct.lambda_star:.3f} selected once on the calibration half")
    print(f"{'rate':>6s}{'realised':>11s}{'holds':>7s}")
    stab = []
    for rate in RATES:
        # Same pool split per rate, so the stability table uses the same
        # protocol as the calibration curve rather than the cross corpus one.
        w = build_corpus(spec_for(rate, POOL_SEED, args.n), source="ett")
        losses = losses_over_grid(w, models, POOL_SEED, f"rate{rate}")
        _, ridx = split_pool(len(w))
        realised = float(losses[DELTA][ct.lambda_star][ridx].mean())
        stab.append({"rate": rate, "realised": realised,
                     "holds": bool(realised <= 0.02)})
        print(f"{rate:6d}{realised:11.4f}{str(realised <= 0.02):>7s}", flush=True)
        payload["stability"] = stab
        (ROOT / "results" / "conformal.json").write_text(
            json.dumps(payload, indent=1, default=float), encoding="utf-8")
    print("___CONFORMAL_STAGE2_DONE___", flush=True)


if __name__ == "__main__":
    main()
