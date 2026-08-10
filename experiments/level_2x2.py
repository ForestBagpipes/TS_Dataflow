"""Separating level uncertainty from local predictability.

The controlled ladder killed two explanations for what behavioural risk
measures. It is not classical predictability, since white noise barely alarms
the model and AR(0.95) alarms it far more than AR(0.30) despite being the more
forecastable of the two. It is not structural familiarity either, since
piecewise linear, staircase and sawtooth all score below the real data anchor.

What the top of that table had in common was a randomly wandering level. This
experiment tests that directly by crossing level behaviour against local shape
predictability, which a sweep over the AR coefficient cannot do: phi moves
persistence, within window non stationarity and the stationary variance
sigma^2/(1-phi^2) all at once, so a monotone result would not be attributable.

  cell                     level        local shape      prediction if the
                                                         hypothesis holds
  sine_anchored            anchored     predictable      low
  noise_anchored           anchored     unpredictable    low
  sine_on_walk             wandering    predictable      HIGH, the decisive cell
  walk_only                wandering    unpredictable    high
  sine_on_ramp             moving but   predictable      low if the variable is
                           determined                    uncertainty, high if it
                                                         is merely level change

`sine_on_walk` and `sine_on_ramp` are built by the same code path with the same
component variances, so the only difference between them is whether the
baseline is a random walk or a straight line. That pair is the cleanest test in
the design.

Every series is normalised to unit variance at the end so amplitude cannot act
as a hidden variable.

Known limitation, stated rather than hidden. In the composite cells the sine
carries half the total variance while in `sine_anchored` it carries all of it,
so the composite cells have a locally smaller oscillation. The comparison that
is free of this is `sine_on_walk` against `sine_on_ramp`, which is why the
verdict leans on that pair.

Usage:
    python -u experiments/level_2x2.py --device cuda
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

from datasets import sample_ett_windows  # noqa: E402
from stratum_risk import describe, mann_whitney  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.types import TSWindow  # noqa: E402

T = 512
PER_CELL = 100
CELLS = ["sine_anchored", "noise_anchored", "sine_on_walk", "walk_only",
         "sine_on_ramp"]
PHIS = [0.30, 0.50, 0.70, 0.85, 0.95, 0.99, 1.00]


def _unit(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, float)
    s = float(np.std(x))
    return (x - float(np.mean(x))) / (s if s > 1e-12 else 1.0)


def _sine(rng) -> np.ndarray:
    t = np.arange(T, dtype=float)
    period = rng.uniform(32, 96)
    return _unit(np.sin(2 * np.pi * t / period + rng.uniform(0, 2 * np.pi)))


def make_cell(cell: str, rng) -> np.ndarray:
    """One instance. Composite cells mix unit variance components equally."""
    if cell == "sine_anchored":
        return _unit(_sine(rng))
    if cell == "noise_anchored":
        return _unit(rng.randn(T))
    if cell == "walk_only":
        return _unit(np.cumsum(rng.randn(T)))
    if cell == "sine_on_walk":
        return _unit(_sine(rng) + _unit(np.cumsum(rng.randn(T))))
    if cell == "sine_on_ramp":
        slope = np.arange(T, dtype=float) * (1.0 if rng.rand() < 0.5 else -1.0)
        return _unit(_sine(rng) + _unit(slope))
    raise ValueError(cell)


def make_ar(phi: float, rng) -> np.ndarray:
    e = rng.randn(T)
    x = np.zeros(T)
    for i in range(1, T):
        x[i] = phi * x[i - 1] + e[i]
    return _unit(x)


def build(seed: int = 11) -> list:
    rng = np.random.RandomState(seed)
    windows, wid = [], 0
    for cell in CELLS:
        for _ in range(PER_CELL):
            windows.append(TSWindow(window_id=wid, series=make_cell(cell, rng),
                                    freq="H", dataset=f"gen:{cell}", stratum=cell))
            wid += 1
    for phi in PHIS:
        name = f"phi_{phi:.2f}".replace(".", "")
        for _ in range(PER_CELL):
            windows.append(TSWindow(window_id=wid, series=make_ar(phi, rng),
                                    freq="H", dataset=f"gen:{name}", stratum=name))
            wid += 1
    for item in sample_ett_windows(PER_CELL, window_len=T, seed=seed):
        windows.append(TSWindow(window_id=wid, series=_unit(item["series"]),
                                freq=item["freq"], dataset=item["dataset"],
                                stratum="ett_real"))
        wid += 1
    return windows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--preset", default="multi-family")
    args = ap.parse_args()

    windows = build()
    print(f"{len(windows)} windows, {PER_CELL} per condition", flush=True)
    models = make_pool(PRESETS[args.preset]["curation"], device=args.device)
    agent = IntroActAgent(models, AgentConfig())
    t0 = time.time()
    states = agent.perceive(windows)
    print(f"perceive {time.time() - t0:.0f}s", flush=True)

    by = {}
    for w, s in zip(windows, states):
        by.setdefault(w.stratum, []).append(float(s.behav_risk))

    phi_names = [f"phi_{p:.2f}".replace(".", "") for p in PHIS]
    payload = {"cells": {}, "phi": {}, "tests": {}}
    for k in CELLS + phi_names + ["ett_real"]:
        d = describe(by[k])
        d["raw"] = by[k]
        (payload["cells"] if k in CELLS + ["ett_real"] else payload["phi"])[k] = d

    print()
    print(f"{'condition':18s}{'n':>5s}{'p25':>9s}{'median':>10s}{'p75':>9s}"
          f"{'iqr':>8s}{'auc vs anchored sine':>22s}{'p':>11s}")
    ref = by["sine_anchored"]
    for k in CELLS + ["ett_real"]:
        d = payload["cells"][k]
        if k == "sine_anchored":
            auc, p = "ref", ""
        else:
            t = mann_whitney(by[k], ref)
            payload["tests"][k] = t
            auc, p = f"{t['auc']:.3f}", f"{t['p']:.2e}"
        print(f"{k:18s}{d['n']:5d}{d['p25']:+9.3f}{d['median']:+10.3f}"
              f"{d['p75']:+9.3f}{d['p75'] - d['p25']:8.3f}{auc:>22s}{p:>11s}",
              flush=True)

    print()
    print("the decisive pair, same construction, only the baseline differs")
    t = mann_whitney(by["sine_on_walk"], by["sine_on_ramp"])
    payload["tests"]["walk_vs_ramp"] = t
    print(f"  sine_on_walk {np.median(by['sine_on_walk']):+.3f} against "
          f"sine_on_ramp {np.median(by['sine_on_ramp']):+.3f}, "
          f"auc {t['auc']:.3f}, p {t['p']:.2e}", flush=True)

    print()
    print("phi sweep, corroborating only, phi confounds several quantities")
    print(f"{'phi':>7s}{'median':>10s}{'iqr':>8s}")
    for p, k in zip(PHIS, phi_names):
        d = payload["phi"][k]
        print(f"{p:7.2f}{d['median']:+10.3f}{d['p75'] - d['p25']:8.3f}")
    seq = [payload["phi"][k]["median"] for k in phi_names]
    print(f"monotone rises: {sum(1 for a, b in zip(seq[:-1], seq[1:]) if b > a)}"
          f"/{len(seq) - 1}")

    mw = float(np.median(by["sine_on_walk"]))
    mr = float(np.median(by["sine_on_ramp"]))
    ms = float(np.median(by["sine_anchored"]))
    print()
    if mw > ms + 0.1 and t["p"] < 0.05 and mr < mw:
        verdict = ("level uncertainty supported, and separated from both local "
                   "predictability and mere level change")
    elif mw > ms + 0.1 and mr >= mw:
        verdict = "level change rather than level uncertainty"
    elif mw <= ms + 0.1:
        verdict = "level uncertainty not supported by the decisive cell"
    else:
        verdict = "mixed, see the table"
    print(f"verdict: {verdict}")
    payload["verdict"] = verdict

    (ROOT / "results" / "level_2x2.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8")
    print("___LEVEL2X2_DONE___", flush=True)


if __name__ == "__main__":
    main()
