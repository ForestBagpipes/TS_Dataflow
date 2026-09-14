"""Contamination rate sweep, both rulers at every point.

The headline claim is no longer which method has the higher net number. It is
that curating for model utility and curating for fidelity to a pristine
reference are different objectives that agree at low contamination and part
company at high contamination on defects a strong model is robust to. This
sweep is the experiment that shows where they part.

Every point records both rulers per contamination type. Nothing is averaged
across strata, because one stratum carries most of the absolute error and a
corpus mean is that stratum wearing a disguise.

Only the methods the comparison needs are run, since the ablation ladder is a
separate job on the same queue and re running it at six contamination rates
would buy nothing.

Usage:
    python -u experiments/run_sweep.py --rates 5 10 20 35 50 67 --seeds 42
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

from audit import _nmse, replay_method  # noqa: E402
from baselines import BASELINES  # noqa: E402
from corpus import CorpusSpec, build_corpus  # noqa: E402
from metrics import summarise  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402

#: Windows per sweep point. Smaller than the xl run because a sweep needs the
#: trend across rates, not the tightest possible estimate at any one of them.
#:
#: Known limitation of this design. Holding the total fixed means the count per
#: contamination type falls with the rate: at 5 percent there are 40
#: contaminated windows split across seven types, so roughly six each, which is
#: enough to place the aggregate trend and not enough to rank types against
#: each other. Per type conclusions should be drawn from the high rate points
#: and from the 2000 window run, where each type has around 105 members. Fixing
#: this properly means holding the contaminated count fixed and varying the
#: clean count, which at 5 percent would need a 14000 window corpus.
N_TOTAL = 800

#: Baselines plus the full agent. The ablation ladder runs separately.
SWEEP_BASELINES = ["no_action", "always_clean", "stat_only", "quality_rank"]


def spec_for(rate_pct: int, seed: int, n_total: int = N_TOTAL) -> CorpusSpec:
    """Corpus with the requested contaminated share, protected strata balanced.

    The five protected strata keep equal shares of whatever is left, so the
    protection measurement has the same power at every rate and only the thing
    under study changes.
    """
    n_contam = int(round(n_total * rate_pct / 100.0))
    rest = n_total - n_contam
    per = rest // 5
    return CorpusSpec(
        n_contaminated=n_contam,
        n_clean=rest - 4 * per,
        n_hard=per,
        n_rare_valid=per,
        n_changepoint=per,
        n_clean_ood=per,
        seed=seed,
    )


def two_rulers(traces, windows, method):
    """Per contamination fidelity gain and model utility gain for one method."""
    replayed = replay_method([t.summary() for t in traces], windows, method)
    byid = {w.window_id: w for w in windows}
    util = {t.window_id: t.final_utility - t.initial_utility for t in traces}

    groups = {}
    for wid, rep in replayed.items():
        w = byid[wid]
        if w.clean_series is None:
            continue
        key = w.contamination or w.stratum
        ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))
        before = _nmse(w.series, w.clean_series, ref_var)
        after = _nmse(rep["final_series"], w.clean_series[rep["crop_offset"]:], ref_var)
        d = groups.setdefault(key, {"n": 0, "before": [], "after": [], "du": []})
        d["n"] += 1
        d["before"].append(before)
        d["after"].append(after)
        d["du"].append(util.get(wid, 0.0))

    out = {}
    for k, d in sorted(groups.items()):
        b, a = float(np.mean(d["before"])), float(np.mean(d["after"]))
        repairable = b > 1e-6
        out[k] = {
            "n": d["n"],
            "nmse_before": b,
            "nmse_after": a,
            "fidelity_gain": (1.0 - a / b) if repairable else None,
            "damage": None if repairable else a,
            "model_utility_gain": float(np.mean(d["du"])),
        }
    return out


def run_point(rate, seed, models, transfer, verbose=True):
    spec = spec_for(rate, seed)
    windows = build_corpus(spec, source="ett")
    agent = IntroActAgent(models, AgentConfig())
    t0 = time.time()
    states = agent.perceive(windows)
    if verbose:
        print(f"    perception {time.time() - t0:.0f}s", flush=True)

    point = {"rate": rate, "seed": seed, "n_windows": len(windows), "methods": {}}
    for name in SWEEP_BASELINES:
        t0 = time.time()
        traces = BASELINES[name](windows, states, models)
        point["methods"][name] = {
            "summary": summarise(traces, windows, transfer),
            "rulers": two_rulers(traces, windows, name),
        }
        if verbose:
            print(f"    {name:16s} {time.time() - t0:.0f}s", flush=True)

    t0 = time.time()
    traces = [agent.curate_window(w, s, peer_idx=i)
              for i, (w, s) in enumerate(zip(windows, states))]
    point["methods"]["introact_full"] = {
        "summary": summarise(traces, windows, transfer),
        "rulers": two_rulers(traces, windows, "introact_full"),
    }
    if verbose:
        print(f"    introact_full    {time.time() - t0:.0f}s", flush=True)
    return point


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rates", type=int, nargs="+", default=[5, 10, 20, 35, 50, 67])
    ap.add_argument("--seeds", type=int, nargs="+", default=[42])
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--out", default=str(ROOT / "results" / "sweep"))
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    pools = PRESETS[args.preset]
    models = make_pool(pools["curation"], device=args.device)
    transfer = make_pool(pools["transfer"], device=args.device)

    points = []
    for rate in args.rates:
        for seed in args.seeds:
            print(f"[{time.strftime('%H:%M:%S')}] rate {rate} percent, seed {seed}",
                  flush=True)
            t0 = time.time()
            points.append(run_point(rate, seed, models, transfer))
            print(f"  point done in {time.time() - t0:.0f}s", flush=True)
            (out_dir / "sweep.json").write_text(
                json.dumps(points, indent=2, default=float), encoding="utf-8")
    print("___SWEEP_DONE___", flush=True)


if __name__ == "__main__":
    main()
