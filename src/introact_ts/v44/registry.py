"""Frozen source registry and row reader for v4.4.

Reads the same eight sources under the same 60/15/10/15 split already
pre-registered by the r5 main protocol.  Two Weather TRAIN parents are declared
unsupported by the r5 timestamp audit and stay excluded here as well; the task
book requires that they keep their unsupported status rather than be silently
repaired.

The reader streams each container file exactly once per pass and yields the
context and the future separately, so a deployment path that must not see the
future simply never asks for it.
"""

from __future__ import annotations

import csv
import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from .protocol import CONTEXT, HORIZONS, SOURCES
from .splits import ParentWindow

PROTOCOL_PATH = "configs/v431-r5/main_protocol_v2.json"
TIMESTAMP_AUDIT_PATH = "results/v431-r5/main-preparation/audit-v2/timestamp_audit.json"


@dataclass(frozen=True)
class SourceInfo:
    source: str
    path: str
    columns: int
    target_channel: int
    split_bounds: dict
    frequency: str
    file_sha256: str


def load_protocol(root: str | Path) -> dict:
    return json.loads((Path(root) / PROTOCOL_PATH).read_text())


def unsupported_parents(root: str | Path) -> set[str]:
    """TRAIN parents the r5 timestamp audit marked unsupported."""
    path = Path(root) / TIMESTAMP_AUDIT_PATH
    if not path.exists():
        return set()
    audit = json.loads(path.read_text())
    return {row["parent"] for row in audit.get("affected_parent_windows", [])}


def source_registry(root: str | Path) -> dict[str, SourceInfo]:
    protocol = load_protocol(root)
    registry: dict[str, SourceInfo] = {}
    for info in protocol["sources"]:
        if info["source"] not in SOURCES:
            continue
        registry[info["source"]] = SourceInfo(
            source=info["source"],
            path=info["path"],
            columns=int(info["columns"]),
            target_channel=0,
            split_bounds={k: tuple(v) for k, v in info["split_bounds"].items()},
            frequency=info.get("frequency", "unknown"),
            file_sha256=info["file_sha256"],
        )
    missing = [s for s in SOURCES if s not in registry]
    if missing:
        raise KeyError(f"protocol is missing registered sources: {missing}")
    return registry


def train_parents(root: str | Path, *, exclude_unsupported: bool = True,
                  horizons=HORIZONS) -> list[ParentWindow]:
    """The legal TRAIN parents, in registry order."""
    protocol = load_protocol(root)
    unsupported = unsupported_parents(root) if exclude_unsupported else set()
    parents: list[ParentWindow] = []
    for window in protocol["windows_metadata"]:
        if window["role"] != "train":
            continue
        if window["parent"] in unsupported:
            continue
        if not set(horizons) <= set(window["horizons"]):
            continue
        parents.append(ParentWindow(
            source=window["source"],
            parent=window["parent"],
            read_start=int(window["read_start"]),
            origin=int(window["origin"]),
            max_target_end=int(window["max_target_end"]),
            role="train",
        ))
    return parents


def source_rows(path: str | Path) -> Iterator[tuple[int, list[str]]]:
    """Container rows as strings; the caller converts only allowed contexts.

    Matches the frozen r5 convention exactly: gzip containers have no header
    row, csv containers carry a timestamp column that is dropped.
    """
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as handle:
        rows = csv.reader(handle)
        if path.suffix != ".gz":
            next(rows)
        for index, row in enumerate(rows):
            yield index, (row if path.suffix == ".gz" else row[1:])


def read_windows(root: str | Path, info: SourceInfo,
                 windows: list[ParentWindow], *, horizon: int,
                 context: int = CONTEXT) -> Iterator[tuple[ParentWindow, np.ndarray, np.ndarray]]:
    """Stream one source once, yielding ``(window, context, future)`` in order.

    ``context`` is ``(context, columns)`` with NaN for gaps; ``future`` is the
    target channel over the horizon.  Windows must be sorted and disjoint.  Only
    the rows of the current window are held in memory.
    """
    ordered = sorted(windows, key=lambda w: w.read_start)
    if not ordered:
        return
    path = Path(root) / info.path
    if not path.exists():
        raise FileNotFoundError(f"missing source container {path}")

    iterator = source_rows(path)
    cursor = -1
    row: list[str] | None = None
    span = context + horizon

    for window in ordered:
        if window.origin + horizon > window.max_target_end:
            raise ValueError(f"horizon {horizon} exceeds window {window.parent}")
        while cursor < window.read_start:
            cursor, row = next(iterator)
        block: list[list[float]] = []
        while len(block) < span:
            block.append([float(c) if c.strip() else np.nan for c in row])
            if len(block) == span:
                break
            cursor, row = next(iterator)
        if cursor != window.read_start + span - 1:
            raise ValueError(f"row cursor desynchronised for {window.parent}")
        values = np.asarray(block, dtype=np.float64)
        if values.shape != (span, info.columns):
            raise ValueError(f"unexpected block shape for {window.parent}: {values.shape}")
        if np.isinf(values).any():
            raise ValueError(f"infinity in {window.parent}")
        yield window, values[:context].copy(), values[context:, info.target_channel].copy()


def expected_window_count(root: str | Path) -> dict:
    """Per-source TRAIN parent counts, for the protocol freeze record."""
    parents = train_parents(root)
    counts: dict[str, int] = {source: 0 for source in SOURCES}
    for parent in parents:
        counts[parent.source] += 1
    return counts
