#!/usr/bin/env python3
"""Run only v43 CPU contracts and record a gate bound to exact code/config."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import yaml
from introact_ts.v43.cli import atomic_json, code_manifest
from introact_ts.v43.data_io import file_hash
from introact_ts.v43.schemas import json_hash, require


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/v43/bootstrap.yaml")
    args = ap.parse_args()
    require(Path(sys.prefix).resolve() == Path("/home/vipuser/work2-envs/w2-core").resolve(), "use isolated core interpreter")
    config = yaml.safe_load(Path(args.config).read_text())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    out = Path("logs/v43/contracts") / stamp
    out.mkdir(parents=True, exist_ok=False)
    code = code_manifest()
    tests = {str(p): file_hash(p) for p in sorted(Path("tests/v43").rglob("*.py"))}
    start = time.perf_counter()
    with (out / "pytest.log").open("x") as log:
        result = subprocess.run([sys.executable, "-m", "pytest", "tests/v43", "-q", f"--junitxml={out / 'pytest.xml'}"],
                                stdout=log, stderr=subprocess.STDOUT)
    counts = {}
    xml = out / "pytest.xml"
    if xml.exists():
        suites = ET.parse(xml).getroot().iter("testsuite")
        for suite in suites:
            for key in ("tests", "failures", "errors", "skipped"):
                counts[key] = counts.get(key, 0)+int(suite.get(key, 0))
    current_tests = {str(p): file_hash(p) for p in sorted(Path("tests/v43").rglob("*.py"))}
    passed = (result.returncode == 0 and counts.get("tests", 0) > 0 and counts.get("skipped", 0) == 0
              and code_manifest()["hash"] == code["hash"] and tests == current_tests)
    report = dict(status="completed" if passed else "failed", scope="CPU_contracts_only", code_hash=code["hash"],
                  code_manifest=code, config_hash=json_hash(config), config=config, test_hashes=tests,
                  counts=counts, exit_code=result.returncode, python=sys.executable, pid=os.getpid(),
                  runtime_seconds=time.perf_counter()-start, log=str((out / "pytest.log").resolve()),
                  junit=str(xml.resolve()), created_at=stamp)
    atomic_json(out / "report.json", report)
    atomic_json(config["runtime"]["semantic_gate"], report)
    print((out / "pytest.log").read_text())
    print("report:", out / "report.json")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
