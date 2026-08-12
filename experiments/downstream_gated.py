"""Does gated curation produce data a model actually learns better from?

This is the question the whole project exists to answer and the one piece of
evidence that was missing. Damage and repair are measured against a pristine
reference we happen to hold; this trains a forecaster on what each method
produced and scores it on futures no method ever touched.

The protocol from `downstream.py` is kept exactly: windows are split before any
curation, training uses whatever a method output, and the test target is always
the pristine series. A method that smooths everything produces training data
that predicts its own smoothed future well and the real one badly, and only a
clean test target exposes that.

What is new here is the gated arms. `stat_only_gated` and `always_clean_gated`
run the same proposals as their ungated counterparts and keep only what the
acceptance rule admits, so the comparison isolates the gate.

Usage:
    python -u experiments/downstream_gated.py --device cuda --n 800 --seeds 42 1 2
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

from baselines import BASELINES  # noqa: E402
from corpus import CorpusSpec, build_corpus  # noqa: E402
from downstream import compare, evaluate, split_windows  # noqa: E402
from gating import gate, proposals_of  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.verify import VerifyConfig  # noqa: E402

METHODS = ["no_action", "stat_only", "always_clean"]


class _GatedTrace:
    """Minimal trace shape for `evaluate`, which needs id and final series."""

    def __init__(self, window_id, final_series, crop_offset=0):
        self.window_id = window_id
        self.final_series = final_series
        self.crop_offset = crop_offset


def run_seed(seed, n, tau, device, include_deep):
    spec = CorpusSpec(
        n_contaminated=int(n * 0.35), n_clean=int(n * 0.20),
        n_hard=int(n * 0.1125), n_rare_valid=int(n * 0.1125),
        n_changepoint=int(n * 0.1125), n_clean_ood=int(n * 0.1125), seed=seed,
    )
    windows = build_corpus(spec, source="ett")
    train_ids, test_ids = split_windows(windows, train_frac=0.7, seed=seed)

    models = make_pool(PRESETS["multi-family"]["curation"], device=device)
    cfg = VerifyConfig(tau=tau)
    agent = IntroActAgent(models, AgentConfig(verification=cfg))
    t0 = time.time()
    states = agent.perceive(windows)
    print(f"  perceive {time.time() - t0:.0f}s", flush=True)

    byid = {w.window_id: (w, s, i)
            for i, (w, s) in enumerate(zip(windows, states))}
    results = {}

    for name in METHODS:
        t0 = time.time()
        traces = BASELINES[name](windows, states, models)
        results[name] = evaluate(traces, windows, train_ids, test_ids,
                                 include_deep=include_deep, seed=seed)
        print(f"  {name} {time.time() - t0:.0f}s", flush=True)

        if name == "no_action":
            continue
        t0 = time.time()
        gated = []
        for t in traces:
            w, s, idx = byid[t.window_id]
            plan = proposals_of(t)
            if not plan:
                gated.append(_GatedTrace(w.window_id, np.asarray(w.series, float)))
                continue
            series, crop, _, _ = gate(w, s, models, plan, agent, idx, cfg)
            gated.append(_GatedTrace(w.window_id, series, crop))
        results[f"{name}_gated"] = evaluate(gated, windows, train_ids, test_ids,
                                            include_deep=include_deep, seed=seed)
        print(f"  {name}_gated {time.time() - t0:.0f}s", flush=True)

    t0 = time.time()
    traces = [agent.curate_window(w, s, peer_idx=i)
              for i, (w, s) in enumerate(zip(windows, states))]
    results["introact_full"] = evaluate(traces, windows, train_ids, test_ids,
                                        include_deep=include_deep, seed=seed)
    print(f"  introact_full {time.time() - t0:.0f}s", flush=True)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--tau", type=float, default=0.02)
    ap.add_argument("--seeds", type=int, nargs="+", default=[42])
    ap.add_argument("--deep", action="store_true",
                    help="include PatchTST, the only deep downstream model")
    args = ap.parse_args()

    per_seed = {}
    for seed in args.seeds:
        print(f"[seed {seed}]", flush=True)
        per_seed[seed] = run_seed(seed, args.n, args.tau, args.device, args.deep)
        (ROOT / "results" / "downstream_gated.json").write_text(
            json.dumps(per_seed, indent=1, default=float), encoding="utf-8")

    order = ["no_action", "stat_only", "stat_only_gated", "always_clean",
             "always_clean_gated", "introact_full"]
    model_names = sorted({m for r in per_seed.values() for v in r.values()
                          for m, x in v.items() if isinstance(x, dict) and "mse" in x})

    print(f"\ndownstream MSE, trained on curated data, tested on pristine futures")
    print(f"seeds {args.seeds}, {'mean and std' if len(args.seeds) > 1 else 'single seed'}")
    for mdl in model_names:
        print(f"\n-- {mdl}")
        print(f"{'method':22s}{'mse':>12s}{'std':>10s}{'mae':>12s}"
              f"{'vs no_action':>14s}")
        base = None
        for k in order:
            vals = [per_seed[s][k][mdl]["mse"] for s in args.seeds
                    if k in per_seed[s] and mdl in per_seed[s][k]]
            maes = [per_seed[s][k][mdl]["mae"] for s in args.seeds
                    if k in per_seed[s] and mdl in per_seed[s][k]]
            if not vals:
                continue
            m, sd = float(np.mean(vals)), float(np.std(vals))
            if k == "no_action":
                base = m
                print("-- reference, untouched corpus")
            rel = f"{100 * (1 - m / max(base, 1e-12)):+.1f}%" if base else "ref"
            print(f"{k:22s}{m:12.5f}{sd:10.5f}{float(np.mean(maes)):12.5f}{rel:>14s}")
            if k == "no_action":
                print("-- curated corpora")

    print("___DOWNSTREAM_GATED_DONE___", flush=True)


if __name__ == "__main__":
    main()
