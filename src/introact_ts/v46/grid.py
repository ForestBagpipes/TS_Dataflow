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
from introact_ts.v44 import protocol as P
from introact_ts.v44 import registry as R
from introact_ts.v44.splits import ParentWindow

#: Blocks of the v4.6 run.  ``bank`` and ``train_eval`` are inside TRAIN,
#: ``test`` is the held-out region every reported table is computed on, and
#: ``test30`` / ``test50`` are the same TEST parents at the two higher
#: registered severities, used for the within-grid robustness sweep.
BLOCKS = ("bank", "train_eval", "test", "test30", "test50")

#: TRAIN is split by origin time; the bank gets the earlier parents.
BANK_FRACTION = 0.80

#: Severities enumerated per block.  The bank draws one hash-chosen severity
#: per episode from the full ladder, exactly as v4.4 did, so a request at any
#: registered severity has same-severity support.  TRAIN-eval and TEST run the
#: main severity; the robustness sweep adds 30 % and 50 % on TEST separately.
BLOCK_SEVERITIES = {
    "bank": None,                       # None means hash-mixed
    "train_eval": (P.MAIN_SEVERITY,),
    "test": (P.MAIN_SEVERITY,),
    "test30": (0.30,),
    "test50": (0.50,),
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


def parents_of(root: str | Path, block: str) -> list[ParentWindow]:
    if block.startswith("test"):
        return test_parents(root)
    train = train_parents(root)
    assignment = assign_train(train)
    return [p for p in train if assignment[p.parent] == block]


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
                  severities=None) -> list[EpisodeSpec]:
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
                                           parent.origin, horizon, pattern)
                          if mixed else None)
                for severity in ([chosen] if mixed else levels):
                    specs.append(EpisodeSpec(
                        episode_id=episode_id(parent.source, parent.parent,
                                              horizon, pattern, severity),
                        source=parent.source, parent=parent.parent,
                        origin=int(parent.origin), read_start=int(parent.read_start),
                        horizon=int(horizon), pattern=pattern,
                        severity=float(severity),
                        severity_source="hash_mixed" if mixed else "main",
                        block=block, period=P.seasonal_period(parent.source),
                        n_channels=int(info.columns)))
    return specs


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
                                            n_channels=context.shape[1])
                        yield spec, context, M.apply_mask(context, mask), future


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
