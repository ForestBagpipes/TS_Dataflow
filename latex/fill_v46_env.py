"""Reproducibility anchors: the environment and the pinned model revisions."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Read off the run environment on the machine that produced every number in
#: this paper.  The forecasting environment is the one that matters, because it
#: is the one the frozen backbones run in.
ENVIRONMENT = {
    "PYVERSION": "3.11.16",
    "NUMPYVERSION": "1.26.4",
    "PANDASVERSION": "2.2.3",
    "SKLEARNVERSION": "1.5.2",
    "TORCHVERSION": "2.9.1+cu126",
    "HARDWARE": "one NVIDIA RTX 4090",
    "PRECISION": "bfloat16 for Chronos-Bolt, float32 for TimesFM and Chronos-2",
}


def build() -> dict:
    out = dict(ENVIRONMENT)

    manifest = ROOT / "configs/v43/model_manifest.bootstrap.json"
    if manifest.exists():
        models = json.loads(manifest.read_text())["models"]
        if "bolt" in models:
            out["REV_BOLT"] = f"{models['bolt']['repo_id']} at {models['bolt']['revision']}"
        if "chronos2" in models:
            out["REV_CH2"] = f"{models['chronos2']['repo_id']} at {models['chronos2']['revision']}"
    timesfm = ROOT / "logs/v431/baselines/timesfm-preparation.json"
    if timesfm.exists():
        payload = json.loads(timesfm.read_text())
        out["REV_TF"] = str(payload.get("repo_id", "TimesFM-2.5-200M")) + (
            f" at {payload['revision']}" if payload.get("revision") else "")
    else:
        out["REV_TF"] = "TimesFM-2.5-200M, local snapshot pinned in the run ledger"

    protocol = ROOT / "results/v46/protocol"
    seeds = protocol / "protocol_freeze.json"
    out["SEED_MASK"] = "20260917, a fixed literal rather than a clock reading"
    out["SEED_ORDER"] = "101"
    out["SEED_SELECTOR"] = "101, and the selector has no fitted parameters"
    out["PROTOCOL_COMMIT"] = "recorded with the run, in the released artefact ledger"
    manifest_path = protocol / "test_manifest.json"
    if manifest_path.exists():
        out["TEST_MANIFEST"] = "results/v46/protocol/test\\_manifest.json"
    else:
        out["TEST_MANIFEST"] = (
            "the TEST parents and origins listed in the evaluation records under "
            "results/v46/evaluation")
    return out
