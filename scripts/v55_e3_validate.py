#!/usr/bin/env python3
"""Audit the complete E3 request-level latency report before paper use."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BACKBONES = ("bolt", "timesfm", "chronos2")
METHODS = ("NATIVE_KEEP", "BEST_FIXED", "FIXED_SAITS", "TATO", "FULL_INTROACT")


def check(root: Path = ROOT) -> dict:
    cost = root / "results/v54/cost"
    report = json.loads((cost / "e2e_latency.json").read_text())
    if report.get("requests") != 80:
        raise ValueError("E3 must contain 80 sampled requests")
    legality = report.get("legality_validation", {})
    if legality.get("mismatch_count") != 0 or legality.get("mismatches"):
        raise ValueError("E3 candidate legality differs from frozen replay")
    code = root / "scripts/v54_latency_e2e.py"
    digest = hashlib.sha256(code.read_bytes()).hexdigest()
    if report.get("code_sha256", {}).get("scripts/v54_latency_e2e.py") != digest:
        raise ValueError("E3 report uses a different measurement script")
    sampled = None
    for backbone in BACKBONES:
        chain = json.loads((cost / "work" / f"chain_{backbone}.json").read_text())
        rows = chain.get("records", [])
        episodes = [row["episode"] for row in rows]
        if len(episodes) != 80 or len(set(episodes)) != 80:
            raise ValueError(f"{backbone}: incomplete chain requests")
        if sampled is None:
            sampled = episodes
        elif episodes != sampled:
            raise ValueError(f"{backbone}: request order differs")
        summary = report.get("per_backbone", {}).get(backbone, {})
        totals = report.get("raw_totals_seconds", {}).get(backbone, {})
        for method in METHODS:
            values = totals.get(method, [])
            n = summary.get("hot_per_request", {}).get(method, {}).get("n")
            if n != 80 or len(values) != 80:
                raise ValueError(f"{backbone}/{method}: incomplete latency denominator")
            if not all(isinstance(value, (int, float)) and math.isfinite(value)
                       and value > 0 for value in values):
                raise ValueError(f"{backbone}/{method}: missing or invalid timings")
    for role in ("tsicl", "saits"):
        payload = json.loads((cost / "work" / f"{role}_times.json").read_text())
        episodes = [row["episode"] for row in payload.get("records", [])]
        if episodes != sampled:
            raise ValueError(f"{role}: request coverage differs")
    return {"status": "passed", "requests": 80, "backbones": list(BACKBONES),
            "methods": list(METHODS), "legality_mismatches": 0,
            "code_sha256": digest}


if __name__ == "__main__":
    print(json.dumps(check(), sort_keys=True))
