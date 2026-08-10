"""What variable does behavioural risk actually measure?

Three explanations have been offered for the same observation and two are now
dead. Behavioural risk is highest on synthetic clean shapes and lowest on real
cross domain windows, both of which are clean and both of which sit outside the
base corpus, so unfamiliarity of domain does not explain it. Three classical
predictability proxies fail to separate those two strata at all, and the hard
stratum has the lowest linear predictability in the corpus while barely
alarming the model, so predictability in the classical sense does not explain
it either.

This experiment is built to name the variable rather than to argue about it.
Everything here is generated, so no series belongs to a public dataset and no
question about pretraining corpus membership can arise. Two ladders are run
against each other:

  the predictability ladder     pure sine through to a random walk, monotonically
                                less forecastable, all stationary except the last
  the deterministic irregular   piecewise linear, staircase, sawtooth, pulse train
  ladder                        exactly forecastable given the rule, and shaped
                                unlike anything typical of a time series corpus

The two hypotheses make opposite predictions on the second ladder, which is why
it is the discriminating one:

  A, the variable is predictability. Then behavioural risk rises along the first
     ladder and stays low on the second, since those series are deterministic.
  B, the variable is structural familiarity, how much the shape resembles what
     the model saw in pretraining. Then the second ladder alarms the model just
     as much as a random walk does, despite being deterministic.

Real ETT windows are included as the anchor at the familiar end, and every rung
carries 100 instances so the spread can be reported rather than a bare median.

Usage:
    python -u experiments/ladder.py --device cuda
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
PER_RUNG = 100

#: Ordered so the table reads as a gradient. The first block is the
#: predictability ladder, the second is the discriminating one.
PREDICTABILITY = ["sine_pure", "sine_noisy", "ar_095", "ar_070", "ar_030",
                  "white_noise", "random_walk"]
IRREGULAR = ["piecewise_linear", "staircase", "sawtooth", "pulse_train"]
ANCHOR = ["ett_real"]


def _norm(x: np.ndarray) -> np.ndarray:
    """Zero mean unit variance, so amplitude cannot act as a hidden variable."""
    x = np.asarray(x, float)
    s = float(np.std(x))
    return (x - float(np.mean(x))) / (s if s > 1e-12 else 1.0)


def generate(kind: str, rng: np.random.RandomState) -> np.ndarray:
    t = np.arange(T, dtype=float)

    if kind == "sine_pure":
        period = rng.uniform(32, 96)
        return _norm(np.sin(2 * np.pi * t / period + rng.uniform(0, 2 * np.pi)))

    if kind == "sine_noisy":
        period = rng.uniform(32, 96)
        base = np.sin(2 * np.pi * t / period + rng.uniform(0, 2 * np.pi))
        return _norm(base + 0.3 * rng.randn(T))

    if kind.startswith("ar_"):
        phi = {"ar_095": 0.95, "ar_070": 0.70, "ar_030": 0.30}[kind]
        e = rng.randn(T)
        x = np.zeros(T)
        for i in range(1, T):
            x[i] = phi * x[i - 1] + e[i]
        return _norm(x)

    if kind == "white_noise":
        return _norm(rng.randn(T))

    if kind == "random_walk":
        return _norm(np.cumsum(rng.randn(T)))

    if kind == "piecewise_linear":
        # Deterministic given the breakpoints, and every segment is a straight
        # line, which is about as forecastable as a signal gets.
        n_seg = int(rng.randint(3, 7))
        bps = np.sort(rng.choice(np.arange(40, T - 40), n_seg - 1, replace=False))
        bps = np.concatenate([[0], bps, [T]])
        x = np.zeros(T)
        level = 0.0
        for a, b in zip(bps[:-1], bps[1:]):
            slope = rng.uniform(-1, 1)
            seg = level + slope * np.arange(b - a)
            x[a:b] = seg
            level = seg[-1]
        return _norm(x)

    if kind == "staircase":
        n_steps = int(rng.randint(4, 10))
        edges = np.sort(rng.choice(np.arange(20, T - 20), n_steps, replace=False))
        x = np.zeros(T)
        level = 0.0
        prev = 0
        for e in list(edges) + [T]:
            x[prev:e] = level
            level += rng.uniform(-2, 2)
            prev = e
        return _norm(x)

    if kind == "sawtooth":
        period = rng.uniform(40, 100)
        return _norm(((t % period) / period) * 2.0 - 1.0)

    if kind == "pulse_train":
        period = int(rng.randint(30, 80))
        width = int(rng.randint(2, 6))
        x = np.zeros(T)
        for start in range(int(rng.randint(0, period)), T, period):
            x[start:start + width] = 1.0
        return _norm(x)

    raise ValueError(kind)


def build(seed: int = 7) -> list:
    """One window list holding every rung plus the real data anchor."""
    rng = np.random.RandomState(seed)
    windows, wid = [], 0

    for kind in PREDICTABILITY + IRREGULAR:
        for _ in range(PER_RUNG):
            windows.append(TSWindow(
                window_id=wid, series=generate(kind, rng), freq="H",
                dataset=f"gen:{kind}", stratum=kind,
            ))
            wid += 1

    for item in sample_ett_windows(PER_RUNG, window_len=T, seed=seed):
        windows.append(TSWindow(
            window_id=wid, series=_norm(item["series"]), freq=item["freq"],
            dataset=item["dataset"], stratum="ett_real",
        ))
        wid += 1
    return windows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--preset", default="multi-family")
    args = ap.parse_args()

    windows = build()
    print(f"{len(windows)} windows, {PER_RUNG} per rung", flush=True)

    models = make_pool(PRESETS[args.preset]["curation"], device=args.device)
    agent = IntroActAgent(models, AgentConfig())
    t0 = time.time()
    states = agent.perceive(windows)
    print(f"perceive {time.time() - t0:.0f}s", flush=True)

    by = {}
    for w, s in zip(windows, states):
        by.setdefault(w.stratum, []).append(float(s.behav_risk))

    order = PREDICTABILITY + IRREGULAR + ANCHOR
    payload = {"per_rung": {}, "tests": {}}
    for k in order:
        payload["per_rung"][k] = describe(by[k])
        payload["per_rung"][k]["raw"] = by[k]

    ref = by["ett_real"]
    for k in order:
        if k == "ett_real":
            continue
        payload["tests"][k] = mann_whitney(by[k], ref)

    print()
    print(f"{'rung':20s}{'n':>5s}{'p25':>9s}{'median':>10s}{'p75':>9s}{'iqr':>8s}"
          f"{'auc vs ett':>12s}{'p':>11s}")
    for block, title in [(PREDICTABILITY, "predictability ladder"),
                         (IRREGULAR, "deterministic irregular ladder"),
                         (ANCHOR, "anchor")]:
        print(f"-- {title}")
        for k in block:
            d = payload["per_rung"][k]
            t = payload["tests"].get(k)
            auc = f"{t['auc']:.3f}" if t else "ref"
            p = f"{t['p']:.2e}" if t else ""
            print(f"{k:20s}{d['n']:5d}{d['p25']:+9.3f}{d['median']:+10.3f}"
                  f"{d['p75']:+9.3f}{d['p75'] - d['p25']:8.3f}{auc:>12s}{p:>11s}",
                  flush=True)

    med = {k: payload["per_rung"][k]["median"] for k in order}
    pred_seq = [med[k] for k in PREDICTABILITY]
    rises = sum(1 for a, b in zip(pred_seq[:-1], pred_seq[1:]) if b > a)
    irr_med = float(np.median([med[k] for k in IRREGULAR]))
    print()
    print(f"predictability ladder monotone rises: {rises}/{len(pred_seq) - 1}")
    print(f"random_walk median {med['random_walk']:+.3f}, "
          f"white_noise median {med['white_noise']:+.3f}")
    print(f"deterministic irregular median of medians {irr_med:+.3f}, "
          f"ett_real {med['ett_real']:+.3f}")
    verdict = ("B, structural familiarity" if irr_med > med["ar_030"]
               else "A, predictability" if irr_med < med["ett_real"] + 0.05
               else "neither cleanly")
    print(f"hypothesis favoured by the irregular ladder: {verdict}")

    (ROOT / "results" / "ladder.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8")
    print("___LADDER_DONE___", flush=True)


if __name__ == "__main__":
    main()
