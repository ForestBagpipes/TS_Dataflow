"""Does the flattening failure need the synthetic shapes too?

The perception pass established that behavioural risk does not invert on real
cross domain data. It leaves open the other half of the question. Ten synthetic
out of distribution windows were flattened by DESPIKE, nine percent of their
points edited and ninety six percent of their variance removed, and if that
also needs the synthetic shapes then the failure is a property of the
construction rather than of the method.

This runs the full curation loop on a corpus holding both kinds and reports,
per stratum, how many windows were edited and how much spread survived.
"""

import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from corpus import CorpusSpec, build_corpus  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    spec = CorpusSpec(
        n_contaminated=350, n_clean=200, n_hard=100, n_rare_valid=100,
        n_changepoint=100, n_clean_ood=150, n_real_ood=150, seed=42,
    )
    wins = build_corpus(spec, source="ett")
    models = make_pool(PRESETS["multi-family"]["curation"], device=args.device)
    agent = IntroActAgent(models, AgentConfig())

    t0 = time.time()
    states = agent.perceive(wins)
    print(f"perceive {time.time() - t0:.0f}s", flush=True)
    t0 = time.time()
    traces = [agent.curate_window(w, s, peer_idx=i)
              for i, (w, s) in enumerate(zip(wins, states))]
    print(f"curate {time.time() - t0:.0f}s", flush=True)

    out = {}
    for w, t in zip(wins, traces):
        d = out.setdefault(w.stratum, {"n": 0, "mod": 0, "du": [], "var": [],
                                       "acc": Counter()})
        d["n"] += 1
        if not t.modified:
            continue
        d["mod"] += 1
        d["du"].append(float(t.final_utility - t.initial_utility))
        for action in t.accepted_actions:
            d["acc"][str(action).split(".")[-1]] += 1
        sb = float(np.std(w.series))
        sa = float(np.std(t.final_series))
        d["var"].append(sa / max(sb, 1e-9))

    header = ("stratum".ljust(14) + "n".rjust(5) + "mod".rjust(5)
              + "mod%".rjust(7) + "mean du".rjust(10) + "min var".rjust(9)
              + "  accepted")
    print()
    print(header, flush=True)
    for k in sorted(out):
        d = out[k]
        mv = min(d["var"]) if d["var"] else float("nan")
        du = float(np.mean(d["du"])) if d["du"] else 0.0
        print(f"{k:14s}{d['n']:5d}{d['mod']:5d}{100 * d['mod'] / d['n']:7.1f}"
              f"{du:10.2f}{mv:9.3f}  {dict(d['acc'])}", flush=True)

    flat = [(k, r) for k, d in out.items() for r in d["var"] if r < 0.5]
    print()
    print(f"edits removing more than half the variance: {len(flat)}", flush=True)
    print(f"by stratum: {dict(Counter(k for k, _ in flat))}", flush=True)

    payload = {k: {"n": d["n"], "mod": d["mod"], "du": d["du"],
                   "var": d["var"], "acc": dict(d["acc"])}
               for k, d in out.items()}
    (ROOT / "results" / "ood_curate.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8")
    print("___OOD_CURATE_DONE___", flush=True)


if __name__ == "__main__":
    main()
