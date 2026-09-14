"""Replay every rolled back candidate and measure what committing it would cost.

`experiments/shield_conservatism.py` asks the same question through the utility
change, and that proxy fails on exactly the data the question matters for:
section 2.2 shows the model's utility reading disagrees with fidelity on clean
but unfamiliar windows. This file answers it directly. Each rejected candidate is
executed again on its window and the distance to the clean reference is measured
before and after.

    closer   the candidate would have improved the window. The shield refused a
             real repair, and that is what its caution costs
    further  the candidate would have damaged it. That is what the shield is for

The ratio of the first to the total is the number the paper needs when it puts
`introact` beside `spec_veto`, since the two sit close on damage and apart on
repair and the question is whether the gap is caution or waste.

**Why the replay reproduces the candidate.** The trace stores each candidate's
operator and the parameter dictionary the operator returned, which is filled in
after execution rather than before: `IMPUTE` records the period and the fill
count it actually used, `DESPIKE` records `n_sigma` and how many points it
replaced, `RESEGMENT` records the exact `lo` and `hi` it cut to. Re applying the
operator with those values is deterministic and reproduces the same series.

**The limitation, and it is larger than it first looked.** The replay applies
the candidate to the window as the corpus holds it, that is to the state before
any edit in that window was committed, whereas the candidate originally ran
against whatever the working copy had become. Where an earlier candidate was
accepted, the defect it repaired is still present in the replay's input.

That is not a rare corner. Measured on the xl traces, 449 of 1157 rolled back
candidates come back reporting nothing to do, 444 of them `IMPUTE` finding
nothing to fill and 5 `DESPIKE` finding no spike, because the defect they were
proposed for had already been repaired by an accepted edit earlier in the same
window. Those are counted as **superseded** rather than failed, since nothing
went wrong: the replay is asking about a defect that is absent from its input.

Genuine failures are 39, all RESEGMENT declining because the cut would discard
too much of the window.

The consequence for the result is that the replayable set is biased away from
imputation on windows that had already been repaired once. That is stated with
the number rather than folded into a single failure count.

No GPU, no model, no API. Pure numpy over the stored actions.

Usage:
    python -u experiments/shield_replay.py \
        --traces results/xl/xl_ett_multi-family_seed42_traces.json \
        --arm introact_full --scale xl --source ett
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from corpus import build_corpus  # noqa: E402
from run_agent import SCALES  # noqa: E402

from introact_ts.actions import apply_action  # noqa: E402
from introact_ts.types import Action  # noqa: E402

ROLLED_BACK = ("ROLLED_BACK_UTILITY", "ROLLED_BACK_STRUCTURE",
               "ROLLED_BACK_RISK")

#: Parameter keys the operators report after the fact rather than accept as
#: input. Passing them back in would raise, so they are dropped on replay.
REPORTED_ONLY = {"n_filled", "n_seasonal", "n_seasonal_used", "n_replaced",
                 "removed_std", "n_changepoints", "keep_frac"}


def distance(series, clean, crop=0):
    """Root mean square distance to the clean reference over the shared span."""
    if clean is None:
        return None
    a = np.asarray(series, dtype=np.float64)
    b = np.asarray(clean, dtype=np.float64)[crop:crop + len(a)]
    n = min(len(a), len(b))
    if n == 0:
        return None
    d = a[:n] - b[:n]
    d = d[np.isfinite(d)]
    if d.size == 0:
        return None
    return float(np.sqrt(np.mean(d ** 2)))


def replay_window(window, steps):
    """Every rolled back candidate of one window, replayed.

    Returns one row per candidate plus a flag saying whether an accepted edit
    preceded it, which is the case the replay approximates.
    """
    src = np.asarray(window.series, dtype=np.float64)
    base = distance(src, window.clean_series)
    rows = []
    accepted_before = False
    for s in steps:
        verdict = s["verdict"]
        if verdict == "ACCEPTED":
            accepted_before = True
            continue
        if verdict not in ROLLED_BACK:
            continue
        try:
            action = Action(s["action"])
        except ValueError:
            continue
        params = {k: v for k, v in (s.get("params") or {}).items()
                  if k not in REPORTED_ONLY}
        try:
            out = apply_action(src, action, **params)
        except Exception:
            rows.append({"verdict": verdict, "action": s["action"],
                         "stratum": window.stratum, "replayed": False,
                         "after_accepted": accepted_before})
            continue
        if not out.applicable:
            # An operator that reports nothing to do is not a replay failure.
            # It means the defect this candidate targeted is absent from the
            # replay's input, which is what an earlier accepted edit does.
            note = (out.note or "").lower()
            superseded = ("nothing to fill" in note or "no spikes" in note)
            rows.append({"verdict": verdict, "action": s["action"],
                         "stratum": window.stratum, "replayed": False,
                         "superseded": superseded, "note": out.note,
                         "after_accepted": accepted_before})
            continue
        crop = int(out.params.get("lo", 0)) if action is Action.RESEGMENT else 0
        after = distance(out.series, window.clean_series, crop)
        if base is None or after is None:
            rows.append({"verdict": verdict, "action": s["action"],
                         "stratum": window.stratum, "replayed": False,
                         "after_accepted": accepted_before})
            continue
        rows.append({
            "verdict": verdict, "action": s["action"],
            "stratum": window.stratum, "replayed": True,
            "after_accepted": accepted_before,
            "distance_before": base, "distance_after": after,
            # Negative means the candidate moved the window closer to the truth,
            # so refusing it cost a real repair.
            "delta_distance": after - base,
        })
    return rows


def summarise(rows):
    ok = [r for r in rows if r.get("replayed")]
    superseded = [r for r in rows if not r.get("replayed") and r.get("superseded")]
    failed = [r for r in rows
              if not r.get("replayed") and not r.get("superseded")]
    out = {
        "candidates": len(rows),
        "replayed": len(ok),
        # The defect was already repaired by an earlier accepted edit, so the
        # replay's input no longer contains it. Not a failure.
        "superseded": len(superseded),
        "superseded_by_note": dict(Counter(r.get("note", "") for r in superseded)),
        "replay_failed": len(failed),
        "failed_by_note": dict(Counter(r.get("note", "") for r in failed)),
        "after_accepted_edit": sum(1 for r in ok if r["after_accepted"]),
    }
    if not ok:
        return out
    wrong = [r for r in ok if r["delta_distance"] < 0]
    out["would_have_helped"] = len(wrong)
    out["would_have_harmed"] = len(ok) - len(wrong)
    out["wrongly_refused_rate"] = len(wrong) / len(ok)
    by = defaultdict(list)
    for r in ok:
        by[r["stratum"]].append(r)
    out["by_stratum"] = {
        s: {"n": len(v),
            "would_have_helped": sum(1 for r in v if r["delta_distance"] < 0),
            "wrongly_refused_rate":
                sum(1 for r in v if r["delta_distance"] < 0) / len(v),
            "median_delta": float(np.median([r["delta_distance"] for r in v]))}
        for s, v in sorted(by.items())}
    by_a = defaultdict(list)
    for r in ok:
        by_a[r["action"]].append(r)
    out["by_action"] = {
        a: {"n": len(v),
            "would_have_helped": sum(1 for r in v if r["delta_distance"] < 0),
            "wrongly_refused_rate":
                sum(1 for r in v if r["delta_distance"] < 0) / len(v)}
        for a, v in sorted(by_a.items())}
    return out


def load_traces(path, arm):
    """Traces from either the JSONL the main run flushes or the older JSON.

    The JSONL is one record per window with an `arm` field, written line by line
    so an interrupted run keeps what it flushed. The older format is one JSON
    document keyed by arm. Both are read here because the ett run that produced
    the first version of this measurement is in the older one and is kept for
    comparison, while every number that goes in the paper comes from the newer.
    """
    p = Path(path)
    if p.suffix == ".jsonl":
        out = []
        for line in p.open(encoding="utf-8"):
            r = json.loads(line)
            if r.get("arm") == arm:
                out.append(r)
        return out
    blob = json.loads(p.read_text(encoding="utf-8"))
    return blob[arm] if arm in blob else blob


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces", required=True)
    ap.add_argument("--arm", default="introact")
    ap.add_argument("--scale", default="xl", choices=list(SCALES))
    #: The paper's corpus. The first version of this measurement ran on `ett`,
    #: whose windows are all transformer telemetry, and a number measured there
    #: cannot be quoted in a section whose table is on `mixed`. That is the same
    #: mistake the repair distance column made, see `docs/number_selfchecks.md`.
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT / "results" / "shield_replay.json"))
    args = ap.parse_args()

    spec = SCALES[args.scale]
    spec.seed = args.seed
    windows = {w.window_id: w for w in build_corpus(spec, source=args.source)}
    traces = load_traces(args.traces, args.arm)
    print(f"{len(windows)} windows, {len(traces)} traces, "
          f"source {args.source}, seed {args.seed}", flush=True)

    rows = []
    missing = 0
    for t in traces:
        w = windows.get(int(t["window_id"]))
        if w is None:
            missing += 1
            continue
        rows.extend(replay_window(w, t.get("steps") or []))

    rep = summarise(rows)
    rep["windows_not_in_corpus"] = missing
    rep["arm"] = args.arm
    rep["traces"] = str(args.traces)

    print(f"candidates {rep['candidates']}, replayed {rep['replayed']}, "
          f"superseded by an earlier accepted edit {rep['superseded']}, "
          f"genuinely failed {rep['replay_failed']}")
    for note, n in rep["failed_by_note"].items():
        print(f"    failed: {n:5d}  {note}")
    if rep.get("replayed"):
        print(f"wrongly refused {rep['would_have_helped']} of {rep['replayed']} "
              f"({rep['wrongly_refused_rate']:.3f})")
        print()
        print("by stratum")
        for s, d in rep["by_stratum"].items():
            print(f"  {s:16s} n={d['n']:5d}  wrongly refused {d['wrongly_refused_rate']:.3f}"
                  f"  median delta {d['median_delta']:+.4f}")
        print()
        print("by operator")
        for a, d in rep["by_action"].items():
            print(f"  {a:12s} n={d['n']:5d}  wrongly refused {d['wrongly_refused_rate']:.3f}")

    Path(args.out).write_text(json.dumps(rep, indent=1, default=float),
                              encoding="utf-8")
    print("___SHIELD_REPLAY_DONE___", flush=True)


if __name__ == "__main__":
    main()
