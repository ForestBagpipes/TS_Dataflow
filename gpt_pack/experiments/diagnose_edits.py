"""Which edits changed between the two arms, and why the ones that did not.

Two things need explaining after the tau 0.02 comparison.

The spread term vetoed 10 of 10 flattening edits when replayed against the 2000
window traces, and it vetoed none of the 5 on the 800 window corpus. Either
those 5 are a different phenomenon or the term is not doing what the replay
said it does.

Repair fell by 0.0375 and the edit count fell from 80 to 71. Nine edits went
away and the question is whether they were concentrated or spread out, because
a concentrated loss is a bug and a diffuse one is a design tradeoff.

This records, per window, the operator, the spread ratio, the structural
distance and the verdict, on both arms.
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from audit import _nmse  # noqa: E402
from corpus import CorpusSpec, build_corpus  # noqa: E402
from fix_compare import set_arm  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.verify import VerifyConfig  # noqa: E402


def collect(agent, windows, states):
    rows = []
    for i, (w, s) in enumerate(zip(windows, states)):
        t = agent.curate_window(w, s, peer_idx=i)
        acc = [str(r.action).split(".")[-1] for r in t.records if r.accepted]
        vr = float("nan")
        if t.modified and np.isfinite(w.series).all():
            vr = float(np.std(t.final_series)) / max(float(np.std(w.series)), 1e-9)
        rep = None
        if w.clean_series is not None:
            ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))
            rep = {
                "before": _nmse(w.series, w.clean_series, ref_var),
                "after": _nmse(t.final_series, w.clean_series[t.crop_offset:], ref_var),
            }
        rows.append({
            "window_id": w.window_id, "stratum": w.stratum,
            "contamination": w.contamination, "modified": bool(t.modified),
            "accepted": acc, "var_ratio": vr, "crop_offset": int(t.crop_offset),
            "spread_parts": [float(r.struct_parts.get("spread", float("nan")))
                             for r in t.records if r.accepted],
            "distortions": [float(r.struct_distortion) for r in t.records if r.accepted],
            "nmse": rep,
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--tau", type=float, default=0.02)
    args = ap.parse_args()

    n = args.n
    spec = CorpusSpec(
        n_contaminated=int(n * 0.35), n_clean=int(n * 0.20),
        n_hard=int(n * 0.1125), n_rare_valid=int(n * 0.1125),
        n_changepoint=int(n * 0.1125), n_clean_ood=int(n * 0.1125), seed=42,
    )
    windows = build_corpus(spec, source="ett")
    models = make_pool(PRESETS["multi-family"]["curation"], device=args.device)
    print(f"{len(windows)} windows, tau {args.tau}", flush=True)

    arms = {}
    for label, enabled in [("before", False), ("after", True)]:
        set_arm(enabled)
        agent = IntroActAgent(
            models, AgentConfig(verification=VerifyConfig(tau=args.tau)))
        t0 = time.time()
        states = agent.perceive(windows)
        arms[label] = collect(agent, windows, states)
        print(f"  {label} {time.time() - t0:.0f}s", flush=True)

    b = {r["window_id"]: r for r in arms["before"]}
    a = {r["window_id"]: r for r in arms["after"]}

    print("\n== the destructive edits on clean_ood, what operator made them ==")
    for label, rows in [("before", b), ("after", a)]:
        d = [r for r in rows.values()
             if r["stratum"] == "clean_ood" and np.isfinite(r["var_ratio"])
             and r["var_ratio"] < 0.5]
        print(f"  {label}: {len(d)}")
        for r in d:
            sp = ", ".join(f"{x:.3f}" for x in r["spread_parts"])
            ds = ", ".join(f"{x:.4f}" for x in r["distortions"])
            print(f"    wid {r['window_id']:4d} var {r['var_ratio']:.3f} "
                  f"crop {r['crop_offset']:3d} ops {r['accepted']} "
                  f"spread [{sp}] D [{ds}]")

    print("\n== the 9 edits that disappeared ==")
    lost = [w for w in b if b[w]["modified"] and not a[w]["modified"]]
    gained = [w for w in b if not b[w]["modified"] and a[w]["modified"]]
    print(f"  lost {len(lost)}, gained {len(gained)}")
    print(f"  lost by stratum: {Counter(b[w]['stratum'] for w in lost)}")
    print(f"  lost by operator: {Counter(op for w in lost for op in b[w]['accepted'])}")
    print(f"  lost by contamination: "
          f"{Counter(b[w]['contamination'] for w in lost if b[w]['contamination'])}")

    print("\n  repair each lost edit had been providing, contaminated only:")
    deltas = []
    for w in lost:
        r = b[w]
        if r["stratum"] != "contaminated" or not r["nmse"]:
            continue
        gain = r["nmse"]["before"] - r["nmse"]["after"]
        deltas.append((gain, w, r["contamination"], r["accepted"]))
    for g, w, c, ops in sorted(deltas, reverse=True):
        print(f"    wid {w:4d} {c:18s} nmse gain {g:+.4f} ops {ops}")
    if deltas:
        gs = [g for g, *_ in deltas]
        print(f"  total nmse gain given up {sum(gs):+.4f}, "
              f"median {np.median(gs):+.4f}, max {max(gs):+.4f}")
        print(f"  concentration: top edit is "
              f"{100 * max(gs) / max(sum(gs), 1e-9):.0f} percent of the loss")

    (ROOT / "results" / "diagnose_edits.json").write_text(
        json.dumps(arms, indent=1, default=float), encoding="utf-8")
    print("___DIAGNOSE_EDITS_DONE___", flush=True)


if __name__ == "__main__":
    main()
