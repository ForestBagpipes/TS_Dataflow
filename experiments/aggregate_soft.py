"""The soft penalty sweep, aggregated, and theorem 2's lower bound tested on it.

Experiment one's second sub table. The competing design puts structural
preservation in the objective as a weighted penalty, ours puts it in a veto.
Theorem 2 says the first has a positive lower bound on damage that no choice of
weight removes, unless the weight is raised until almost nothing is accepted.
This file states what the sweep measured and checks that claim in the only form
that can refute it.

**The comparison that decides it is not the damage column alone.** A large
enough weight refuses nearly every edit, and an arm that edits nothing damages
nothing, so a soft arm can always reach a low damage rate by ceasing to repair.
The question theorem 2 poses is whether it can reach our damage rate **while
repairing as well**. So every weight is placed on both axes and the frontier is
read off, rather than the minimum of one column being reported as if it settled
anything.

Two readings are given because they answer different questions.

  at equal damage    the best repair any weight achieves without exceeding our
                     damage rate. This is the frontier comparison
  at equal repair    the lowest damage any weight achieves without repairing
                     worse than we do. The mirror of the same question

The nRMSD used here is the headline from `nrmsd_by_contamination.py`, the window
count weighted mean over the five sound contamination kinds, because the plain
mean is 62 percent one subgroup and the two missing kinds score an arm that
repairs nothing at zero. Reading a frontier off the plain mean would reward the
high weight end for the wrong reason, which is exactly the confound this
comparison is about.

Usage:
    python experiments/aggregate_soft.py --results results/xl
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent

UNSOUND_KINDS = ("missing_block", "missing_scattered")
PROTECTED = ("clean", "hard", "rare_valid", "changepoint")


def sound_nrmsd(trace_path, arm):
    """Window count weighted mean nRMSD over the sound contamination kinds."""
    vals = []
    p = Path(trace_path)
    if not p.exists():
        return None
    for line in p.open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("arm") != arm or r.get("stratum") != "contaminated":
            continue
        if r.get("contamination") in UNSOUND_KINDS:
            continue
        v = r.get("nrmsd_after")
        if v is not None:
            vals.append(float(v))
    return float(np.mean(vals)) if vals else None


def recount(trace_path, arm):
    """Edits and mis edit rate straight from the traces, for check four."""
    p = Path(trace_path)
    if not p.exists():
        return None
    edits = prot = mis = 0
    for line in p.open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("arm") != arm:
            continue
        if r["modified"]:
            if r["dist_before"] is not None:
                edits += 1
        if r["stratum"] in PROTECTED:
            prot += 1
            if r["modified"]:
                mis += 1
    return {"edits": edits, "mis_rate": mis / prot if prot else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "results" / "xl"))
    ap.add_argument("--seeds", default="0,1,2")
    #: The row this is compared against, from the ablation ladder's reference.
    ap.add_argument("--ours-damage", type=float, default=0.1306)
    ap.add_argument("--ours-damage-std", type=float, default=0.0084)
    ap.add_argument("--out", default=str(ROOT / "results" / "soft_sweep_agg.json"))
    args = ap.parse_args()

    seeds = [int(s) for s in args.seeds.replace(" ", "").split(",") if s]
    files = sorted(Path(args.results).glob("soft_mu*_seed*.json"))
    by_mu = defaultdict(dict)
    for f in files:
        blob = json.loads(f.read_text(encoding="utf-8"))
        s = int(blob["seed"])
        if s in seeds:
            by_mu[float(blob["soft_mu"])][s] = (blob, f)
    mus = sorted(by_mu)
    print(f"{len(files)} result files, {len(mus)} weights, seeds {seeds}")

    # Our reference row's sound nRMSD, from the ablation's full method traces.
    ours_nrmsd = []
    for s in seeds:
        v = sound_nrmsd(Path(args.results) / f"ablation_f_full_seed{s}_traces.jsonl",
                        "f_full")
        if v is not None:
            ours_nrmsd.append(v)
    ours_n = float(np.mean(ours_nrmsd)) if ours_nrmsd else None
    if ours_n is None:
        print("the full method's traces are absent, the frontier cannot be "
              "placed against ours")

    rows = []
    print()
    print(f"{'mu':>7s}{'edits':>14s}{'mis edit rate':>20s}{'damage rate':>20s}"
          f"{'nRMSD sound':>20s}")
    for mu in mus:
        got = by_mu[mu]
        if len(got) != len(seeds):
            print(f"{mu:7g}  only {sorted(got)} present, skipped")
            continue
        def col(k):
            a = np.asarray([got[s][0][k] for s in seeds], dtype=np.float64)
            return {"mean": float(a.mean()),
                    "std": float(a.std(ddof=1)) if len(a) > 1 else 0.0,
                    "values": [float(x) for x in a]}
        ns = []
        for s in seeds:
            tp = Path(args.results) / f"soft_mu{mu:g}_seed{s}_traces.jsonl"
            v = sound_nrmsd(tp, f"soft_mu{mu:g}")
            if v is not None:
                ns.append(v)
        rec = {"mu": mu,
               "committed_edits": col("committed_edits"),
               "protected_mis_edit_rate": col("protected_mis_edit_rate"),
               "damage_rate": col("damage_rate"),
               "nrmsd_sound": ({"mean": float(np.mean(ns)),
                                "std": float(np.std(ns, ddof=1)) if len(ns) > 1
                                else 0.0, "values": ns} if ns else None)}
        rows.append(rec)
        ns_txt = (f"{rec['nrmsd_sound']['mean']:9.4f}+-{rec['nrmsd_sound']['std']:.4f}"
                  if rec["nrmsd_sound"] else f"{'n/a':>20s}")
        print(f"{mu:7g}{rec['committed_edits']['mean']:9.0f}+-"
              f"{rec['committed_edits']['std']:.0f}"
              f"{rec['protected_mis_edit_rate']['mean']:13.4f}+-"
              f"{rec['protected_mis_edit_rate']['std']:.4f}"
              f"{rec['damage_rate']['mean']:13.4f}+-"
              f"{rec['damage_rate']['std']:.4f}{ns_txt}")

    print()
    print(f"ours, the full method: damage {args.ours_damage:.4f} "
          f"+- {args.ours_damage_std:.4f}"
          + (f", nRMSD sound {ours_n:.4f}" if ours_n else ""))

    # Reading one. Can any weight match our damage, and what does it repair
    # when it does.
    at_damage = [r for r in rows
                 if r["damage_rate"]["mean"] <= args.ours_damage + 1e-12]
    print()
    print("weights whose damage rate is at or below ours")
    if not at_damage:
        best = min(rows, key=lambda r: r["damage_rate"]["mean"])
        print(f"  none. The lowest the sweep reaches is {best['damage_rate']['mean']:.4f} "
              f"at mu {best['mu']:g}, against ours at {args.ours_damage:.4f}")
    else:
        for r in at_damage:
            n = r["nrmsd_sound"]["mean"] if r["nrmsd_sound"] else float("nan")
            worse = ((n - ours_n) if ours_n else float("nan"))
            print(f"  mu {r['mu']:g}: damage {r['damage_rate']['mean']:.4f}, "
                  f"edits {r['committed_edits']['mean']:.0f}, "
                  f"nRMSD {n:.4f}, which is {worse:+.4f} against ours")

    # Reading two. Among weights that repair at least as well as we do, how low
    # does damage go.
    if ours_n is not None:
        ok = [r for r in rows
              if r["nrmsd_sound"] and r["nrmsd_sound"]["mean"] <= ours_n + 1e-12]
        print()
        print("weights that repair at least as well as ours")
        if not ok:
            print("  none")
        else:
            b = min(ok, key=lambda r: r["damage_rate"]["mean"])
            print(f"  best damage among them {b['damage_rate']['mean']:.4f} at "
                  f"mu {b['mu']:g}, against ours {args.ours_damage:.4f}")

    # Check four, the cross reconciliation.
    print()
    print("cross reconciliation against the traces")
    bad = 0
    total = 0
    for mu in mus:
        for s in seeds:
            if s not in by_mu[mu]:
                continue
            blob, _ = by_mu[mu][s]
            got = recount(Path(args.results) /
                          f"soft_mu{mu:g}_seed{s}_traces.jsonl", f"soft_mu{mu:g}")
            if got is None:
                continue
            total += 1
            ok = (got["edits"] == blob["committed_edits"]
                  and abs(got["mis_rate"] - blob["protected_mis_edit_rate"]) < 1e-9)
            if not ok:
                bad += 1
                print(f"  mu {mu:g} seed {s} differs: edits "
                      f"{blob['committed_edits']} against {got['edits']}, "
                      f"mis {blob['protected_mis_edit_rate']:.4f} against "
                      f"{got['mis_rate']:.4f}")
    print(f"  {total - bad} of {total} agree")

    Path(args.out).write_text(json.dumps(
        {"rows": rows, "ours_damage": args.ours_damage,
         "ours_nrmsd_sound": ours_n, "seeds": seeds}, indent=1, default=float),
        encoding="utf-8")
    print()
    print("___SOFT_AGG_DONE___")


if __name__ == "__main__":
    main()
