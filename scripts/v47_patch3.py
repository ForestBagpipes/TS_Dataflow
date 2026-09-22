#!/usr/bin/env python3
"""Two fixes and one saving, found by running the stage.

The plausibility guard was applied to every candidate, including the reference.
The reference action is the incomplete context itself, so its missing positions
are still missing by definition, and the guard read that as a failed repair and
marked it unsupported on every episode.  With no reference execution there is
no reference forecast, and the bank came out empty.  The guard now looks only
at the positions a repair wrote, and the reference action is exempt from it
because it writes nothing.

The rerun would otherwise recompute every prediction that is already on disk.
A prediction is keyed by the input hash under a pinned model revision, so the
run may read the earlier archive for any input it has already seen and spend a
call only on the ones it has not.  The count of reused entries is recorded.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path("/home/vipuser/work/work2")
CHANGES: list[str] = []


def edit(rel: str, old: str, new: str, *, tag: str) -> None:
    path = ROOT / rel
    text = path.read_text()
    if new in text:
        print("  = already present:", tag)
        return
    if text.count(old) != 1:
        raise SystemExit(f"FAILED {tag}: anchor appears {text.count(old)} times")
    path.write_text(text.replace(old, new))
    CHANGES.append(tag)


# ---------------------------------------------- the guard looks at the repair

edit("src/introact_ts/v44/actions.py",
     '''    filled = np.asarray(filled, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    if filled.shape != reference.shape:
        return "candidate length differs from the reference"
    if not np.isfinite(filled).all():
        return "candidate is not finite"
    written = ~np.isfinite(reference)
    if not written.any():
        return None
    lo, hi = plausibility_bounds(reference)
    values = filled[written]''',
     '''    filled = np.asarray(filled, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    if filled.shape != reference.shape:
        return "candidate length differs from the reference"
    written = ~np.isfinite(reference)
    if not written.any():
        return None
    values = filled[written]
    if not np.isfinite(values).all():
        return "repair left a hidden position unfilled"
    lo, hi = plausibility_bounds(reference)''',
     tag="guard: judge a repair by the positions it wrote")


# ------------------------------------- the reference action writes nothing

edit("scripts/v47_forecast.py",
     '''                # Every candidate meets the registered plausibility bound
                # before it is executed, whichever stage produced it, so a
                # diverging repair is recorded here instead of entering the
                # bank as a legitimate execution.
                implausible = A.implausible_reason(value, store[f"{key}|reference"])''',
     '''                # Every repair meets the registered plausibility bound before
                # it is executed, whichever stage produced it, so a diverging
                # repair is recorded here instead of entering the bank as a
                # legitimate execution.  The reference action repairs nothing
                # and is the incomplete context itself, so it is exempt.
                implausible = (None if action == P.REFERENCE_ACTION else
                               A.implausible_reason(value, store[f"{key}|reference"]))''',
     tag="forecast: the reference action is exempt from the repair guard")


# ------------------------------------------- reuse the predictions on disk

edit("scripts/v47_forecast.py",
     '''    parser.add_argument("--limit", type=int, default=0,
                        help="probe only the first N episodes (diagnostic runs)")''',
     '''    parser.add_argument("--limit", type=int, default=0,
                        help="probe only the first N episodes (diagnostic runs)")
    parser.add_argument("--donor", default="",
                        help="an earlier predictions archive of the same block and "
                             "backbone; entries whose input hash and horizon match "
                             "are read from it instead of being recomputed")''',
     tag="forecast: a donor archive argument")

edit("scripts/v47_forecast.py",
     '''            try:
                order = sorted(unique)
                for index, digest in enumerate(order):''',
     '''            # A prediction is keyed by the input hash under a pinned model
            # revision and dtype, which is the cache identity the protocol
            # defines, so an entry that matches may be read rather than
            # recomputed.  The count is recorded in the status file.
            donor_hits = 0
            if args.donor:
                with np.load(args.donor, allow_pickle=False) as old:
                    for name in old.files:
                        if name not in arrays:
                            arrays[name] = old[name]
                            donor_hits += 1
            try:
                order = sorted(unique)
                for index, digest in enumerate(order):''',
     tag="forecast: load the donor archive")

edit("scripts/v47_forecast.py",
     '''                    for horizon in horizons:
                        tick = time.perf_counter()
                        try:''',
     '''                    for horizon in horizons:
                        if f"{digest}|h{horizon}" in arrays:
                            continue
                        tick = time.perf_counter()
                        try:''',
     tag="forecast: skip an input the donor already carries")

edit("scripts/v47_forecast.py",
     '''        "unique_inputs": len(unique),
        "unique_predictions": len(arrays),''',
     '''        "unique_inputs": len(unique),
        "unique_predictions": len(arrays),
        "donor": args.donor or None,
        "reused_from_donor": donor_hits,
        "computed_here": len(calls),''',
     tag="forecast: record what was reused")

print("APPLIED:")
for item in CHANGES:
    print("  +", item)
