#!/usr/bin/env python3
"""Compare three registered healthy-card reruns against archived GPU shards."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results/v55/hardware_compare.json"
PAIRS = (
    ("T1_ETTh1", "t1", "t1-etth1-full", "t1-etth1-verify"),
    ("PSWI_Exchange", "pswi", "pswi-exchange-full", "pswi-exchange-verify"),
    ("TimesNet_ETTh1", "timesnet", "timesnet-etth1-full",
     "timesnet-etth1-verify"),
)


def compare_one(name: str, directory: str, old_tag: str, new_tag: str) -> dict:
    folder = ROOT / "results/v54/replay/external" / directory
    paths = [folder / f"test__{tag}.npz" for tag in (old_tag, new_tag)]
    result = {"name": name, "old": str(paths[0]), "new": str(paths[1]),
              "exists": [p.exists() for p in paths]}
    if not all(result["exists"]):
        result["status"] = "missing"
        return result
    result["file_sha256"] = [hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in paths]
    with np.load(paths[0], allow_pickle=False) as old, \
            np.load(paths[1], allow_pickle=False) as new:
        a_keys, b_keys = set(old.files), set(new.files)
        result["keys"] = [len(a_keys), len(b_keys)]
        result["missing_old"] = sorted(b_keys - a_keys)
        result["missing_new"] = sorted(a_keys - b_keys)
        mismatched = []
        max_abs_diff = 0.0
        for key in sorted(a_keys & b_keys):
            a, b = old[key], new[key]
            equal = (a.shape == b.shape and a.dtype == b.dtype
                     and a.tobytes(order="C") == b.tobytes(order="C"))
            if not equal:
                mismatched.append(key)
                if a.shape == b.shape and np.issubdtype(a.dtype, np.number):
                    with np.errstate(invalid="ignore"):
                        diff = np.abs(a.astype(np.float64) - b.astype(np.float64))
                    finite = diff[np.isfinite(diff)]
                    if finite.size:
                        max_abs_diff = max(max_abs_diff, float(finite.max()))
        result["mismatched_keys"] = mismatched
        result["max_abs_diff"] = max_abs_diff
        result["status"] = ("bitwise_equal" if not result["missing_old"]
                            and not result["missing_new"]
                            and not mismatched else "mismatch")
    return result


def main() -> None:
    rows = [compare_one(*spec) for spec in PAIRS]
    payload = {"stage": "v55-hardware-comparison", "rows": rows,
               "all_bitwise_equal": all(r["status"] == "bitwise_equal"
                                        for r in rows)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1) + "\n")
    print(json.dumps(payload, indent=1))
    if not payload["all_bitwise_equal"]:
        raise SystemExit("hardware comparison incomplete or different")


if __name__ == "__main__":
    main()
