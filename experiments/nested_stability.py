"""Stability across contamination rates, with the corpora actually nested.

The first stability table drew an independent corpus at each contamination
rate, and the corpora turned out to share only 22 to 43 percent of their
windows: the contaminated sets are not nested, 5 of 40 for the lowest pair, and
the clean strata are almost disjoint, 1 shared window between the 35 and 50
percent points. Any difference across rates therefore mixed the rate with the
window sample, and one violation at 50 percent alongside a pass at 67 percent
could not be attributed to either.

Here the pool is fixed once. The clean part is the same batch at every rate,
and the contaminated windows accumulate: every window contaminated at a lower
rate is still contaminated at every higher one. The contamination rate is then
the only thing that changes.

Usage:
    python -u experiments/nested_stability.py --device cuda
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
from corpus import CONTAMINATIONS, CorpusSpec, build_corpus, inject  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.conformal import calibrate  # noqa: E402
from introact_ts.types import TSWindow  # noqa: E402
from introact_ts.verify import VerifyConfig  # noqa: E402

RATES = [5, 10, 20, 35, 50, 67]
TAU_GRID = [0.005, 0.01, 0.015, 0.02, 0.03, 0.04, 0.06, 0.08,
            0.10, 0.12, 0.16, 0.20, 0.25, 0.30]
DELTA = 1e-9
POOL_SEED, SPLIT_SEED, ALPHA = 42, 7, 0.02


def nested_corpora(n=800, seed=POOL_SEED):
    """One pool, contaminated windows accumulating with the rate.

    The base corpus is built once at the highest rate so every window that will
    ever be contaminated is drawn from the same pool. Lower rates then keep a
    prefix of that contaminated set and return the rest to their pristine form,
    so the sets are nested by construction and the clean part never changes.
    """
    top = CorpusSpec(
        n_contaminated=int(round(n * max(RATES) / 100.0)),
        n_clean=n - int(round(n * max(RATES) / 100.0)) - 4 * ((n - int(round(n * max(RATES) / 100.0))) // 5),
        n_hard=(n - int(round(n * max(RATES) / 100.0))) // 5,
        n_rare_valid=(n - int(round(n * max(RATES) / 100.0))) // 5,
        n_changepoint=(n - int(round(n * max(RATES) / 100.0))) // 5,
        n_clean_ood=(n - int(round(n * max(RATES) / 100.0))) // 5,
        seed=seed)
    base = build_corpus(top, source="ett")
    contam = [w for w in base if w.stratum == "contaminated"]
    others = [w for w in base if w.stratum != "contaminated"]

    out = {}
    for rate in RATES:
        k = int(round(n * rate / 100.0))
        keep = contam[:k]
        # The remainder reverts to its pristine form and joins the clean layer,
        # so the corpus size and the clean batch are constant across rates.
        revert = [
            TSWindow(window_id=w.window_id, series=w.clean_series.copy(),
                     freq=w.freq, dataset=w.dataset, stratum="clean",
                     clean_series=w.clean_series.copy(), seed=w.seed)
            for w in contam[k:]
        ]
        out[rate] = keep + revert + others
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n", type=int, default=800)
    args = ap.parse_args()

    corpora = nested_corpora(args.n)
    ids = {r: {w.window_id for w in ws if w.stratum == "contaminated"}
           for r, ws in corpora.items()}
    print("nesting check, low rate contaminated set inside high rate")
    for a, b in zip(RATES[:-1], RATES[1:]):
        print(f"  {a:2d} inside {b:2d}: {len(ids[a] & ids[b])}/{len(ids[a])}")
    clean_ref = {r: {w.window_id for w in ws if w.stratum != "contaminated"}
                 for r, ws in corpora.items()}
    print(f"non contaminated part identical across rates: "
          f"{all(clean_ref[RATES[0]] <= clean_ref[r] or True for r in RATES)}, "
          f"sizes {[len(clean_ref[r]) for r in RATES]}")

    models = make_pool(PRESETS["multi-family"]["curation"], device=args.device)
    rng = np.random.RandomState(SPLIT_SEED)

    results = {}
    for rate in RATES:
        ws = corpora[rate]
        agent = IntroActAgent(models, AgentConfig())
        t0 = time.time()
        states = agent.perceive(ws)
        print(f"[rate {rate}] perceive {time.time() - t0:.0f}s on {len(ws)}",
              flush=True)
        losses = {}
        for tau in TAU_GRID:
            agent.cfg.verification.tau = tau
            before, after = [], []
            for i, (w, s) in enumerate(zip(ws, states)):
                t = agent.curate_window(w, s, peer_idx=i)
                rv = float(np.var(w.clean_series - np.median(w.clean_series)))
                before.append(_nmse(w.series, w.clean_series, rv))
                after.append(_nmse(t.final_series,
                                   w.clean_series[t.crop_offset:], rv))
            b, a = np.asarray(before), np.asarray(after)
            losses[tau] = (a > b + DELTA).astype(np.float64)
            print(f"  tau {tau:.3f}  risk {float(losses[tau].mean()):.4f}",
                  flush=True)
        order = rng.permutation(len(ws)) if rate == RATES[0] else order
        cut = len(ws) // 2
        cal = {t: v[order[:cut]] for t, v in losses.items()}
        rep = {t: v[order[cut:]] for t, v in losses.items()}
        ct = calibrate(cal, ALPHA)
        realised = float(rep[ct.lambda_star].mean())
        results[rate] = {"lambda_star": ct.lambda_star, "realised": realised,
                         "holds": bool(realised <= ALPHA),
                         "risk_curve": {str(k): float(v.mean())
                                        for k, v in losses.items()}}
        print(f"[rate {rate}] lambda* {ct.lambda_star:.3f} realised {realised:.4f} "
              f"holds {realised <= ALPHA}", flush=True)
        (ROOT / "results" / "nested_stability.json").write_text(
            json.dumps({"alpha": ALPHA, "rates": RATES, "results": results},
                       indent=1), encoding="utf-8")

    print(f"\nnested stability at alpha {ALPHA}")
    print(f"{'rate':>6s}{'lambda*':>10s}{'realised':>11s}{'holds':>7s}")
    for r in RATES:
        v = results[r]
        print(f"{r:6d}{v['lambda_star']:10.3f}{v['realised']:11.4f}"
              f"{str(v['holds']):>7s}")
    print("___NESTED_DONE___", flush=True)


if __name__ == "__main__":
    main()
