"""What the successful repairs have in common, read off the runs already done.

The question DATE's rule discovery poses in our setting: **is there a repair
recipe that belongs to a subpopulation rather than to a window.** If windows
that look alike succeed with the same operator, a policy over subpopulations
has something to learn, and it has hundreds of windows per cluster to learn it
from rather than the zero or one candidate a single window offers.

This reads the flushed traces and answers three things, none of which needs a
GPU or a rerun:

  what succeeded   per stratum and contamination kind, which operator was
                   committed and how often
  what it earned   the distance improvement those commits produced, so a
                   frequent operator that helps little is separable from a rare
                   one that helps a lot
  how concentrated it is  the share of one group's commits that go to its single
                   most common operator. A group whose commits are spread evenly
                   across operators has no recipe to learn

**Why the grouping here is by stratum and contamination rather than by profile
cluster.** The cluster label is assigned inside a run and is not written to the
trace, so it cannot be recovered offline. Stratum and contamination kind are
recorded, they partition the corpus the same way the injection protocol does,
and a recipe that is not visible across them is unlikely to be visible across a
clustering of the same windows. If a recipe does show up here, the cluster level
version is worth computing inside a run, which costs a GPU pass.

Usage:
    python experiments/extract_trajectories.py --results results/xl \
        --arm f_full --seeds 0,1,2
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent

ARMS = ("IMPUTE", "DESPIKE", "DENOISE", "RESEGMENT")


def load(results_dir, arm, seeds, pattern):
    rows = []
    for s in seeds:
        p = Path(results_dir) / pattern.format(seed=s)
        if not p.exists():
            print(f"  absent, skipped: {p.name}")
            continue
        for line in p.open(encoding="utf-8"):
            r = json.loads(line)
            if r.get("arm") == arm:
                r["seed"] = s
                rows.append(r)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "results" / "xl"))
    ap.add_argument("--arm", default="f_full")
    ap.add_argument("--pattern", default="ablation_f_full_seed{seed}_traces.jsonl")
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--out", default=str(ROOT / "results" / "trajectory_patterns.json"))
    args = ap.parse_args()

    seeds = [int(x) for x in args.seeds.replace(" ", "").split(",") if x]
    rows = load(args.results, args.arm, seeds, args.pattern)
    print(f"{len(rows)} window traces, arm {args.arm}, seeds {seeds}")

    # Every committed edit, with what it earned.
    commits = []
    attempts = []
    for r in rows:
        gain = None
        if r["dist_before"] is not None and r["dist_after"] is not None:
            gain = r["dist_before"] - r["dist_after"]
        for st in r["steps"]:
            if st["action"] not in ARMS:
                continue
            rec = {"stratum": r["stratum"],
                   "contamination": r["contamination"] or "none",
                   "action": st["action"], "verdict": st["verdict"],
                   "delta_utility": st["delta_utility"],
                   "struct_distortion": st["struct_distortion"],
                   "window_gain": gain, "seed": r["seed"]}
            attempts.append(rec)
            if st["verdict"] == "ACCEPTED":
                commits.append(rec)
    print(f"{len(attempts)} operator attempts, {len(commits)} committed")

    # Group by the two labels the trace carries.
    def report(key, label):
        print()
        print(f"committed operators by {label}")
        print(f"{label:20s}{'commits':>9s}{'top operator':>14s}{'share':>8s}"
              f"{'mean gain':>11s}{'entropy':>9s}")
        out = {}
        groups = defaultdict(list)
        for c in commits:
            groups[c[key]].append(c)
        for g in sorted(groups):
            sub = groups[g]
            cnt = Counter(c["action"] for c in sub)
            top, n_top = cnt.most_common(1)[0]
            share = n_top / len(sub)
            gains = [c["window_gain"] for c in sub if c["window_gain"] is not None]
            p = np.array([v / len(sub) for v in cnt.values()], dtype=np.float64)
            ent = float(-(p * np.log2(p)).sum()) if len(p) > 1 else 0.0
            out[g] = {"commits": len(sub), "top_operator": top,
                      "top_share": share, "counts": dict(cnt),
                      "mean_gain": float(np.mean(gains)) if gains else None,
                      "entropy_bits": ent}
            print(f"{str(g):20s}{len(sub):9d}{top:>14s}{share:8.3f}"
                  f"{(np.mean(gains) if gains else float('nan')):11.4f}"
                  f"{ent:9.3f}")
        return out

    by_contam = report("contamination", "contamination")
    by_stratum = report("stratum", "stratum")

    # Acceptance rate per group and operator, which is the quantity a recipe
    # would have to differ on.
    print()
    print("acceptance rate by contamination kind and operator")
    kinds = sorted({a["contamination"] for a in attempts})
    print(f"{'contamination':20s}" + "".join(f"{a[:9]:>11s}" for a in ARMS))
    rates = {}
    for k in kinds:
        sub = [a for a in attempts if a["contamination"] == k]
        row = {}
        for op in ARMS:
            tried = [a for a in sub if a["action"] == op]
            acc = sum(1 for a in tried if a["verdict"] == "ACCEPTED")
            row[op] = acc / len(tried) if tried else None
        rates[k] = row
        print(f"{k:20s}" + "".join(
            f"{row[op]:11.3f}" if row[op] is not None else f"{'-':>11s}"
            for op in ARMS))

    # Is the best operator the same everywhere. If it is, there is no recipe to
    # learn, only one global rule.
    best = {}
    for k, row in rates.items():
        ok = {op: v for op, v in row.items() if v is not None}
        best[k] = max(ok, key=ok.get) if ok else None
    distinct = sorted({v for v in best.values() if v})
    print()
    print(f"best operator per contamination kind: {best}")
    print(f"distinct answers across kinds: {len(distinct)}  {distinct}")
    print("a single answer everywhere means one global rule suffices and a "
          "per group policy has nothing to add")

    Path(args.out).write_text(json.dumps(
        {"arm": args.arm, "seeds": seeds, "n_traces": len(rows),
         "n_attempts": len(attempts), "n_commits": len(commits),
         "by_contamination": by_contam, "by_stratum": by_stratum,
         "acceptance_rates": rates, "best_operator": best}, indent=1,
        default=float), encoding="utf-8")
    print()
    print("___TRAJECTORY_PATTERNS_DONE___")


if __name__ == "__main__":
    main()
