"""Calibrate one structural threshold per operator family, on the paper's corpus.

A single global tau was calibrated on the families that rewrite a handful of
points and then applied to families that do something else entirely. Measured on
xl: RESEGMENT's distortion was identically zero on all 2766 attempts so the
condition never refused it once, and DENOISE's median distortion was 0.2085
against a threshold of 0.02 so the condition never accepted it once. One family
always passes and one never does, and both are the same fault: a threshold
calibrated on one family of transformations does not govern another.

**Candidate level rather than window level.** The old calibration ran the whole
loop at each threshold and asked whether the window ended up worse. That cannot
be split by family, because one window's episode involves candidates from
several. Here each candidate is executed once in the sandbox on the pristine
window and scored on its own, which decouples the families and matches what the
shield actually adjudicates, since the shield rules on candidates rather than on
windows.

The risk for family f at threshold lambda is

    R_f(lambda) = (1 / n_f) * sum_i  loss_i * 1[distortion_i < lambda]

with loss the corrected damage, `max(worse, discard_share)`, in [0, 1]. A
candidate the threshold refuses contributes nothing, so R_f is non decreasing in
lambda and conformal risk control's finite sample correction applies unchanged.

**Two things this changes about what theorem 5 says**, both to be written into
the statement rather than left implicit. It controls the expected damage of the
candidates a family's threshold admits, not the damage of a finished window; and
where a window commits more than one edit the candidate level bound is the
conservative side. Deployment also applies the utility and risk conditions on
top, so the admitted set at run time is a subset of what this calibrates over,
which is conservative in the same direction.

Crash safety: every window's candidates are appended to a JSONL as they finish,
so an interrupted run resumes from the last complete line rather than from the
start. That matters here because the pass is 1599 windows times 4 operators
times 3 rungs.

Usage:
    python -u experiments/run_conformal_family.py --n 1600 --seed 101 \
        --device cuda
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from audit import _nmse  # noqa: E402
from build_calibration import build as build_calibration  # noqa: E402

from introact_ts.actions import apply_action  # noqa: E402
from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.calibration import RISK_WEIGHTS, recalibrate_one  # noqa: E402
from introact_ts.conformal import LOSS_BOUND, check_monotone  # noqa: E402
from introact_ts.policy import PolicyConfig, propose_actions  # noqa: E402
from introact_ts.probe import (SIGNAL_NAMES, ProbeConfig,  # noqa: E402
                               probe_window, reference_scale)
from introact_ts.structure import (_discard_distortion,  # noqa: E402
                                   structure_distortion)
from introact_ts.types import Action  # noqa: E402

#: Operators the ladder covers, which are the ones this calibrates.
LADDER_ACTIONS = (Action.IMPUTE, Action.DESPIKE, Action.DENOISE,
                  Action.RESEGMENT)

RUNGS = ("aggressive", "default", "conservative")


def _rung_of(action, params):
    """Which rung a parameter dict came from, for reporting only."""
    from introact_ts.policy import LADDER, _key
    table = LADDER.get(action, {})
    for name, p in table.items():
        if _key(p) == _key(params):
            return name
    return "other"

#: Thresholds to evaluate. Wider than the old grid at the top because two
#: families live an order of magnitude above where the global value sat.
LAMBDA_GRID = [0.0, 0.005, 0.01, 0.015, 0.02, 0.03, 0.04, 0.06, 0.08, 0.10,
               0.12, 0.16, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80,
               0.90, 0.95, 1.0]

ALPHA = 0.03

#: Below this many candidates a family's own calibration is not trustworthy and
#: the run says so rather than silently falling back to a global value.
MIN_FAMILY_N = 100


def measure(window, state, agent, models, peer_idx, action, params):
    """One candidate in the sandbox: the shield's input and the damage it does."""
    work = np.asarray(window.series, dtype=np.float64)
    outcome = apply_action(work, action, **params)
    if not outcome.applicable:
        return None
    scale = reference_scale(window.series)
    after = probe_window(outcome.series, models, scale, ProbeConfig())
    report = structure_distortion(work, outcome.series, action, outcome.params,
                                  touched=outcome.touched)
    c = np.asarray(window.clean_series, dtype=np.float64)
    ref_var = float(np.var(c - np.median(c)))
    crop = int(outcome.params.get("lo", 0)) if action is Action.RESEGMENT else 0
    hi = crop + len(outcome.series)
    b = _nmse(work, c, ref_var)
    a = _nmse(outcome.series, c[crop:], ref_var)
    disc = _discard_distortion(work, {"lo": crop, "hi": hi})
    worse = 1.0 if a > b + 1e-9 else 0.0
    return {
        "family": action.value,
        "distortion": float(report.distortion),
        "delta_utility": float(after.utility - state.utility),
        "loss": float(max(worse, disc)),
        "worse": float(worse), "discard": float(disc),
        "stratum": window.stratum,
        "contamination": window.contamination,
    }


def calibrate_family(rows, grid, alpha):
    """Largest threshold whose corrected risk over this family clears alpha."""
    n = len(rows)
    d = np.asarray([r["distortion"] for r in rows], dtype=np.float64)
    L = np.asarray([r["loss"] for r in rows], dtype=np.float64)
    curve = []
    for g in grid:
        admitted = d < g
        curve.append(float((L * admitted).sum() / max(n, 1)))
    corrected = [(n * r + LOSS_BOUND) / (n + 1) for r in curve]
    ok = [(g, r, c) for g, r, c in zip(grid, curve, corrected) if c <= alpha]
    if ok:
        g_star, r_star, c_star = ok[-1]
    else:
        g_star, r_star, c_star = grid[0], curve[0], corrected[0]
    return {
        "n": n, "lambda_star": float(g_star),
        "risk_at_lambda": float(r_star), "corrected_risk": float(c_star),
        "grid": list(grid), "risk_curve": curve,
        "monotone": check_monotone(tuple(curve)),
        "admitted_at_lambda": int((d < g_star).sum()),
        "distortion_quantiles": {f"q{p:02d}": float(np.percentile(d, p))
                                 for p in (5, 25, 50, 75, 95)},
        "lambda_percentile": float((d < g_star).mean() * 100.0),
        "loss_share_from_discard": float(
            np.sum([r["discard"] for r in rows if r["discard"] > r["worse"]])
            / max(L.sum(), 1e-12)),
        "mean_loss": float(L.mean()),
        "sufficient": bool(n >= MIN_FAMILY_N),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1600)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=32)
    ap.add_argument("--alpha", type=float, default=ALPHA)
    ap.add_argument("--scores", default=str(ROOT / "results" / "family_scores.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "results" / "conformal_family.json"))
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    scores_path = Path(args.scores)
    if args.fresh:
        scores_path.unlink(missing_ok=True)

    done = set()
    if scores_path.exists():
        for line in scores_path.open(encoding="utf-8"):
            try:
                done.add(int(json.loads(line)["window_id"]))
            except Exception:
                pass
        print(f"resuming, {len(done)} windows already scored", flush=True)

    windows, dropped = build_calibration(n=args.n, seed=args.seed,
                                         source=args.source, verbose=True)
    todo = [w for w in windows if int(w.window_id) not in done]
    print(f"{len(windows)} calibration windows, {len(todo)} left to score",
          flush=True)

    if todo:
        models = make_pool(PRESETS[args.preset]["curation"], device=args.device)
        # The proposer decides which operators a window is offered, exactly as
        # it will at deployment, and the ladder gives each of them its three
        # rungs. Calibrating over every operator on every window instead was
        # the first version of this script and it measured the wrong quantity:
        # DESPIKE applied to a window with no spike is pure damage, so the
        # family's risk was 0.43 at any threshold above zero and its calibrated
        # threshold came out at zero, admitting nothing. Same lesson as tree
        # nine, one level down: the calibration distribution has to be the
        # deployment distribution, for candidates as well as for corpora.
        pcfg = PolicyConfig(enable_param_ladder=True)
        agent = IntroActAgent(models, AgentConfig(policy=pcfg,
                                                  n_jobs=args.n_jobs))
        t0 = time.time()
        states = agent.perceive(windows)
        print(f"perception {time.time() - t0:.0f}s", flush=True)
        index = {int(w.window_id): i for i, w in enumerate(windows)}

        scores_path.parent.mkdir(parents=True, exist_ok=True)
        with scores_path.open("a", encoding="utf-8") as fh:
            for k, w in enumerate(todo):
                i = index[int(w.window_id)]
                rows = []
                for action, params in propose_actions(states[i], [], pcfg):
                    if action not in LADDER_ACTIONS:
                        continue
                    r = measure(w, states[i], agent, models, i, action, params)
                    if r is not None:
                        r["rung"] = _rung_of(action, params)
                        rows.append(r)
                fh.write(json.dumps({"window_id": int(w.window_id),
                                     "candidates": rows}, default=float) + chr(10))
                fh.flush()
                if (k + 1) % 50 == 0:
                    print(f"  {k + 1}/{len(todo)} windows, "
                          f"{time.time() - t0:.0f}s", flush=True)

    by_family = defaultdict(list)
    for line in scores_path.open(encoding="utf-8"):
        for r in json.loads(line)["candidates"]:
            by_family[r["family"]].append(r)
    print()
    print(f"{sum(len(v) for v in by_family.values())} candidates scored")

    out = {}
    print()
    print(f"{'family':12s}{'n_f':>7s}{'lambda*':>10s}{'pctile':>9s}"
          f"{'risk':>9s}{'corrected':>11s}{'admitted':>10s}{'discard share':>15s}"
          f"{'monotone':>10s}")
    for fam in sorted(by_family):
        rows = by_family[fam]
        rec = calibrate_family(rows, LAMBDA_GRID, args.alpha)
        out[fam] = rec
        flag = "" if rec["sufficient"] else "   <-- below MIN_FAMILY_N"
        print(f"{fam:12s}{rec['n']:7d}{rec['lambda_star']:10.4f}"
              f"{rec['lambda_percentile']:9.1f}{rec['risk_at_lambda']:9.4f}"
              f"{rec['corrected_risk']:11.4f}{rec['admitted_at_lambda']:10d}"
              f"{rec['loss_share_from_discard']:15.4f}"
              f"{str(rec['monotone']):>10s}{flag}")

    print()
    print("distortion quantiles per family, and where lambda sits")
    for fam in sorted(out):
        q = out[fam]["distortion_quantiles"]
        print(f"  {fam:12s}" + "  ".join(f"{k}={v:.4f}" for k, v in q.items())
              + f"   lambda {out[fam]['lambda_star']:.4f}")

    insufficient = [f for f, r in out.items() if not r["sufficient"]]
    if insufficient:
        print()
        print(f"families with fewer than {MIN_FAMILY_N} candidates: "
              f"{insufficient}")
        print("  their thresholds are reported but are not trustworthy and "
              "must not be silently replaced by a global value")

    Path(args.out).write_text(json.dumps(
        {"alpha": args.alpha, "seed": args.seed, "source": args.source,
         "n_windows": len(windows), "dropped": dropped,
         "min_family_n": MIN_FAMILY_N, "families": out}, indent=1,
        default=float), encoding="utf-8")
    print()
    print("___CONFORMAL_FAMILY_DONE___", flush=True)


if __name__ == "__main__":
    main()
