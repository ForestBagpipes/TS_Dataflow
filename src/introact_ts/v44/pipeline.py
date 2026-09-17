"""Shared replay-input pipeline for v4.4 stages A/B/C.

One place builds the deterministic masked panel of an episode, so the CPU
preparation stage, the TS-ICL stage and the forecast stage cannot disagree
about what the mask was.  Every stage rebuilds the panel from the frozen
identity tuple rather than passing panels between processes: the panels are
large (Traffic has 862 channels), and a mask that is a pure function of its
identity does not need to be shipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from . import masking as M
from . import protocol as P
from . import registry as R
from . import splits as S


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


def episode_specs(root: str | Path, block: str, *,
                  horizons=P.HORIZONS) -> list[EpisodeSpec]:
    """The frozen episode list of one block, in source/time order."""
    root = Path(root)
    registry = R.source_registry(root)
    parents = R.train_parents(root)
    assignment = S.assign_splits(parents)
    grid = S.episode_grid(parents, assignment, block=block, horizons=horizons)
    specs = []
    for episode in grid:
        info = registry[episode["source"]]
        specs.append(EpisodeSpec(
            episode_id=episode_id(episode["source"], episode["parent"],
                                  episode["horizon"], episode["pattern"],
                                  episode["severity"]),
            source=episode["source"],
            parent=episode["parent"],
            origin=int(episode["origin"]),
            read_start=int(episode["read_start"]),
            horizon=int(episode["horizon"]),
            pattern=episode["pattern"],
            severity=float(episode["severity"]),
            severity_source=episode["severity_source"],
            block=block,
            period=P.seasonal_period(episode["source"]),
            n_channels=int(info.columns),
        ))
    return specs


def iter_panels(root: str | Path, specs: list[EpisodeSpec]
                ) -> Iterator[tuple[EpisodeSpec, np.ndarray, np.ndarray, np.ndarray]]:
    """Yield ``(spec, raw_context, masked_panel, future)``.

    The raw context is yielded alongside the masked one so the metrics
    denominators can be computed from the untouched series: a denominator that
    moved with the mask would make two patterns of the same window
    incomparable.

    Streams each source once per horizon; the mask is rebuilt from the spec so
    two stages reading the same spec are guaranteed to see the same panel.
    """
    root = Path(root)
    registry = R.source_registry(root)
    parents = R.train_parents(root)
    window_map = {(p.source, p.parent): p for p in parents}

    by_source: dict[str, list[EpisodeSpec]] = {}
    for spec in specs:
        by_source.setdefault(spec.source, []).append(spec)

    for source, source_specs in sorted(by_source.items()):
        info = registry[source]
        for horizon in sorted({s.horizon for s in source_specs}):
            subset = [s for s in source_specs if s.horizon == horizon]
            names = sorted({s.parent for s in subset},
                           key=lambda n: window_map[(source, n)].read_start)
            windows = [window_map[(source, name)] for name in names]
            index: dict[tuple[str, str], list[EpisodeSpec]] = {}
            for spec in subset:
                index.setdefault((spec.parent, spec.pattern), []).append(spec)
            for window, context, future in R.read_windows(
                    root, info, windows, horizon=horizon):
                for pattern in P.PATTERNS:
                    matching = index.get((window.parent, pattern))
                    if not matching:
                        continue
                    for spec in matching:
                        mask = M.build_mask(source, window.parent, window.origin,
                                            horizon, pattern, spec.severity,
                                            length=context.shape[0],
                                            n_channels=context.shape[1])
                        masked = M.apply_mask(context, mask)
                        yield spec, context, masked, future
