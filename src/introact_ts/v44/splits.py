"""TRAIN-internal partitioning (task book §10).

Three contiguous, time-ordered blocks inside the legal TRAIN split:

* **replay_fit** (~60%) -- builds the replay bank, fits the feature scaler, and
  fits any trainable baseline.
* **gate** (~20%) -- the only place ``K`` and ``beta`` are chosen.
* **train_eval** (~20%) -- frozen-method internal validation and admission.

Every pattern / severity / horizon variant of a parent stays inside the same
block, because variants of one parent share a future and are therefore
correlated.  A purge of at least ``L + max(H)`` rows separates the blocks.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .masking import mixed_severity
from .protocol import (
    CONTEXT,
    HORIZONS,
    MAIN_SEVERITY,
    PATTERNS,
    PURGE,
    SEVERITIES,
    SPLIT_NAMES,
    SPLIT_RATIOS,
)

#: Which severities each block is evaluated at.
#:
#: Replay-Fit draws a *mixed* support: every historical pseudo-deployment gets
#: exactly one severity, chosen by hash from the ladder (task book §9).  Gate
#: and TRAIN-Eval run the single main severity, because ``K``/``beta`` are
#: selected for -- and the method is admitted under -- the main condition.
BLOCK_SEVERITIES = {
    "replay_fit": SEVERITIES,
    "gate": (MAIN_SEVERITY,),
    "train_eval": (MAIN_SEVERITY,),
}

#: Blocks whose severity is decided per episode rather than enumerated.
MIXED_SEVERITY_BLOCKS = ("replay_fit",)


@dataclass(frozen=True)
class ParentWindow:
    """One TRAIN parent window, as declared by the frozen r5 protocol."""

    source: str
    parent: str
    read_start: int
    origin: int
    max_target_end: int
    role: str = "train"

    @property
    def span(self) -> tuple[int, int]:
        return (self.read_start, self.max_target_end)


def _boundaries(count: int, ratios=SPLIT_RATIOS) -> list[int]:
    """Index boundaries of the contiguous blocks, each guaranteed non-empty."""
    if count < len(ratios):
        raise ValueError(f"need at least {len(ratios)} parents, got {count}")
    cuts = [int(round(count * r)) for r in np.cumsum(ratios)[:-1]]
    # Enforce strictly increasing, non-empty blocks without changing the ratio
    # more than one parent.
    for i in range(len(cuts)):
        low = (cuts[i - 1] if i else 0) + 1
        cuts[i] = max(cuts[i], low)
    for i in range(len(cuts) - 1, -1, -1):
        high = (cuts[i + 1] if i + 1 < len(cuts) else count) - 1
        cuts[i] = min(cuts[i], high)
    if cuts != sorted(set(cuts)) or len(set(cuts)) != len(cuts):
        raise ValueError("degenerate split boundaries")
    return cuts


def assign_splits(parents: list[ParentWindow], *, ratios=SPLIT_RATIOS,
                  purge: int = PURGE) -> dict[str, str]:
    """Map ``parent`` -> block name, source by source, in time order."""
    if not parents:
        return {}
    assignment: dict[str, str] = {}
    by_source: dict[str, list[ParentWindow]] = {}
    for parent in parents:
        if parent.role != "train":
            raise ValueError(f"non-TRAIN parent in development split: {parent.parent}")
        by_source.setdefault(parent.source, []).append(parent)

    for source, items in by_source.items():
        ordered = sorted(items, key=lambda p: p.read_start)
        cuts = _boundaries(len(ordered), ratios)
        edges = [0] + cuts + [len(ordered)]
        for i, name in enumerate(SPLIT_NAMES):
            for parent in ordered[edges[i]:edges[i + 1]]:
                if parent.parent in assignment:
                    raise ValueError(f"duplicate parent {parent.parent}")
                assignment[parent.parent] = name

    audit_purge(ordered_all(parents), assignment, purge=purge)
    return assignment


def ordered_all(parents: list[ParentWindow]) -> list[ParentWindow]:
    return sorted(parents, key=lambda p: (p.source, p.read_start))


def audit_purge(parents: list[ParentWindow], assignment: dict[str, str], *,
                purge: int = PURGE) -> dict:
    """Verify the purge and disjointness guarantees; raise on violation.

    Two different blocks may not share a raw row, and their forecast origins
    must be at least ``purge`` rows apart.  With the frozen stride this holds
    exactly, so a failure here means the window registry changed.
    """
    by_source: dict[str, list[ParentWindow]] = {}
    for parent in parents:
        by_source.setdefault(parent.source, []).append(parent)
    checked = 0
    for source, items in by_source.items():
        ordered = sorted(items, key=lambda p: p.read_start)
        for a, b in zip(ordered, ordered[1:]):
            split_a, split_b = assignment[a.parent], assignment[b.parent]
            if split_a == split_b:
                continue
            checked += 1
            lo, hi = a.span
            lo_b, hi_b = b.span
            if max(lo, lo_b) < min(hi, hi_b):
                raise ValueError(
                    f"purge violation: {a.parent} and {b.parent} share rows")
            if b.origin - a.origin < purge:
                raise ValueError(
                    f"purge violation: origins {a.origin}->{b.origin} closer "
                    f"than {purge}")
    return {"boundary_pairs_checked": checked, "purge": purge}


def episode_grid(parents: list[ParentWindow], assignment: dict[str, str], *,
                 block: str, horizons=HORIZONS, patterns=PATTERNS,
                 severities=None) -> list[dict]:
    """Enumerate the (parent, horizon, pattern, severity) episodes of a block.

    For ``replay_fit`` the severity is *not* enumerated: each episode receives
    one hash-chosen severity from the ladder, so the bank's support is mixed
    without tripling the number of historical executions.
    """
    if block not in SPLIT_NAMES:
        raise ValueError(f"unregistered block {block!r}")
    mixed = severities is None and block in MIXED_SEVERITY_BLOCKS
    if severities is None:
        severities = BLOCK_SEVERITIES[block]
    grid: list[dict] = []
    for parent in sorted(parents, key=lambda p: (p.source, p.read_start)):
        if assignment.get(parent.parent) != block:
            continue
        for horizon in horizons:
            if parent.origin + horizon > parent.max_target_end:
                continue
            for pattern in patterns:
                chosen = (mixed_severity(parent.source, parent.parent,
                                         parent.origin, horizon, pattern)
                          if mixed else None)
                for severity in ([chosen] if mixed else severities):
                    grid.append({
                        "source": parent.source,
                        "parent": parent.parent,
                        "origin": parent.origin,
                        "read_start": parent.read_start,
                        "horizon": int(horizon),
                        "pattern": pattern,
                        "severity": float(severity),
                        "severity_source": "hash_mixed" if mixed else "main",
                        "block": block,
                    })
    return grid


def block_summary(parents: list[ParentWindow],
                  assignment: dict[str, str]) -> dict:
    summary: dict[str, dict] = {name: {"parents": 0, "sources": set()}
                                for name in SPLIT_NAMES}
    for parent in parents:
        block = assignment[parent.parent]
        summary[block]["parents"] += 1
        summary[block]["sources"].add(parent.source)
    return {name: {"parents": data["parents"],
                   "sources": len(data["sources"]),
                   "source_list": sorted(data["sources"])}
            for name, data in summary.items()}


def context_bounds(parent: ParentWindow) -> tuple[int, int]:
    """Half-open raw row interval of the 512-step context."""
    return (parent.read_start, parent.read_start + CONTEXT)
