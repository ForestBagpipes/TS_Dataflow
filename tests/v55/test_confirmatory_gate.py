"""The confirmation TEST must stay closed if code drifted after freezing."""

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import v55_confirmatory as confirm


def test_code_drift_is_rejected_before_loading_test(tmp_path, monkeypatch):
    out = tmp_path / "results/v55/confirmatory"
    out.mkdir(parents=True)
    check = out / "check_report.json"
    check.parent.mkdir(parents=True, exist_ok=True)
    check.write_text(json.dumps({"all_passed": True}))
    (out / "freeze_bolt.json").write_text(json.dumps({
        "test_records_read": 0, "code_sha256": {"wrong": "hash"},
        "selection": {"keep_only": True, "selected": None},
    }))
    source = tmp_path / "src/introact_ts/v55/select.py"
    source.parent.mkdir(parents=True)
    source.write_text("# frozen source stub\n")
    monkeypatch.setattr(confirm, "OUT", out)
    monkeypatch.setattr(confirm, "catalogs", lambda *_args: pytest.fail(
        "confirmation TEST was read before the code hash check"))
    with pytest.raises(SystemExit, match="TEST remains closed"):
        confirm.evaluate(tmp_path, "bolt")
