"""v54 confirmatory grid: Solar and US_Term_Structure (protocol freeze §7).

A mirror of ``introact_ts.v46.grid`` bound to the independent confirmatory
registry ``configs/v54/confirmatory_registry.json`` instead of the main
protocol file.  The main registry, the eight main sources and every main-set
code path are untouched; the confirmatory sources have their own registry,
their own parent tiling and their own episode namespace, while every frozen
constant (CONTEXT, HORIZONS, PARENT_STRIDE, PURGE, PROTOCOL_SEED, PATTERNS,
SEVERITIES, the 0.80 bank fraction and the mask seed derivation) is imported
from ``introact_ts.v44.protocol`` unchanged.

Differences from the main grid, all registered here:

* TRAIN parents are tiled per segment (``train`` and ``dev`` separately, each
  from its own segment start at stride 704, exactly how the r5
  ``windows_metadata`` were built) because the confirmatory sources have no
  pre-registered window metadata.
* Only ``bankx``, ``train_eval``, ``test``, ``test_m2`` and ``test_m3`` exist;
  the 30 %/50 % robustness blocks and ``bankx2`` are not run on the
  confirmatory set (task book freeze §7).
* ``US_Term_Structure`` keeps its native missingness (finite_fraction 0.957).
  Masks are *overlaid* on the native NaN cells: ``masking.apply_mask`` sets
  the injected cells to NaN and leaves every native gap untouched, which is
  already the exact semantics of the main pipeline (no prefill anywhere), so
  no extension of the masking code was needed.  The recorded ``mask`` of an
  episode (``np.isnan(masked)``) is the union of native and injected gaps.
* ``Solar`` has no original timestamps; the seasonal period 144 follows the
  registered 10-minute frequency, as recorded in the provenance contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from introact_ts.v44 import masking as M
from introact_ts.v44 import protocol as P
from introact_ts.v44 import registry as R
from introact_ts.v44.splits import ParentWindow
from introact_ts.v46.grid import EpisodeSpec, episode_id

REGISTRY_PATH = "configs/v54/confirmatory_registry.json"

#: Confirmatory blocks.  Mirrors the main grid minus the severity-robustness
#: blocks (test30/test50) and the second bank realisation (bankx2).
BLOCKS = ("bankx", "train_eval", "test", "test_m2", "test_m3")

#: Same seed rule as the main grid: m2/m3 re-derive masks from +1/+2.
MASK_SEED = {"test_m2": P.PROTOCOL_SEED + 1, "test_m3": P.PROTOCOL_SEED + 2}


def mask_seed_of(block: str) -> int:
    return MASK_SEED.get(block, P.PROTOCOL_SEED)


#: TRAIN is split by origin time; the bank gets the earlier parents.
BANK_FRACTION = 0.80

#: bankx enumerates the full severity ladder exactly as on the main set, so
#: the confirmatory bank carries the same support; the evaluation blocks run
#: the main severity only.
BLOCK_SEVERITIES = {
    "bankx": P.SEVERITIES,
    "train_eval": (P.MAIN_SEVERITY,),
    "test": (P.MAIN_SEVERITY,),
    "test_m2": (P.MAIN_SEVERITY,),
    "test_m3": (P.MAIN_SEVERITY,),
}


@dataclass(frozen=True)
class ConfirmSource:
    source: str
    path: str
    columns: int
    target_channel: int
    split_bounds: dict
    frequency: str
    seasonal_period: int
    file_sha256: str


def load_registry(root: str | Path) -> dict:
    return json.loads((Path(root) / REGISTRY_PATH).read_text())


def source_names(root: str | Path) -> list[str]:
    """The confirmatory sources, in registry order."""
    return [s["source"] for s in load_registry(root)["sources"]]


def source_registry(root: str | Path) -> dict[str, ConfirmSource]:
    registry: dict[str, ConfirmSource] = {}
    for info in load_registry(root)["sources"]:
        registry[info["source"]] = ConfirmSource(
            source=info["source"],
            path=info["path"],
            columns=int(info["columns"]),
            target_channel=int(info.get("target_channel", 0)),
            split_bounds={k: tuple(v) for k, v in info["split_bounds"].items()},
            frequency=info.get("frequency", "unknown"),
            seasonal_period=int(info["seasonal_period"]),
            file_sha256=info["file_sha256"],
        )
    return registry


# --------------------------------------------------------------------- parents

def _tile(source: str, start: int, end: int, *, span: int) -> list[ParentWindow]:
    out: list[ParentWindow] = []
    read_start = start
    while read_start + span <= end:
        out.append(ParentWindow(
            source=source, parent=f"{source}:{read_start}:{read_start + span}",
            read_start=read_start, origin=read_start + P.CONTEXT,
            max_target_end=read_start + span, role="train"))
        read_start += P.PARENT_STRIDE
    return out


def train_parents(root: str | Path) -> list[ParentWindow]:
    """TRAIN parents: ``train`` and ``dev`` segments tiled at the frozen stride.

    Each segment is tiled from its own start, matching how the r5
    ``windows_metadata`` were built for the main sources, and the latest
    parent of each source is dropped as the purge buffer against TEST,
    matching ``v46.grid.train_parents``.
    """
    registry = source_registry(root)
    span = P.CONTEXT + max(P.HORIZONS)
    out: list[ParentWindow] = []
    for name in source_names(root):
        info = registry[name]
        parents = [w for seg in ("train", "dev")
                   for w in _tile(name, info.split_bounds[seg][0],
                                  info.split_bounds[seg][1], span=span)]
        out.extend(parents[:-1])
    return out


def test_parents(root: str | Path, *, stride: int = P.PARENT_STRIDE) -> list[ParentWindow]:
    """TEST windows, tiled from the start of the held-out region."""
    registry = source_registry(root)
    span = P.CONTEXT + max(P.HORIZONS)
    out: list[ParentWindow] = []
    for name in source_names(root):
        info = registry[name]
        out.extend(_tile(name, info.split_bounds["calibration"][0],
                         info.split_bounds["test"][1], span=span))
    return out


#: The densified bank block draws the same TRAIN parents as ``bank``
#: (same alias as ``v46.grid.BANK_ALIAS``).
BANK_ALIAS = {"bankx": "bank"}


def parents_of(root: str | Path, block: str) -> list[ParentWindow]:
    if block.startswith("test"):
        return test_parents(root)
    train = train_parents(root)
    assignment = assign_train(train)
    return [p for p in train if assignment[p.parent] == BANK_ALIAS.get(block, block)]


def assign_train(parents: list[ParentWindow]) -> dict[str, str]:
    """Split TRAIN by origin time inside each source: bank first, then TRAIN-eval.

    Identical rule to ``v46.grid.assign_train``.
    """
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
    train_end: dict[str, int] = {}
    test_start: dict[str, int] = {}
    for p in train:
        train_end[p.source] = max(train_end.get(p.source, 0), p.max_target_end)
    for p in test:
        test_start[p.source] = min(test_start.get(p.source, 10 ** 12), p.read_start)
    gaps = {}
    for source in source_names(root):
        gap = test_start[source] - train_end[source]
        if gap < 0:
            raise ValueError(f"TRAIN and TEST rows overlap on {source}: gap {gap}")
        gaps[source] = int(gap)
    assignment = assign_train(train)
    for source in source_names(root):
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
    """The frozen episode list of one confirmatory block, in source/time order."""
    if block not in BLOCKS:
        raise ValueError(f"unregistered confirmatory block {block!r}")
    root = Path(root)
    registry = source_registry(root)
    parents = parents_of(root, block)
    levels = severities if severities is not None else BLOCK_SEVERITIES[block]
    specs: list[EpisodeSpec] = []
    for parent in sorted(parents, key=lambda p: (p.source, p.read_start)):
        info = registry[parent.source]
        for horizon in horizons:
            if parent.origin + horizon > parent.max_target_end:
                continue
            for pattern in P.PATTERNS:
                realisation = ("" if mask_seed_of(block) == P.PROTOCOL_SEED
                               else f"|r{mask_seed_of(block) - P.PROTOCOL_SEED}")
                for severity in levels:
                    specs.append(EpisodeSpec(
                        episode_id=episode_id(parent.source, parent.parent,
                                              horizon, pattern, severity) + realisation,
                        source=parent.source, parent=parent.parent,
                        origin=int(parent.origin), read_start=int(parent.read_start),
                        horizon=int(horizon), pattern=pattern,
                        severity=float(severity),
                        severity_source="main",
                        block=block, period=info.seasonal_period,
                        n_channels=int(info.columns)))
    return specs


# ---------------------------------------------------------------------- reading

def _read_windows_npz(root: Path, info: ConfirmSource, windows: list[ParentWindow],
                      *, horizon: int, context: int
                      ) -> Iterator[tuple[ParentWindow, np.ndarray, np.ndarray]]:
    """Slice windows out of an npz container; native NaN cells pass through."""
    path = Path(root) / info.path
    if not path.exists():
        raise FileNotFoundError(f"missing source container {path}")
    span = context + horizon
    with np.load(path, allow_pickle=False) as store:
        values = np.asarray(store["values"], dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != info.columns:
        raise ValueError(f"unexpected npz shape {values.shape} for {info.source}")
    if np.isinf(values).any():
        raise ValueError(f"infinity in {info.source}")
    for window in sorted(windows, key=lambda w: w.read_start):
        if window.origin + horizon > window.max_target_end:
            raise ValueError(f"horizon {horizon} exceeds window {window.parent}")
        if window.read_start < 0 or window.read_start + span > values.shape[0]:
            raise ValueError(f"window {window.parent} exceeds {info.source} rows")
        block = values[window.read_start:window.read_start + span]
        yield window, block[:context].copy(), block[context:, info.target_channel].copy()


def read_windows(root: str | Path, info: ConfirmSource,
                 windows: list[ParentWindow], *, horizon: int,
                 context: int = P.CONTEXT
                 ) -> Iterator[tuple[ParentWindow, np.ndarray, np.ndarray]]:
    """Dispatch to the container reader; gzip/csv sources use the frozen reader."""
    if str(info.path).endswith(".npz"):
        yield from _read_windows_npz(Path(root), info, windows,
                                     horizon=horizon, context=context)
    else:
        yield from R.read_windows(root, info, windows,
                                  horizon=horizon, context=context)


def iter_panels(root: str | Path, specs: list[EpisodeSpec]
                ) -> Iterator[tuple[EpisodeSpec, np.ndarray, np.ndarray, np.ndarray]]:
    """Yield ``(spec, raw_context, masked_panel, future)`` for a block.

    Same contract as ``v46.grid.iter_panels``: the raw context travels
    alongside the masked one because the metric denominators are computed on
    the untouched series.  The injected mask is overlaid on any native NaN
    cells (US_Term_Structure); nothing is prefilled.
    """
    root = Path(root)
    registry = source_registry(root)
    windows_by_name: dict[str, ParentWindow] = {}
    by_source: dict[str, list[EpisodeSpec]] = {}
    for spec in specs:
        by_source.setdefault(spec.source, []).append(spec)
        windows_by_name.setdefault(spec.parent, ParentWindow(
            source=spec.source, parent=spec.parent, read_start=spec.read_start,
            origin=spec.origin, max_target_end=spec.origin + max(P.HORIZONS),
            role="train"))

    for source, source_specs in sorted(by_source.items()):
        info = registry[source]
        for horizon in sorted({s.horizon for s in source_specs}):
            subset = [s for s in source_specs if s.horizon == horizon]
            names = sorted({s.parent for s in subset},
                           key=lambda n: windows_by_name[n].read_start)
            windows = [windows_by_name[n] for n in names]
            index: dict[tuple[str, str], list[EpisodeSpec]] = {}
            for spec in subset:
                index.setdefault((spec.parent, spec.pattern), []).append(spec)
            for window, context, future in read_windows(
                    root, info, windows, horizon=horizon):
                for pattern in P.PATTERNS:
                    for spec in index.get((window.parent, pattern), []):
                        mask = M.build_mask(source, window.parent, window.origin,
                                            horizon, pattern, spec.severity,
                                            length=context.shape[0],
                                            n_channels=context.shape[1],
                                            protocol_seed=mask_seed_of(spec.block))
                        yield spec, context, M.apply_mask(context, mask), future


def summary(root: str | Path) -> dict:
    """Block sizes and the purge audit, for the confirmatory freeze record."""
    out = {}
    for block in BLOCKS:
        parents = parents_of(root, block)
        specs = episode_specs(root, block)
        per_source: dict[str, int] = {}
        for p in parents:
            per_source[p.source] = per_source.get(p.source, 0) + 1
        out[block] = {"parents": len(parents), "episodes": len(specs),
                      "severities": [float(s) for s in BLOCK_SEVERITIES[block]],
                      "mask_seed": mask_seed_of(block),
                      "sources": len(per_source),
                      "per_source": dict(sorted(per_source.items()))}
    out["purge_audit"] = audit_purge(root)
    return out
