"""A single signal calibrated gate, the shape the recent gating literature uses.

The systems in that line score each proposed action with one risk model and
calibrate a single threshold on that score so the rate of harmful executions
meets a stated budget. Transposed here, the score is the only thing available
that speaks to whether an edit helped, namely the change in model utility, and
the threshold is epsilon rather than a structural budget.

This is the arm the paper needs in order to say anything about that design. It
isolates one variable: whether the acceptance test consults more than the
model. Everything else is shared with our own arm, the same proposers, the same
candidates, the same probe, the same corpus.

Calibration reuses the machinery already validated for the structural
threshold. The loss is unchanged, one per window that comes out measurably
worse, and the parameter swept is epsilon.

Prediction, recorded before the run. If model utility were a sound proxy for
harm, calibrating epsilon should reach the same protection as calibrating the
structural threshold. Our characterisation says it is not a sound proxy, being
anti correlated with harm over a region we can describe, so this arm should
need a far larger epsilon to reach comparable damage and should give up much
more repair doing so. If instead it matches the structural arm, the
characterisation does not have the consequence we claim for it.

Usage:
    python -u experiments/utility_only_gate.py --device cuda --n 800
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
from baselines import BASELINES  # noqa: E402
from corpus import CorpusSpec, build_corpus  # noqa: E402
from gating import proposals_of  # noqa: E402

from introact_ts.actions import apply_action  # noqa: E402
from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.conformal import calibrate  # noqa: E402
from introact_ts.probe import ProbeConfig, probe_window, reference_scale  # noqa: E402
from introact_ts.types import Action  # noqa: E402

PROTECTED = ("clean", "hard", "rare_valid", "changepoint", "clean_ood")

#: Epsilon grid, ordered so a larger value is a stricter gate, which is what the
#: calibration machinery expects of a nested family.
EPS_GRID = [0.0, 0.005, 0.01, 0.02, 0.05, 0.10, 0.25, 0.50, 1.0, 2.0, 5.0]

#: The structural thresholds our own arm was calibrated over, for the frontier.
TAU_GRID = [0.005, 0.01, 0.02, 0.04, 0.08, 0.12, 0.20, 0.30]

ALPHA = 0.02
DELTA = 1e-9


def walk(window, state, models, plan, decide):
    """Apply a proposal sequence, committing when `decide` says so."""
    work = np.asarray(window.series, dtype=np.float64).copy()
    scale = reference_scale(window.series)
    u = state.utility
    crop = 0
    n_kept = 0
    for action, params in plan:
        outcome = apply_action(work, action, **params)
        if not outcome.applicable:
            continue
        after = probe_window(outcome.series, models, scale, ProbeConfig())
        delta_u = after.utility - u
        if decide(delta_u):
            if action is Action.RESEGMENT:
                crop += int(outcome.params.get("lo", 0))
            work = outcome.series
            u = after.utility
            n_kept += 1
    return work, crop, n_kept


def score(rows, windows):
    byid = {w.window_id: w for w in windows}
    dmg, before, after = [], [], []
    n_mod = prot = 0
    losses = []
    for r in rows:
        w = byid[r["window_id"]]
        if r["kept"]:
            n_mod += 1
            if w.stratum in PROTECTED:
                prot += 1
        rv = float(np.var(w.clean_series - np.median(w.clean_series)))
        a = _nmse(r["series"], w.clean_series[r["crop"]:], rv)
        b = _nmse(w.series, w.clean_series, rv)
        losses.append(1.0 if a > b + DELTA else 0.0)
        if w.stratum in PROTECTED:
            dmg.append(a)
        elif w.stratum == "contaminated":
            before.append(b)
            after.append(a)
    bm, am = float(np.mean(before)), float(np.mean(after))
    return ({"mean_damage": float(np.mean(dmg)),
             "repair_reduction": (1.0 - am / bm) if bm > 1e-9 else 0.0,
             "n_modified": n_mod, "protected_edits": prot},
            np.asarray(losses))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--proposer", default="stat_only")
    args = ap.parse_args()

    n = args.n
    spec = CorpusSpec(
        n_contaminated=int(n * 0.35), n_clean=int(n * 0.20),
        n_hard=int(n * 0.1125), n_rare_valid=int(n * 0.1125),
        n_changepoint=int(n * 0.1125), n_clean_ood=int(n * 0.1125), seed=args.seed)
    windows = build_corpus(spec, source="ett")
    models = make_pool(PRESETS["multi-family"]["curation"], device=args.device)
    agent = IntroActAgent(models, AgentConfig())
    t0 = time.time()
    states = agent.perceive(windows)
    print(f"{len(windows)} windows, perceive {time.time() - t0:.0f}s", flush=True)

    proposals = {t.window_id: proposals_of(t)
                 for t in BASELINES[args.proposer](windows, states, models)}
    total = sum(len(v) for v in proposals.values())
    print(f"proposer {args.proposer}, {total} candidate edits", flush=True)

    out, losses_by_eps = {}, {}
    print(f"\n{'epsilon':>9s}{'damage':>10s}{'repair':>10s}{'edits':>8s}{'prot':>7s}")
    for eps in EPS_GRID:
        t0 = time.time()
        rows = []
        for w, s in zip(windows, states):
            plan = proposals[w.window_id]
            if not plan:
                rows.append({"window_id": w.window_id, "series": w.series,
                             "crop": 0, "kept": 0})
                continue
            series, crop, kept = walk(w, s, models, plan,
                                      lambda du, _e=eps: du > _e)
            rows.append({"window_id": w.window_id, "series": series,
                         "crop": crop, "kept": kept})
        r, losses = score(rows, windows)
        out[f"{eps:g}"] = r
        losses_by_eps[eps] = losses
        print(f"{eps:9g}{r['mean_damage']:10.4f}{r['repair_reduction']:+10.3f}"
              f"{r['n_modified']:8d}{r['protected_edits']:7d}  "
              f"{time.time() - t0:.0f}s", flush=True)

    # Calibrate epsilon the same way tau was calibrated, same loss, same split.
    rng = np.random.RandomState(7)
    order = rng.permutation(len(windows))
    cut = len(windows) // 2
    # A larger epsilon is a stricter gate, so the nested family runs the other
    # way and the grid is reversed before calibration.
    cal = {-e: losses_by_eps[e][order[:cut]] for e in EPS_GRID}
    rep = {-e: losses_by_eps[e][order[cut:]] for e in EPS_GRID}
    ct = calibrate(cal, ALPHA)
    eps_star = -ct.lambda_star
    realised = float(rep[ct.lambda_star].mean())
    print(f"\ncalibrated at alpha {ALPHA}: epsilon* {eps_star:g}, "
          f"realised {realised:.4f}, holds {realised <= ALPHA}")
    sel = out[f"{eps_star:g}"]
    print(f"  at that epsilon: damage {sel['mean_damage']:.4f} "
          f"repair {sel['repair_reduction']:+.3f} edits {sel['n_modified']}")

    print(f"\nfrontier, best repair at or below each damage budget")
    print(f"{'budget':>9s}{'utility only':>14s}{'at eps':>9s}")
    frontier = []
    for budget in [0.001, 0.002, 0.005, 0.01, 0.02, 0.05]:
        ok = [(v["repair_reduction"], k) for k, v in out.items()
              if v["mean_damage"] <= budget]
        best = max(ok) if ok else (float("nan"), "none")
        frontier.append({"budget": budget, "repair": best[0], "eps": best[1]})
        print(f"{budget:9.3f}{best[0]:+14.3f}{best[1]:>9s}")

    (ROOT / "results" / "utility_only_gate.json").write_text(
        json.dumps({"proposer": args.proposer, "seed": args.seed,
                    "alpha": ALPHA, "grid": out, "epsilon_star": eps_star,
                    "realised": realised, "frontier": frontier},
                   indent=1, default=float), encoding="utf-8")
    print("___UTILITY_ONLY_DONE___", flush=True)


if __name__ == "__main__":
    main()
