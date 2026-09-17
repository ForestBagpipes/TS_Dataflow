"""Deterministic missingness pattern generators (task book §8, §9).

Four patterns, three severities, one seed namespace.  Every mask is a pure
function of the frozen identity tuple ``(source, parent, origin, horizon,
pattern, protocol_seed)`` plus the severity; nothing here looks at the data
values, at a model, or at a future label.

The generators never *decide* anything after a model has run: the task book
requires the mask to be frozen before any model execution, so this module is
imported by the replay builder and by the unit tests, never by the selector.
"""

from __future__ import annotations

import numpy as np

from .protocol import CONTEXT, PATTERNS, PROTOCOL_SEED, SEVERITIES, mask_seed

#: Missing runs are drawn from this many candidate runs at most, so a
#: severity's budget is spread over a bounded number of blocks.
MAX_BLOCKS = 3


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _severity_budget(severity: float, length: int) -> int:
    """Number of missing points implied by a severity, at least one."""
    if not (0.0 < severity < 1.0):
        raise ValueError(f"severity must be in (0, 1), got {severity!r}")
    budget = int(round(severity * length))
    if budget < 1:
        raise ValueError("severity implies an empty mask")
    if budget >= length:
        raise ValueError("severity would remove the whole context")
    return budget


def _split_budget(budget: int, n_blocks: int, rng: np.random.Generator) -> list[int]:
    """Split a point budget into ``n_blocks`` positive parts."""
    n_blocks = max(1, min(n_blocks, budget))
    parts = [1] * n_blocks
    remaining = budget - n_blocks
    if remaining > 0:
        weights = rng.random(n_blocks) + 0.5
        weights = weights / weights.sum()
        extra = np.floor(weights * remaining).astype(int)
        for i in range(remaining - int(extra.sum())):
            extra[i % n_blocks] += 1
        parts = [p + int(e) for p, e in zip(parts, extra)]
    return parts


def _block_layout(budget: int, length: int, rng: np.random.Generator,
                  max_blocks: int = MAX_BLOCKS) -> list[tuple[int, int]]:
    """Non-overlapping half-open ``(lo, hi)`` runs totalling exactly ``budget``.

    Built by composing the *leftover* ``length - budget`` free points into
    ``n_blocks + 1`` gaps around the runs.  That makes the total exact by
    construction instead of by retry, which matters because the severity
    ladder is part of the frozen protocol.
    """
    n_blocks = int(rng.integers(1, max_blocks + 1))
    parts = _split_budget(budget, n_blocks, rng)
    n_blocks = len(parts)
    leftover = length - budget
    if leftover < 0:
        raise ValueError("severity budget exceeds the context length")
    if leftover > 0:
        gaps = rng.multinomial(leftover, np.full(n_blocks + 1, 1.0 / (n_blocks + 1)))
    else:
        gaps = np.zeros(n_blocks + 1, dtype=np.int64)

    runs: list[tuple[int, int]] = []
    position = int(gaps[0])
    for i, size in enumerate(parts):
        runs.append((position, position + size))
        position += size + int(gaps[i + 1])
    assert position == length, "block layout must tile the leftover exactly"
    return runs


def _runs_to_mask(runs: list[tuple[int, int]], length: int) -> np.ndarray:
    mask = np.zeros(length, dtype=bool)
    for lo, hi in runs:
        mask[lo:hi] = True
    return mask


def target_mask(pattern: str, severity: float, length: int, seed: int) -> np.ndarray:
    """Boolean mask over the target channel; ``True`` means *missing*."""
    if pattern not in PATTERNS:
        raise ValueError(f"unregistered pattern {pattern!r}")
    budget = _severity_budget(severity, length)
    rng = _rng(seed)

    if pattern == "P1_point":
        positions = rng.choice(length, size=budget, replace=False)
        mask = np.zeros(length, dtype=bool)
        mask[positions] = True
        return mask

    if pattern == "P2_target_block":
        return _runs_to_mask(_block_layout(budget, length, rng), length)

    if pattern == "P3_shared_block":
        # Same layout rule, but the *same* layout is applied to every
        # observable channel, so the missingness is shared rather than
        # target-only.  The returned mask is the target-channel view; the
        # caller uses ``shared_channels`` to build the 2-D mask.
        return _runs_to_mask(_block_layout(budget, length, rng), length)

    if pattern == "P4_tail":
        # The last ``budget`` points before the forecast origin.
        return _runs_to_mask([(length - budget, length)], length)

    raise AssertionError("unreachable")  # pragma: no cover


def shared_channels(pattern: str) -> tuple[int, ...] | None:
    """Channel indices sharing the target mask, or ``None`` for target-only.

    ``None`` means "only channel 0 is masked"; a tuple means "these channels,
    including channel 0, carry the identical block layout".
    """
    if pattern == "P3_shared_block":
        return (0,)
    return None


def build_mask(source: str, parent: str, origin: int, horizon: int,
               pattern: str, severity: float, *,
               length: int = CONTEXT, n_channels: int = 1,
               protocol_seed: int = PROTOCOL_SEED) -> np.ndarray:
    """2-D ``(length, n_channels)`` boolean mask; ``True`` means missing.

    Channel 0 is always the target channel.  For ``P3_shared_block`` the same
    run layout is written to every channel, so the missingness is genuinely
    shared across the observable panel rather than target-only.
    """
    if n_channels < 1:
        raise ValueError("n_channels must be >= 1")
    seed = mask_seed(source, parent, origin, horizon, pattern, protocol_seed)
    target = target_mask(pattern, severity, length, seed)
    mask = np.zeros((length, n_channels), dtype=bool)
    mask[:, 0] = target
    if pattern == "P3_shared_block":
        mask[:] = target[:, None]
    return mask


def mask_identity(source: str, parent: str, origin: int, horizon: int,
                  pattern: str, severity: float, *, length: int = CONTEXT,
                  n_channels: int = 1,
                  protocol_seed: int = PROTOCOL_SEED) -> dict:
    """Frozen provenance for one mask; stored on every replay record."""
    from .hashing import array_hash

    mask = build_mask(source, parent, origin, horizon, pattern, severity,
                      length=length, n_channels=n_channels,
                      protocol_seed=protocol_seed)
    return {
        "source": source,
        "parent": parent,
        "origin": int(origin),
        "horizon": int(horizon),
        "pattern": pattern,
        "severity": float(severity),
        "protocol_seed": int(protocol_seed),
        "length": int(length),
        "n_channels": int(n_channels),
        "seed": mask_seed(source, parent, origin, horizon, pattern, protocol_seed),
        "missing_count": int(mask[:, 0].sum()),
        "mask_hash": array_hash(mask),
    }


def apply_mask(context: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Return a copy of ``context`` with the masked cells set to NaN.

    ``context`` is ``(length, n_channels)``; ``mask`` is the same shape.
    """
    context = np.asarray(context, dtype=np.float64)
    mask = np.asarray(mask, dtype=bool)
    if context.shape != mask.shape:
        raise ValueError("context/mask shape mismatch")
    out = context.copy()
    out[mask] = np.nan
    return out


def mixed_severity(source: str, parent: str, origin: int, horizon: int,
                   pattern: str, *, severities=SEVERITIES,
                   protocol_seed: int = PROTOCOL_SEED) -> float:
    """Severity of one historical Replay-Fit episode, decided by hash (§9).

    The replay bank's support is mixed over the severity ladder; the choice is
    deterministic and independent of every result.  It lives in its own hash
    namespace (``:severity``) so that it can never collide with the mask seed.
    """
    import hashlib

    key = (f"{source}|{parent}|{int(origin)}|{int(horizon)}|{pattern}"
           f"|severity|{int(protocol_seed)}")
    seed = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:16], 16)
    return float(severities[seed % len(severities)])


def is_registered_severity(severity: float) -> bool:
    return any(abs(float(severity) - s) < 1e-12 for s in SEVERITIES)
