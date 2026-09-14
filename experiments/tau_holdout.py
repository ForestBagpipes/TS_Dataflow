"""Choosing the structural threshold on held out data.

The ablation ladder showed tau 0.12 is off the efficient frontier: damage rises
sixfold between 0.04 and 0.12 while repair moves 0.004. Moving tau on that
basis would be tuning against the corpus the results are reported on, and the
value would be chosen after seeing the failure it prevents, which is the
practice this paper argues against.

So the selection happens here, on a corpus built from a different seed, and the
chosen value is then applied to the reporting corpus exactly once. The
selection rule is fixed before looking at the numbers and written into the code
below: take the largest tau whose damage is within one tenth of the minimum
damage observed, which keeps as much repair capacity as possible while staying
on the flat part of the damage curve.

The reporting corpus is never consulted during selection.

Usage:
    python -u experiments/tau_holdout.py --device cuda
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
from introact_ts.verify import VerifyConfig  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402

#: Extended left in the second pass. The first pass selected 0.02, the leftmost
#: point, which means the rule found no plateau inside the range and the
#: obvious question is whether 0.02 is on the frontier or merely the edge of
#: where anyone looked. A knee must exist somewhere below, since tau at zero
#: rejects every edit and repair must collapse, so these two points either find
#: it or show 0.02 is already on the flat part.
TAUS = [0.005, 0.01, 0.02, 0.03, 0.04, 0.06, 0.08, 0.12, 0.20]
PROTECTED = ("clean", "hard", "rare_valid", "changepoint", "clean_ood")

#: Seeds. The holdout seed is the only corpus consulted while choosing tau.
HOLDOUT_SEED = 123
REPORT_SEED = 42


def score(traces, windows):
    """Damage on protected windows and fidelity gain on contaminated ones."""
    byid = {w.window_id: w for w in windows}
    dmg, before, after = [], [], []
    for t in traces:
        w = byid[t.window_id]
        if w.clean_series is None:
            continue
        ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))
        off = t.crop_offset
        a = _nmse(t.final_series, w.clean_series[off:], ref_var)
        if w.stratum in PROTECTED:
            dmg.append(a)
        elif w.stratum == "contaminated":
            before.append(_nmse(w.series, w.clean_series, ref_var))
            after.append(a)
    b, af = float(np.mean(before)), float(np.mean(after))
    return {
        "mean_damage": float(np.mean(dmg)) if dmg else 0.0,
        "repair_reduction": (1.0 - af / b) if b > 1e-9 else 0.0,
        "n_modified": sum(1 for t in traces if t.modified),
    }


def sweep(agent, windows, states, taus):
    """Re curate at each tau, reusing the calibration built during perceive.

    The agent must be the one that perceived these windows. Building a fresh
    agent per tau loses the peer calibration, which lives on the instance and
    is populated by perceive, and every curate call then fails on a null
    calibration. Only the threshold changes between runs.
    """
    out = {}
    for tau in taus:
        agent.cfg.verification.tau = tau
        t0 = time.time()
        traces = [agent.curate_window(w, s, peer_idx=i)
                  for i, (w, s) in enumerate(zip(windows, states))]
        r = score(traces, windows)
        r["seconds"] = time.time() - t0
        out[f"{tau:.2f}"] = r
        print(f"  tau {tau:.2f}  damage {r['mean_damage']:.4f}  "
              f"repair {r['repair_reduction']:+.3f}  edited {r['n_modified']:4d}  "
              f"{r['seconds']:.0f}s", flush=True)
    return out


def choose(results):
    """Largest tau whose damage is within a tenth of the minimum.

    Fixed before the numbers were seen. Keeps repair capacity while staying on
    the flat part of the damage curve rather than at its extreme left end.
    """
    dmgs = {float(k): v["mean_damage"] for k, v in results.items()}
    lo = min(dmgs.values())
    budget = lo * 1.10 if lo > 0 else 1e-9
    ok = [t for t, d in dmgs.items() if d <= budget]
    return max(ok) if ok else min(dmgs, key=dmgs.get)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--n", type=int, default=800)
    args = ap.parse_args()

    n = args.n
    spec_kw = dict(n_contaminated=int(n * 0.35), n_clean=int(n * 0.20),
                   n_hard=int(n * 0.1125), n_rare_valid=int(n * 0.1125),
                   n_changepoint=int(n * 0.1125), n_clean_ood=int(n * 0.1125))
    models = make_pool(PRESETS[args.preset]["curation"], device=args.device)

    print(f"holdout corpus, seed {HOLDOUT_SEED}", flush=True)
    hw = build_corpus(CorpusSpec(seed=HOLDOUT_SEED, **spec_kw), source="ett")
    agent = IntroActAgent(models, AgentConfig())
    t0 = time.time()
    hs = agent.perceive(hw)
    print(f"  perceive {time.time() - t0:.0f}s on {len(hw)} windows", flush=True)
    holdout = sweep(agent, hw, hs, TAUS)

    tau_star = choose(holdout)
    print(f"\nselected tau {tau_star:.2f} by the pre committed rule", flush=True)

    print(f"\nreporting corpus, seed {REPORT_SEED}, old tau against new", flush=True)
    rw = build_corpus(CorpusSpec(seed=REPORT_SEED, **spec_kw), source="ett")
    t0 = time.time()
    rs = agent.perceive(rw)
    print(f"  perceive {time.time() - t0:.0f}s on {len(rw)} windows", flush=True)
    agent.cfg.verification.tau = 0.12
    report = sweep(agent, rw, rs, sorted({0.12, tau_star}))

    payload = {"holdout_seed": HOLDOUT_SEED, "report_seed": REPORT_SEED,
               "taus": TAUS, "holdout": holdout, "selected": tau_star,
               "report": report,
               "rule": "largest tau with damage within 1.10x the minimum"}
    (ROOT / "results" / "tau_holdout.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8")

    old, new = report.get("0.12"), report.get(f"{tau_star:.2f}")
    if old and new and tau_star != 0.12:
        print(f"\non the reporting corpus")
        print(f"  tau 0.12  damage {old['mean_damage']:.4f}  "
              f"repair {old['repair_reduction']:+.3f}  edited {old['n_modified']}")
        print(f"  tau {tau_star:.2f}  damage {new['mean_damage']:.4f}  "
              f"repair {new['repair_reduction']:+.3f}  edited {new['n_modified']}")
        dd = 100 * (1 - new["mean_damage"] / max(old["mean_damage"], 1e-12))
        print(f"  damage {dd:+.1f} percent, repair change "
              f"{new['repair_reduction'] - old['repair_reduction']:+.4f}")
    print("___TAU_HOLDOUT_DONE___", flush=True)


if __name__ == "__main__":
    main()
