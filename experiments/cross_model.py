"""Does the level uncertainty effect track the backend's normalisation?

The proposed mechanism is that instance normalisation hides the absolute level
from the model, so its ability to locate the end of a window depends on whether
the whole window statistics carry information about that end. A sine has it,
white noise has it, a random walk does not. If that is the mechanism rather
than a correlation, backends that normalise differently should show the effect
with different strength.

What this repository can and cannot establish about normalisation:

  surrogate   confirmed, `backends/surrogate.py` calls `instance_norm` on the
              context explicitly before every forward pass
  timesfm     confirmed at the call site, `normalize_inputs=True` is passed to
              the forecast entry point, the internal scheme is the library's
  chronos     not confirmed here. The adapter passes the raw context and any
              scaling happens inside the pipeline. The published description is
              a mean scaling step, but nothing in this repository verifies it,
              so it is recorded as unconfirmed rather than asserted
  moment      not confirmed here, no normalisation appears in the adapter

Caveat on the measurement itself. `model_disagree` is one of the fourteen
behavioural signals and it is identically zero for a single model pool, so this
comparison is over the other thirteen. That weakens every single model number
equally and does not favour any backend, but it means these values are not
comparable with the multi backend runs elsewhere.

Usage:
    python -u experiments/cross_model.py --device cuda
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

from level_2x2 import CELLS, build  # noqa: E402
from stratum_risk import mann_whitney  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import make_pool  # noqa: E402

#: One entry per backend, with what this repository can actually confirm about
#: its input normalisation.
BACKENDS = [
    ("chronos-bolt-base", "chronos:amazon/chronos-bolt-base", "unconfirmed"),
    ("chronos-bolt-small", "chronos:amazon/chronos-bolt-small", "unconfirmed"),
    ("timesfm-2.5-200m", "timesfm:google/timesfm-2.5-200m-pytorch", "confirmed at call site"),
    ("surrogate", "surrogate:0", "confirmed, explicit instance_norm"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    windows = build()
    keep = set(CELLS)
    windows = [w for w in windows if w.stratum in keep or w.stratum == "ett_real"]
    print(f"{len(windows)} windows over {len(keep) + 1} conditions", flush=True)

    out = {"note": "single model pools, model_disagree is identically zero",
           "backends": {}}
    for name, spec, norm_status in BACKENDS:
        try:
            models = make_pool([spec], device=args.device)
        except Exception as exc:
            print(f"{name}: backend unavailable, {exc}", flush=True)
            out["backends"][name] = {"error": str(exc), "normalisation": norm_status}
            continue
        agent = IntroActAgent(models, AgentConfig())
        t0 = time.time()
        states = agent.perceive(windows)
        elapsed = time.time() - t0

        by = {}
        for w, s in zip(windows, states):
            by.setdefault(w.stratum, []).append(float(s.behav_risk))

        med = {k: float(np.median(v)) for k, v in by.items()}
        # The effect size this experiment is about: how much a wandering level
        # raises risk when the local shape is held fixed.
        pair = mann_whitney(by["sine_on_walk"], by["sine_on_ramp"])
        gap = med["sine_on_walk"] - med["sine_anchored"]
        out["backends"][name] = {
            "normalisation": norm_status,
            "seconds": elapsed,
            "medians": med,
            "walk_minus_anchored": gap,
            "walk_vs_ramp": pair,
        }
        print(f"{name:20s} norm={norm_status:28s} {elapsed:5.0f}s  "
              f"walk-anchored {gap:+.3f}  walk vs ramp auc {pair['auc']:.3f} "
              f"p {pair['p']:.2e}", flush=True)

    print()
    print(f"{'backend':20s}{'sine_anch':>11s}{'sine_walk':>11s}{'sine_ramp':>11s}"
          f"{'walk_only':>11s}{'noise_anch':>12s}{'ett_real':>10s}")
    for name, res in out["backends"].items():
        if "medians" not in res:
            continue
        m = res["medians"]
        print(f"{name:20s}{m['sine_anchored']:+11.3f}{m['sine_on_walk']:+11.3f}"
              f"{m['sine_on_ramp']:+11.3f}{m['walk_only']:+11.3f}"
              f"{m['noise_anchored']:+12.3f}{m['ett_real']:+10.3f}")

    (ROOT / "results" / "cross_model.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")
    print("___CROSS_MODEL_DONE___", flush=True)


if __name__ == "__main__":
    main()
