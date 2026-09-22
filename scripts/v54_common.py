#!/usr/bin/env python3
"""Shared plumbing for the v54 stage-4a recompute (protocol freeze 2026-09-22).

Every v54 stage reads the immutable v47 replay inputs (masked panels, candidate
inputs, prediction cache) and the v47 TATO records -- those depend on candidate
inputs only and do not change with the state definition.  Every v54 stage writes
under ``results/v54/`` (or ``configs/v54/`` for the parent manifest) and never
touches ``results/v47/``.

State semantics come from ``introact_ts.v44.state`` at load time
(``STATE_VERSION = "v54-full22"``); selection/scoring semantics come from
``introact_ts.v47.select`` (parent-clustered scoring, KEEP-only fallback).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from introact_ts.v44 import catalog as C
from introact_ts.v44 import state as ST

ROOT = Path(__file__).resolve().parent.parent
C.REPLAY = "results/v47/replay"
REPLAY_V47 = "results/v47/replay"
OUT = ROOT / "results/v54"

BACKBONES = ("bolt", "timesfm", "chronos2")
BANK_BLOCK = "bankx"
EVAL_BLOCKS = ("train_eval", "test", "test30", "test50", "test_m2", "test_m3")
SEED_BLOCKS = ("test", "test_m2", "test_m3")

assert ST.STATE_VERSION == "v54-full22", "v54 stages require the v54 state"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               allow_nan=False) + "\n")


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    return value


def load_catalogs(root: Path, block: str, backbone: str):
    return C.load_catalog(root, block, backbone)


def code_hashes(root: Path) -> dict:
    return {
        "src/introact_ts/v44/state.py": sha(root / "src/introact_ts/v44/state.py"),
        "src/introact_ts/v47/select.py": sha(root / "src/introact_ts/v47/select.py"),
    }
