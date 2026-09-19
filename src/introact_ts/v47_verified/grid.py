"""v4.6 episode grid: the TRAIN bank region, the TRAIN-eval block, and TEST.

The row regions come from the pre-registered r5 split bounds and are not
re-derived here.  Each source is divided into

    TRAIN  = the ``train`` and ``dev`` row ranges      (first 75 % of the rows)
    TEST   = the ``calibration`` and ``test`` ranges   (last 25 % of the rows)

TRAIN parents are the pre-registered windows of those two roles, minus the two
Weather windows the r5 timestamp audit declared unsupported and minus the last
window of each source, which is dropped as an explicit purge buffer.  TEST
parents do not exist in the pre-registered metadata, so they are tiled from the
start of the TEST region at the frozen stride.

Nothing in this module reads a data value.  A parent is an interval of raw row
indices, and the mask of an episode is a pure function of the identity tuple.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from introact_ts.v44 import masking as M
from . import protocol as P
from introact_ts.v44 import registry as R
from introact_ts.v44.splits import ParentWindow

#: Blocks of the v4.6 run.  ``bank`` and ``train_eval`` are inside TRAIN,
#: ``test`` is the held-out region every reported table is computed on, and
#: ``test30`` / ``test50`` are the same TEST parents at the two higher
#: registered severities, used for the within-grid robustness sweep.
BLOCKS = ("bank", "bankx", "bankx2", "train_eval", "test", "test30", "test50",
          "test_m2", "test_m3")

#: Mask realisation of a block.  Every block uses the registered protocol seed
#: except the two stability blocks, which re-derive the masks of the same TEST
#: parents from a different seed.  Nothing else about them differs, so a
#: difference between them is a difference in the deletion pattern alone.
MASK_SEED = {"test_m2": P.PROTOCOL_SEED + 1, "test_m3": P.PROTOCOL_SEED + 2,
             "bankx2": P.PROTOCOL_SEED + 1}


def mask_seed_of(block: str) -> int:
    return MASK_SEED.get(block, P.PROTOCOL_SEED)

#: TRAIN is split by origin time; the bank gets the earlier parents.
BANK_FRACTION = 0.80

#: Severities enumerated per block.  The bank draws one hash-chosen severity
#: per episode from the full ladder, exactly as v4.4 did, so a request at any
#: registered severity has same-severity support.  TRAIN-eval and TEST run the
#: main severity; the robustness sweep adds 30 % and 50 % on TEST separately.
BLOCK_SEVERITIES = {
    "bank": None,                       # None means hash-mixed
    #: v4.7 enumerates the ladder instead of drawing one level per episode, so
    #: every parent, pattern and horizon carries support at every registered
    #: severity rather than at a hash-chosen one.
    "bankx": P.SEVERITIES,
    "bankx2": P.SEVERITIES,
    "train_eval": (P.MAIN_SEVERITY,),
    "test": (P.MAIN_SEVERITY,),
    "test30": (0.30,),
    "test50": (0.50,),
    "test_m2": (P.MAIN_SEVERITY,),
    "test_m3": (P.MAIN_SEVERITY,),
}


@dataclass(frozen=True)
class EpisodeSpec:
    episode_id: str
    source: str
    parent: str
    origin: int
    read_start: int
    horizon: int
    pattern: str
    severity: float
    severity_source: str
    block: str
    period: int
    n_channels: int


def episode_id(source: str, parent: str, horizon: int, pattern: str,
               severity: float) -> str:
    return f"{source}|{parent}|h{horizon}|{pattern}|s{int(round(severity * 100)):02d}"


# --------------------------------------------------------------------- parents

def train_parents(root: str | Path) -> list[ParentWindow]:
    """Pre-registered ``train`` and ``dev`` windows, audited and purge-buffered."""
    protocol = R.load_protocol(root)
    unsupported = R.unsupported_parents(root)
    out: list[ParentWindow] = []
    for window in protocol["windows_metadata"]:
        if window["role"] not in ("train", "dev"):
            continue
        if window["parent"] in unsupported:
            continue
        if not set(P.HORIZONS) <= set(window["horizons"]):
            continue
        out.append(ParentWindow(
            source=window["source"], parent=window["parent"],
            read_start=int(window["read_start"]), origin=int(window["origin"]),
            max_target_end=int(window["max_target_end"]), role="train"))
    # Drop the latest window of each source: it is the one that sits against the
    # TEST boundary, and dropping it buys a full extra purge interval.
    latest: dict[str, ParentWindow] = {}
    for parent in out:
        if parent.source not in latest or parent.read_start > latest[parent.source].read_start:
            latest[parent.source] = parent
    dropped = {p.parent for p in latest.values()}
    return [p for p in out if p.parent not in dropped]


def test_parents(root: str | Path, *, stride: int = P.PARENT_STRIDE) -> list[ParentWindow]:
    """TEST windows, tiled from the start of the held-out region."""
    registry = R.source_registry(root)
    out: list[ParentWindow] = []
    for source in P.SOURCES:
        info = registry[source]
        start = int(info.split_bounds["calibration"][0])
        end = int(info.split_bounds["test"][1])
        span = P.CONTEXT + max(P.HORIZONS)
        read_start = start
        while read_start + span <= end:
            out.append(ParentWindow(
                source=source, parent=f"{source}:{read_start}:{read_start + span}",
                read_start=read_start, origin=read_start + P.CONTEXT,
                max_target_end=read_start + span, role="train"))
            read_start += stride
    return out


#: The densified bank blocks draw the same TRAIN parents as ``bank``.
BANK_ALIAS = {"bankx": "bank", "bankx2": "bank"}


def parents_of(root: str | Path, block: str) -> list[ParentWindow]:
    if block.startswith("test"):
        return test_parents(root)
    train = train_parents(root)
    assignment = assign_train(train)
    return [p for p in train if assignment[p.parent] == BANK_ALIAS.get(block, block)]


def assign_train(parents: list[ParentWindow]) -> dict[str, str]:
    """Split TRAIN by origin time inside each source: bank first, then TRAIN-eval."""
    assignment: dict[str, str] = {}
    by_source: dict[str, list[ParentWindow]] = {}
    for parent in parents:
        by_source.setdefault(parent.source, []).append(parent)
    for items in by_source.values():
        ordered = sorted(items, key=lambda p: p.read_start)
        cut = max(1, min(len(ordered) - 1, int(round(len(ordered) * BANK_FRACTION))))
        for parent in ordered[:cut]:
            assignment[parent.parent] = "bank"
        for parent in ordered[cut:]:
            assignment[parent.parent] = "train_eval"
    return assignment


def audit_purge(root: str | Path) -> dict:
    """No TRAIN context may overlap a TEST target, and vice versa."""
    train = train_parents(root)
    test = test_parents(root)
    train_end = {}
    test_start = {}
    for p in train:
        train_end[p.source] = max(train_end.get(p.source, 0), p.max_target_end)
    for p in test:
        test_start[p.source] = min(test_start.get(p.source, 10 ** 12), p.read_start)
    gaps = {}
    for source in P.SOURCES:
        gap = test_start[source] - train_end[source]
        if gap < 0:
            raise ValueError(f"TRAIN and TEST rows overlap on {source}: gap {gap}")
        gaps[source] = int(gap)
    # Inside TRAIN the two blocks are contiguous in time; the purge there is the
    # stride, because parents tile at L + max(H) and therefore never share a row.
    assignment = assign_train(train)
    for source in P.SOURCES:
        ordered = sorted([p for p in train if p.source == source],
                         key=lambda p: p.read_start)
        for a, b in zip(ordered, ordered[1:]):
            if assignment[a.parent] == assignment[b.parent]:
                continue
            if b.origin - a.origin < P.PURGE:
                raise ValueError(f"purge violation inside TRAIN on {source}")
            if max(a.span[0], b.span[0]) < min(a.span[1], b.span[1]):
                raise ValueError(f"overlapping TRAIN parents on {source}")
    return {"train_test_row_gap": gaps, "purge": P.PURGE}


# -------------------------------------------------------------------- episodes

def episode_specs(root: str | Path, block: str, *, horizons=P.HORIZONS,
                  severities=None, parent_limit=None) -> list[EpisodeSpec]:
    """The frozen episode list of one block, in source and time order."""
    if block not in BLOCKS:
        raise ValueError(f"unregistered block {block!r}")
    root = Path(root)
    registry = R.source_registry(root)
    parents = parents_of(root, block)
    levels = severities if severities is not None else BLOCK_SEVERITIES[block]
    mixed = levels is None
    specs: list[EpisodeSpec] = []
    for parent in sorted(parents, key=lambda p: (p.source, p.read_start)):
        info = registry[parent.source]
        for horizon in horizons:
            if parent.origin + horizon > parent.max_target_end:
                continue
            for pattern in P.PATTERNS:
                chosen = (M.mixed_severity(parent.source, parent.parent,
                                           parent.origin, horizon, pattern,
                                           protocol_seed=mask_seed_of(block))
                          if mixed else None)
                realisation = ("" if mask_seed_of(block) == P.PROTOCOL_SEED
                               else f"|r{mask_seed_of(block) - P.PROTOCOL_SEED}")
                for severity in ([chosen] if mixed else levels):
                    # A block that re-derives its masks from another seed is a
                    # different request set, so its episode ids must not
                    # collide with the primary realisation of the same window.
                    specs.append(EpisodeSpec(
                        episode_id=episode_id(parent.source, parent.parent,
                                              horizon, pattern, severity) + realisation,
                        source=parent.source, parent=parent.parent,
                        origin=int(parent.origin), read_start=int(parent.read_start),
                        horizon=int(horizon), pattern=pattern,
                        severity=float(severity),
                        severity_source="hash_mixed" if mixed else "main",
                        block=block, period=P.seasonal_period(parent.source),
                        n_channels=int(info.columns)))
    return select_pilot_specs(specs, parent_limit or 0)


def iter_panels(root: str | Path, specs: list[EpisodeSpec]
                ) -> Iterator[tuple[EpisodeSpec, np.ndarray, np.ndarray, np.ndarray]]:
    """Yield ``(spec, raw_context, masked_panel, future)`` for a block.

    The raw context travels alongside the masked one because the metric
    denominators are computed on the untouched series: a denominator that moved
    with the mask would make two patterns of one window incomparable.
    """
    root = Path(root)
    registry = R.source_registry(root)
    window_map = {(s.source, s.parent): s for s in specs}
    by_source: dict[str, list[EpisodeSpec]] = {}
    for spec in specs:
        by_source.setdefault(spec.source, []).append(spec)

    for source, source_specs in sorted(by_source.items()):
        info = registry[source]
        windows_by_name = {}
        for spec in source_specs:
            windows_by_name.setdefault(spec.parent, ParentWindow(
                source=spec.source, parent=spec.parent, read_start=spec.read_start,
                origin=spec.origin, max_target_end=spec.origin + max(P.HORIZONS),
                role="train"))
        for horizon in sorted({s.horizon for s in source_specs}):
            subset = [s for s in source_specs if s.horizon == horizon]
            names = sorted({s.parent for s in subset},
                           key=lambda n: windows_by_name[n].read_start)
            windows = [windows_by_name[n] for n in names]
            index: dict[tuple[str, str], list[EpisodeSpec]] = {}
            for spec in subset:
                index.setdefault((spec.parent, spec.pattern), []).append(spec)
            for window, context, future in R.read_windows(
                    root, info, windows, horizon=horizon):
                for pattern in P.PATTERNS:
                    for spec in index.get((window.parent, pattern), []):
                        mask = M.build_mask(source, window.parent, window.origin,
                                            horizon, pattern, spec.severity,
                                            length=context.shape[0],
                                            n_channels=context.shape[1],
                                            protocol_seed=mask_seed_of(spec.block))
                        yield spec, context, M.apply_mask(context, mask), future


def select_pilot_specs(specs: list[EpisodeSpec], parent_limit: int = 32
                       ) -> list[EpisodeSpec]:
    """Select whole parents, round-robin across sources, retaining all variants."""
    if parent_limit <= 0:
        return list(specs)
    parents = {}
    for spec in specs:
        parents[(spec.source, spec.parent)] = spec.read_start
    by_source = {}
    for (source, parent), start in parents.items():
        by_source.setdefault(source, []).append((start, parent))
    for source in by_source:
        by_source[source].sort()
    chosen = set()
    for rank in range(max((len(v) for v in by_source.values()), default=0)):
        for source in sorted(by_source):
            if rank < len(by_source[source]) and len(chosen) < parent_limit:
                chosen.add((source, by_source[source][rank][1]))
    return [s for s in specs if (s.source, s.parent) in chosen]


def iter_contexts(root: str | Path, specs: list[EpisodeSpec]
                  ) -> Iterator[tuple[EpisodeSpec, np.ndarray, np.ndarray]]:
    """Convert only requested context rows; never parse any future value.

    Container traversal may skip target rows as opaque strings. The numerical
    reader stops at each origin and never requests the final target row range.
    """
    registry = R.source_registry(root)
    by_source = {}
    for spec in specs:
        by_source.setdefault(spec.source, {}).setdefault(spec.parent, []).append(spec)
    for source, parents in sorted(by_source.items()):
        info = registry[source]
        iterator = iter(R.source_rows(Path(root) / info.path))
        cursor, row = -1, None
        previous_end = -1
        for variants in sorted(parents.values(), key=lambda group: group[0].read_start):
            first = variants[0]
            if first.read_start < previous_end or first.origin - first.read_start != P.CONTEXT:
                raise ValueError("overlapping parents or nonregistered context length")
            while cursor < first.read_start:
                cursor, row = next(iterator)
            values = []
            for offset in range(P.CONTEXT):
                if cursor != first.read_start + offset:
                    raise ValueError("context row cursor desynchronised")
                values.append([float(c) if c.strip() else np.nan for c in row])
                if offset + 1 < P.CONTEXT:
                    cursor, row = next(iterator)
            context = np.asarray(values, dtype=np.float64)
            if context.shape != (P.CONTEXT, info.columns) or np.isinf(context).any():
                raise ValueError(f"invalid context for {first.parent}")
            previous_end = first.origin
            for spec in variants:
                if (spec.read_start, spec.origin) != (first.read_start, first.origin):
                    raise ValueError("parent variants disagree on row bounds")
                mask = M.build_mask(source, spec.parent, spec.origin, spec.horizon,
                                    spec.pattern, spec.severity,
                                    length=P.CONTEXT, n_channels=info.columns,
                                    protocol_seed=mask_seed_of(spec.block))
                yield spec, context.copy(), M.apply_mask(context, mask)


def summary(root: str | Path) -> dict:
    """Block sizes, for the protocol freeze record."""
    out = {}
    for block in BLOCKS:
        parents = parents_of(root, block)
        specs = episode_specs(root, block)
        per_source: dict[str, int] = {}
        for p in parents:
            per_source[p.source] = per_source.get(p.source, 0) + 1
        out[block] = {"parents": len(parents), "episodes": len(specs),
                      "sources": len(per_source),
                      "per_source": dict(sorted(per_source.items()))}
    out["purge_audit"] = audit_purge(root)
    return out
