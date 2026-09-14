"""Original-row splitting and as-of reads; never select origins using labels."""
from dataclasses import dataclass, replace
import numpy as np
from .schemas import Episode, require


def split_intervals(length, ratios=(.60, .15, .10, .15)):
    require(length > 0 and len(ratios) == 4 and all(r > 0 for r in ratios)
            and abs(sum(ratios)-1) < 1e-12, "invalid split specification")
    edges = [0] + [int(length*r) for r in np.cumsum(ratios)[:-1]] + [length]
    return dict(zip(("train", "dev", "calibration", "test"), zip(edges[:-1], edges[1:])))


def origin_indices(length, context=512, horizon=32, stride=None):
    require(context > 0 and horizon > 0, "invalid context/horizon")
    stride = context+horizon if stride is None else stride
    require(stride > 0, "invalid stride")
    return {s: list(range(lo+context, hi-horizon+1, stride))
            for s, (lo, hi) in split_intervals(length).items() if s in ("train", "dev")}


@dataclass(frozen=True)
class ReadInterval:
    source: str
    panel: str
    parent_group: str
    split: str
    start: int
    stop: int  # exclusive, includes every context/future/auxiliary read


def audit_reads(records):
    parents = {}
    for r in records:
        require(r.start >= 0 and r.stop > r.start, "invalid read interval")
        require(r.split in ("train", "dev", "calibration", "test"), "invalid split")
        key = (r.source, r.panel, r.parent_group)
        require(key not in parents or parents[key] == r.split, "parent crosses split")
        parents[key] = r.split
    for i, a in enumerate(records):
        for b in records[i+1:]:
            if (a.source, a.panel) == (b.source, b.panel) and a.split != b.split:
                require(max(a.start, b.start) >= min(a.stop, b.stop), "synchronous interval overlap")


def build_episode(*, uid, source, panel, parent_group, split, target_channel,
                  timestamps, target, covariates, availability, raw_start,
                  context_end, horizon, split_bounds):
    """Accept only the already-sliced raw context, not a full parent array."""
    lo, hi = split_bounds
    require(split in ("train", "dev"), "development reader refuses held-out splits")
    require(lo <= raw_start < context_end and context_end+horizon <= hi, "read crosses split")
    x, z = np.array(target, copy=True), np.array(covariates, copy=True)
    t, a = np.asarray(timestamps), np.asarray(availability)
    require(t.ndim == 1 and len(t) > 0 and a.shape == (len(t), 1+z.shape[1]), "availability shape")
    x[a[:, 0] > t[-1]] = np.nan
    z[a[:, 1:] > t[-1]] = np.nan
    return Episode(uid, source, panel, parent_group, split, target_channel, raw_start,
                   context_end, horizon, t, x, z, a)


def as_of(episode, cutoff, horizon=32):
    """cutoff is relative and exclusive; no history before this context."""
    require(0 < cutoff < len(episode.target) and cutoff+horizon <= len(episode.target), "invalid historical origin")
    t = episode.timestamps[:cutoff]
    x, z = episode.target[:cutoff].copy(), episode.covariates[:cutoff].copy()
    a = episode.availability[:cutoff]
    x[a[:, 0] > t[-1]] = np.nan
    z[a[:, 1:] > t[-1]] = np.nan
    return replace(episode, uid=f"{episode.uid}:asof:{cutoff}:{horizon}",
                   context_end=episode.raw_start+cutoff, horizon=horizon,
                   timestamps=t, target=x, covariates=z, availability=a)
