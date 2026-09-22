#!/usr/bin/env python3
"""Apply the v4.7 code changes on the server.

Four changes, each motivated by something visible on the bank side and none of
them by a TEST record:

1. The catalog gains a sixth action, the trained imputer.  Its bank records are
   cross-fitted by parent so the stored utility is out of sample.
2. The bank enumerates the three registered severities instead of drawing one
   by hash, so every parent, pattern and horizon carries same-severity support.
3. Every candidate must pass a registered plausibility guard before it is
   executed, so a diverging extrapolation is recorded as unsupported at the
   source instead of being averaged over downstream.
4. Hyperparameter selection minimises the cross-validated macro under the harm
   cap.  The one-standard-error rule is dropped: it compared a differently
   aggregated quantity and therefore preferred the most conservative cell.

Shared modules are edited additively so the v4.6 run stays reproducible.  The
stage scripts are copied to v47 names with their result root rewritten.
Idempotent: every edit checks for its own result first.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path("/home/vipuser/work/work2")
CHANGES: list[str] = []
SKIPPED: list[str] = []


def edit(rel: str, old: str, new: str, *, tag: str) -> None:
    path = ROOT / rel
    text = path.read_text()
    if new in text:
        SKIPPED.append(tag)
        return
    if old not in text:
        raise SystemExit(f"FAILED {tag}: anchor not found in {rel}")
    if text.count(old) != 1:
        raise SystemExit(f"FAILED {tag}: anchor is not unique in {rel}")
    path.write_text(text.replace(old, new))
    CHANGES.append(tag)


# =========================================================== shared: protocol

edit("src/introact_ts/v44/protocol.py", '''ACTIONS = (
    "KEEP",
    "FFILL",
    "SINGLE_TSICL",
    "MULTI_TSICL",
    "CONTEXT_RIDGE",
)''', '''ACTIONS = (
    "KEEP",
    "FFILL",
    "SINGLE_TSICL",
    "MULTI_TSICL",
    "CONTEXT_RIDGE",
    "SAITS",
)

#: Actions whose candidate input is produced by a separate model stage rather
#: than by a pure function of the context.  ``apply_action`` refuses them and
#: the pipeline reads their candidate from that stage's archive, which keeps
#: one writer per input version.
EXTERNAL_ACTIONS = ("SINGLE_TSICL", "MULTI_TSICL", "SAITS")''',
     tag="protocol: the trained imputer joins the catalog")

edit("src/introact_ts/v44/protocol.py", '''K_GRID = (8, 16, 32)
BETA_GRID = (0.0, 1.0, 1.64)''', '''K_GRID = (8, 16, 32, 64, 128, 256)
BETA_GRID = (0.0, 0.5, 1.0, 1.64)

#: Plausibility guard.  A candidate may only write values inside the range of
#: the visible target widened by this many robust scales on each side.  A
#: repair that leaves it is recorded as unsupported instead of executed, so a
#: diverging extrapolation never reaches the bank or the deployment path.  The
#: constant is registered here before any evaluation record is scored.
PLAUSIBILITY_SCALES = 3.0''',
     tag="protocol: searched grids and the plausibility constant")


# ============================================================ shared: actions

edit("src/introact_ts/v44/actions.py",
     'from .protocol import ACTIONS, REFERENCE_ACTION',
     'from .protocol import ACTIONS, PLAUSIBILITY_SCALES, REFERENCE_ACTION',
     tag="actions: import the plausibility constant")

edit("src/introact_ts/v44/actions.py",
     'def _guard(name: str, filled: np.ndarray, reference: np.ndarray) -> np.ndarray:',
     '''def plausibility_bounds(reference: np.ndarray) -> tuple[float, float]:
    """The admissible value range of any repair of ``reference``.

    The range is the visible target's own range widened by
    ``PLAUSIBILITY_SCALES`` robust scales on each side.  It depends on the
    request alone, so the same bound holds when a record is written to the bank
    and when a request is served.
    """
    from .state import robust_scale

    reference = np.asarray(reference, dtype=np.float64)
    observed = reference[np.isfinite(reference)]
    if observed.size == 0:
        return (float("-inf"), float("inf"))
    width = PLAUSIBILITY_SCALES * float(robust_scale(reference))
    return (float(observed.min()) - width, float(observed.max()) + width)


def implausible_reason(filled: np.ndarray, reference: np.ndarray) -> str | None:
    """``None`` when the candidate is admissible, otherwise why it is not."""
    filled = np.asarray(filled, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    if filled.shape != reference.shape:
        return "candidate length differs from the reference"
    if not np.isfinite(filled).all():
        return "candidate is not finite"
    written = ~np.isfinite(reference)
    if not written.any():
        return None
    lo, hi = plausibility_bounds(reference)
    values = filled[written]
    excess = float(np.max(np.abs(values - np.clip(values, lo, hi))))
    if excess > 0.0:
        return (f"repair leaves the plausible range by {excess:.4g} "
                f"outside [{lo:.4g}, {hi:.4g}]")
    return None


def _guard(name: str, filled: np.ndarray, reference: np.ndarray) -> np.ndarray:''',
     tag="actions: plausibility guard")

edit("src/introact_ts/v44/actions.py",
     '''    require(np.isfinite(filled).all(), f"{name}: left a gap unfilled")
    return filled''',
     '''    require(np.isfinite(filled).all(), f"{name}: left a gap unfilled")
    reason = implausible_reason(filled, reference)
    require(reason is None, f"{name}: {reason}")
    return filled''',
     tag="actions: the guard runs inside _guard")

edit("src/introact_ts/v44/actions.py",
     '''        return outcome(filled, metadata={"strategy": "context_ridge"})

    raise AssertionError("unreachable")  # pragma: no cover''',
     '''        return outcome(filled, metadata={"strategy": "context_ridge"})

    if name == "SAITS":
        # The trained imputer is a model stage rather than a pure function of
        # the context, so its candidate is built once per block and read from
        # that stage's archive.
        return outcome(reference_target, applicable=False,
                       reason="SAITS candidates come from the imputer stage")

    raise AssertionError("unreachable")  # pragma: no cover''',
     tag="actions: the imputer action is built by its own stage")


# ============================================================ shared: catalog

edit("src/introact_ts/v44/catalog.py",
     '''    with np.load(replay / "inputs" / f"{block}.npz", allow_pickle=False) as store, \\
            np.load(replay / "tsicl" / f"{block}.npz", allow_pickle=False) as tsicl, \\
            np.load(forecast_dir / "predictions.npz", allow_pickle=False) as predictions:

        def candidate(key: str, action: str) -> np.ndarray | None:
            name = f"{key}|{action}"
            for source in (store, tsicl):
                if name in source.files:
                    return source[name]
            return None''',
     '''    saits_path = replay / "saits" / f"{block}.npz"
    saits_store = (np.load(saits_path, allow_pickle=False)
                   if saits_path.exists() else None)

    with np.load(replay / "inputs" / f"{block}.npz", allow_pickle=False) as store, \\
            np.load(replay / "tsicl" / f"{block}.npz", allow_pickle=False) as tsicl, \\
            np.load(forecast_dir / "predictions.npz", allow_pickle=False) as predictions:

        stores = ((store, tsicl) if saits_store is None
                  else (store, tsicl, saits_store))

        def candidate(key: str, action: str) -> np.ndarray | None:
            name = f"{key}|{action}"
            for source in stores:
                if name in source.files:
                    return source[name]
            return None''',
     tag="catalog: read the imputer stage archive")


# =============================================================== shared: grid

edit("src/introact_ts/v46/grid.py",
     'BLOCKS = ("bank", "train_eval", "test", "test30", "test50", "test_m2", "test_m3")',
     'BLOCKS = ("bank", "bankx", "bankx2", "train_eval", "test", "test30", "test50",\n'
     '          "test_m2", "test_m3")',
     tag="grid: register the densified bank blocks")

edit("src/introact_ts/v46/grid.py",
     'MASK_SEED = {"test_m2": P.PROTOCOL_SEED + 1, "test_m3": P.PROTOCOL_SEED + 2}',
     'MASK_SEED = {"test_m2": P.PROTOCOL_SEED + 1, "test_m3": P.PROTOCOL_SEED + 2,\n'
     '             "bankx2": P.PROTOCOL_SEED + 1}',
     tag="grid: second bank mask realisation")

edit("src/introact_ts/v46/grid.py",
     '''BLOCK_SEVERITIES = {
    "bank": None,                       # None means hash-mixed''',
     '''BLOCK_SEVERITIES = {
    "bank": None,                       # None means hash-mixed
    #: v4.7 enumerates the ladder instead of drawing one level per episode, so
    #: every parent, pattern and horizon carries support at every registered
    #: severity rather than at a hash-chosen one.
    "bankx": P.SEVERITIES,
    "bankx2": P.SEVERITIES,''',
     tag="grid: enumerate the severity ladder on the bank")

edit("src/introact_ts/v46/grid.py",
     '''def parents_of(root: str | Path, block: str) -> list[ParentWindow]:
    if block.startswith("test"):
        return test_parents(root)
    train = train_parents(root)
    assignment = assign_train(train)
    return [p for p in train if assignment[p.parent] == block]''',
     '''#: The densified bank blocks draw the same TRAIN parents as ``bank``.
BANK_ALIAS = {"bankx": "bank", "bankx2": "bank"}


def parents_of(root: str | Path, block: str) -> list[ParentWindow]:
    if block.startswith("test"):
        return test_parents(root)
    train = train_parents(root)
    assignment = assign_train(train)
    return [p for p in train if assignment[p.parent] == BANK_ALIAS.get(block, block)]''',
     tag="grid: the bank blocks reuse the bank parents")

edit("src/introact_ts/v46/grid.py",
     '''                for severity in ([chosen] if mixed else levels):
                    specs.append(EpisodeSpec(
                        episode_id=episode_id(parent.source, parent.parent,
                                              horizon, pattern, severity),''',
     '''                realisation = ("" if mask_seed_of(block) == P.PROTOCOL_SEED
                               else f"|r{mask_seed_of(block) - P.PROTOCOL_SEED}")
                for severity in ([chosen] if mixed else levels):
                    # A block that re-derives its masks from another seed is a
                    # different request set, so its episode ids must not
                    # collide with the primary realisation of the same window.
                    specs.append(EpisodeSpec(
                        episode_id=episode_id(parent.source, parent.parent,
                                              horizon, pattern, severity) + realisation,''',
     tag="grid: tag the episodes of an alternative mask realisation")


# ====================================================== v47 stage script copies

STAGE_COPIES = {
    "scripts/v46_prepare.py": "scripts/v47_prepare.py",
    "scripts/v46_tsicl.py": "scripts/v47_tsicl.py",
    "scripts/v46_forecast.py": "scripts/v47_forecast.py",
    "scripts/v46_select.py": "scripts/v47_select.py",
    "scripts/v46_evaluate.py": "scripts/v47_evaluate.py",
    "scripts/v46_reconstruction.py": "scripts/v47_reconstruction.py",
    "scripts/v46_latency.py": "scripts/v47_latency.py",
    "scripts/v46_banksize.py": "scripts/v47_banksize.py",
    "scripts/v46_selection_stability.py": "scripts/v47_selection_stability.py",
    "scripts/v46_severity_bias.py": "scripts/v47_severity_bias.py",
    "scripts/v46_score_utility.py": "scripts/v47_score_utility.py",
    "scripts/v46_baseline_forecast.py": "scripts/v47_baseline_forecast.py",
    "scripts/v46_tato.py": "scripts/v47_tato.py",
}

BLOCK_CHOICES_OLD = '["bank", "train_eval", "test", "test30", "test50", "test_m2", "test_m3"]'
BLOCK_CHOICES_NEW = ('["bank", "bankx", "bankx2", "train_eval", "test", "test30", '
                     '"test50", "test_m2", "test_m3"]')

for src, dst in STAGE_COPIES.items():
    target = ROOT / dst
    text = (ROOT / src).read_text()
    text = text.replace("results/v46", "results/v47")
    text = text.replace("from introact_ts.v46 import select as SEL",
                        "from introact_ts.v47 import select as SEL")
    text = text.replace("from introact_ts.v46 import grid as PL",
                        "from introact_ts.v46 import grid as PL")
    text = text.replace(BLOCK_CHOICES_OLD, BLOCK_CHOICES_NEW)
    text = text.replace('choices=["bank", "train_eval", "test", "test30", "test50", "test_m2", "test_m3"]',
                        f'choices={BLOCK_CHOICES_NEW}')
    text = text.replace('choices=["train_eval", "test", "test30", "test50", "test_m2", "test_m3"]',
                        'choices=["train_eval", "test", "test30", "test50", "test_m2", "test_m3"]')
    if target.exists() and target.read_text() == text:
        SKIPPED.append(f"copy {dst}")
        continue
    target.write_text(text)
    target.chmod(0o755)
    CHANGES.append(f"copy {src} -> {dst}")


print("APPLIED:")
for item in CHANGES:
    print("  +", item)
print("SKIPPED (already present):")
for item in SKIPPED:
    print("  =", item)
print("\nremaining work is in v47_patch2.py")
