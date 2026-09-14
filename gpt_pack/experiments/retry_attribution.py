"""Where the retry mechanism's edits come from, by direct observation.

The ablation ladder reports one number per rung, so the comparison between the
single step rung and the full agent had to be made by subtracting the two
summaries. That subtraction assumes the full agent's edited windows are a
superset of the single step agent's, which is not guaranteed, because a retry
changes the state the next candidate is judged against.

This script removes the assumption. It runs both configurations on one corpus
with one shared perception pass and writes a per window record for each, so the
comparison is made on observed pairs.

Two questions are answered directly.

**Within the full agent.** For every window it edited, was the first candidate
the one that was accepted, or was the first candidate rejected and a later one
accepted. Windows of the second kind are the ones the retry mechanism exists
for. Their improved to worsened ratio against the first kind is the quantity
that was previously estimated by subtraction.

**Across the two configurations.** Paired per window, which lets McNemar replace
the unpaired Fisher tests. Those were reported as upper bounds and this makes
them exact.

Usage:
    python -u experiments/retry_attribution.py --scale xl --device cuda
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

from corpus import build_corpus  # noqa: E402
from run_agent import SCALES  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.policy import PolicyConfig  # noqa: E402

PROTECTED = ("clean", "hard", "rare_valid", "changepoint", "clean_ood")


def _nmse(series, clean, ref_var):
    """Normalised error against the pristine reference, the metrics.py rule."""
    n = min(len(series), len(clean))
    a = np.nan_to_num(np.asarray(series[:n], dtype=np.float64))
    b = np.nan_to_num(np.asarray(clean[:n], dtype=np.float64))
    return float(np.mean((a - b) ** 2) / max(ref_var, 1e-12))


def record_of(trace, window):
    """One window's outcome, with the origin of its first accepted action.

    ``origin`` is the distinction the whole question turns on:

    first   the first candidate the policy proposed was accepted
    retry   the first candidate was rejected and a later one was accepted
    none    nothing was accepted
    """
    ref_var = float(np.var(window.clean_series - np.median(window.clean_series)))
    before = _nmse(trace.initial_series, window.clean_series, ref_var)
    after = _nmse(trace.final_series, window.clean_series[trace.crop_offset:], ref_var)

    origin = "none"
    for i, r in enumerate(trace.records):
        if r.accepted and r.action.value not in ("KEEP", "ABSTAIN", "QUARANTINE"):
            origin = "first" if i == 0 else "retry"
            break

    return {
        "window_id": window.window_id,
        "stratum": window.stratum,
        "contamination": window.contamination,
        "edited": bool(trace.content_modified(window.series)),
        "origin": origin,
        "nmse_before": before,
        "nmse_after": after,
        "improved": bool(after < before - 1e-9),
        "worsened": bool(after > before + 1e-9),
        "n_steps": len(trace.records),
        "n_rollbacks": trace.n_rollbacks,
        "first_verdict": trace.records[0].verdict.value if trace.records else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="xl", choices=list(SCALES))
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(ROOT / "results" / "retry_attribution.json"))
    args = ap.parse_args()

    spec = SCALES[args.scale]
    spec.seed = args.seed
    windows = build_corpus(spec, source="ett")
    models = make_pool(PRESETS[args.preset]["curation"], device=args.device)
    print(f"corpus {len(windows)} windows, pool {len(models)}", flush=True)

    # One perception pass, shared, exactly as the ablation ladder does it.
    reference = IntroActAgent(models, AgentConfig())
    t0 = time.time()
    states = reference.perceive(windows)
    print(f"perception {time.time() - t0:.0f}s", flush=True)

    arms = {
        "full": AgentConfig(),
        "single_step": AgentConfig(policy=PolicyConfig(max_candidates=1)),
    }

    payload = {"scale": args.scale, "n_windows": len(windows), "seed": args.seed,
               "pool_size": len(models), "arms": {}}

    for name, cfg in arms.items():
        t0 = time.time()
        agent = IntroActAgent(models, cfg)
        agent._calib = reference._calib
        agent._ood = reference._ood
        agent._reference = reference._reference
        traces = [agent.curate_window(w, s, peer_idx=i)
                  for i, (w, s) in enumerate(zip(windows, states))]
        payload["arms"][name] = [record_of(t, w) for t, w in zip(traces, windows)]
        print(f"  {name:14s} {time.time() - t0:6.0f}s", flush=True)
        Path(args.out).write_text(json.dumps(payload, indent=1, default=float),
                                  encoding="utf-8")

    # Direct observation, inside the full arm.
    full = payload["arms"]["full"]
    by_origin = {}
    for r in full:
        if not r["edited"]:
            continue
        d = by_origin.setdefault(r["origin"], {"improved": 0, "worsened": 0, "n": 0})
        d["n"] += 1
        d["improved"] += int(r["improved"])
        d["worsened"] += int(r["worsened"])
    print("\nwithin the full agent, edited windows by origin of the accepted action")
    print(f"{'origin':>8s}{'n':>7s}{'improved':>10s}{'worsened':>10s}{'ratio':>9s}")
    for k in ("first", "retry", "none"):
        d = by_origin.get(k)
        if not d:
            continue
        ratio = d["improved"] / d["worsened"] if d["worsened"] else float("inf")
        print(f"{k:>8s}{d['n']:7d}{d['improved']:10d}{d['worsened']:10d}{ratio:9.3f}")

    # Paired across arms.
    single = {r["window_id"]: r for r in payload["arms"]["single_step"]}
    pairs = {"both": 0, "full_only": 0, "single_only": 0, "neither": 0}
    for r in full:
        s = single[r["window_id"]]
        key = ("both" if r["edited"] and s["edited"] else
               "full_only" if r["edited"] else
               "single_only" if s["edited"] else "neither")
        pairs[key] += 1
    print(f"\npaired edit sets: {pairs}")
    print(f"superset assumption holds only if single_only is 0, it is "
          f"{pairs['single_only']}")

    payload["by_origin"] = by_origin
    payload["pairs"] = pairs
    Path(args.out).write_text(json.dumps(payload, indent=1, default=float),
                              encoding="utf-8")
    print("___RETRY_ATTRIBUTION_DONE___", flush=True)


if __name__ == "__main__":
    main()
