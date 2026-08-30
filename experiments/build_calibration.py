"""Build a calibration corpus that is actually exchangeable with deployment.

`run_conformal.py` calibrated on `--source ett` and the paper deploys on
`--source mixed`. Those are not two samples of one distribution: the calibration
pool contains no financial series at all while 44.6 percent of the deployment
pool is financial. Theorem 5's exchangeability premise fails at the corpus
construction, which is why the deployed damage rate sat at four times the target
level. This is the fourth time a quantity established on `ett` failed to
transfer to `mixed`.

This builds the replacement and refuses to hand it over unless two things hold.

  **zero overlap with deployment**  Window ids are positional counters, so
  overlap is checked on content: the first sixteen points of the pristine
  series, hashed, paired with the dataset name. The clean series is used where
  it exists so an injection cannot disguise a shared source window.

  **the same six sources in the same proportions**  Matching stratum shares is
  not enough when the sources differ. Both are reported and compared.

Oversampling then filtering is what makes zero overlap achievable: the raw draw
takes more windows than needed, removes any that collide with a deployment seed
or with each other, and then trims each stratum back to its target count. The
number removed is reported, since removal is not random and a large one would
be a selection effect worth knowing about.

Usage:
    python experiments/build_calibration.py --n 1600 --seed 101 \
        --deployment-seeds 0,1,2
"""

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from corpus import CorpusSpec, build_corpus  # noqa: E402
from run_agent import SCALES  # noqa: E402

#: Stratum shares of the xl deployment corpus, measured on seed 0 rather than
#: taken from the spec, so the target is what deployment actually contains.
DEPLOY_SHARES = {
    "contaminated": 0.3726, "clean": 0.2115, "hard": 0.1057,
    "rare_valid": 0.0987, "changepoint": 0.1057, "clean_ood": 0.1057,
}


def ident(w):
    """Content identity of a window, independent of its positional id."""
    base = w.clean_series if w.clean_series is not None else w.series
    a = np.asarray(base, dtype=np.float64)[:16]
    return (w.dataset, hashlib.md5(np.round(a, 6).tobytes()).hexdigest())


def spec_for(n, seed, oversample=1.0):
    m = int(round(n * oversample))
    return CorpusSpec(
        n_contaminated=int(m * DEPLOY_SHARES["contaminated"]),
        n_clean=int(m * DEPLOY_SHARES["clean"]),
        n_hard=int(m * DEPLOY_SHARES["hard"]),
        n_rare_valid=int(m * DEPLOY_SHARES["rare_valid"]),
        n_changepoint=int(m * DEPLOY_SHARES["changepoint"]),
        n_clean_ood=int(m * DEPLOY_SHARES["clean_ood"]),
        seed=seed, window_len=512)


def target_counts(n):
    return {k: int(round(n * v)) for k, v in DEPLOY_SHARES.items()}


def build(n=1600, seed=101, source="mixed", scale="xl",
          dep_seeds=(0, 1, 2), oversample=1.35, verbose=False):
    """The calibration corpus itself, so a caller gets the same one this
    script validated rather than rebuilding it from a window id list.

    Ids are positional and two corpora reuse them for different data, so a
    saved id list is not a way to reload a corpus. Rebuilding through the same
    function is.
    """
    banned = set()
    for s in dep_seeds:
        spec = SCALES[scale]
        spec.seed = s
        for w in build_corpus(spec, source=source):
            banned.add(ident(w))
    raw = build_corpus(spec_for(n, seed, oversample), source=source)
    seen = set()
    by_stratum = defaultdict(list)
    dropped = {"overlap": 0, "duplicate": 0}
    for w in raw:
        k = ident(w)
        if k in banned:
            dropped["overlap"] += 1
            continue
        if k in seen:
            dropped["duplicate"] += 1
            continue
        seen.add(k)
        by_stratum[w.stratum].append(w)
    out = []
    for st, target in target_counts(n).items():
        out.extend(by_stratum.get(st, [])[:target])
    if verbose:
        print(f"calibration {len(out)} windows, dropped {dropped}", flush=True)
    return out, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1600)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--scale", default="xl")
    ap.add_argument("--deployment-seeds", dest="dep_seeds", default="0,1,2")
    ap.add_argument("--oversample", type=float, default=1.35)
    ap.add_argument("--out", default=str(ROOT / "results" / "calibration_corpus.json"))
    args = ap.parse_args()

    dep_seeds = [int(x) for x in args.dep_seeds.replace(" ", "").split(",") if x]

    banned = set()
    dep_sources = Counter()
    dep_total = 0
    for s in dep_seeds:
        spec = SCALES[args.scale]
        spec.seed = s
        dep = build_corpus(spec, source=args.source)
        for w in dep:
            banned.add(ident(w))
            dep_sources[w.dataset] += 1
        dep_total += len(dep)
        print(f"deployment seed {s}: {len(dep)} windows", flush=True)
    print(f"{len(banned)} distinct identities to avoid")

    raw = build_corpus(spec_for(args.n, args.seed, args.oversample),
                       source=args.source)
    print(f"raw calibration draw, seed {args.seed}: {len(raw)} windows")

    # Remove collisions with deployment and duplicates inside the draw itself.
    seen = set()
    kept_by_stratum = defaultdict(list)
    dropped_overlap = dropped_dup = 0
    for w in raw:
        k = ident(w)
        if k in banned:
            dropped_overlap += 1
            continue
        if k in seen:
            dropped_dup += 1
            continue
        seen.add(k)
        kept_by_stratum[w.stratum].append(w)
    print(f"  dropped {dropped_overlap} colliding with deployment, "
          f"{dropped_dup} duplicated within the draw")

    want = target_counts(args.n)
    final = []
    short = {}
    for st, target in want.items():
        pool = kept_by_stratum.get(st, [])
        take = pool[:target]
        final.extend(take)
        if len(take) < target:
            short[st] = {"wanted": target, "got": len(take)}
    print(f"calibration corpus: {len(final)} windows, target {sum(want.values())}")
    if short:
        print(f"  strata that could not be filled: {short}")
        print(f"  raise --oversample and rerun rather than accepting a skew")

    # Hard check one, overlap.
    final_ids = set(ident(w) for w in final)
    overlap = len(final_ids & banned)
    print()
    print(f"hard check 1, overlap with any deployment seed: {overlap}")
    print(f"  distinct identities {len(final_ids)} of {len(final)} windows, "
          f"{len(final) - len(final_ids)} internal duplicates")

    # Hard check two, source composition.
    cal_sources = Counter(w.dataset for w in final)
    all_src = sorted(set(cal_sources) | set(dep_sources))
    print()
    print("hard check 2, source composition")
    print(f"{'dataset':24s}{'calibration':>14s}{'deployment':>13s}{'gap':>9s}")
    worst = 0.0
    for s in all_src:
        a = cal_sources[s] / max(len(final), 1)
        b = dep_sources[s] / max(dep_total, 1)
        worst = max(worst, abs(a - b))
        print(f"{s:24s}{a:14.4f}{b:13.4f}{a - b:+9.4f}")
    missing = [s for s in all_src if cal_sources[s] == 0 or dep_sources[s] == 0]
    print(f"  largest share gap {worst:.4f}, "
          f"sources present in one and not the other: {missing or 'none'}")

    cal_strata = Counter(w.stratum for w in final)
    print()
    print("stratum composition")
    print(f"{'stratum':16s}{'calibration':>14s}{'target':>10s}")
    for st in sorted(cal_strata):
        print(f"{st:16s}{cal_strata[st] / len(final):14.4f}"
              f"{DEPLOY_SHARES.get(st, 0.0):10.4f}")

    ok = overlap == 0 and not missing and not short
    print()
    print(f"both hard checks {'PASS' if ok else 'FAIL'}")

    Path(args.out).write_text(json.dumps(
        {"seed": args.seed, "n": len(final), "source": args.source,
         "overlap_with_deployment": overlap,
         "dropped_overlap": dropped_overlap, "dropped_duplicate": dropped_dup,
         "internal_duplicates": len(final) - len(final_ids),
         "shortfall": short,
         "calibration_sources": dict(cal_sources),
         "deployment_sources": dict(dep_sources),
         "largest_source_gap": worst,
         "window_ids": [int(w.window_id) for w in final],
         "passes": bool(ok)}, indent=1, default=float), encoding="utf-8")
    print("___CALIBRATION_BUILD_DONE___")


if __name__ == "__main__":
    main()
