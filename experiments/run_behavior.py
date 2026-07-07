"""Thin IO shell for behavior extraction.

Reads manifest with profiles, runs behavior extraction via the configured TSFM,
writes updated manifest.
"""

import json
import numpy as np
import argparse
from src.introspect_ts.behavior import FakeTSFM, extract_behavior_signature
from src.introspect_ts.profiling import extract_statistical_profile


def run_behavior_from_manifest(
    input_path: str,
    output_path: str,
    tsfm=None,
    seed: int = 42,
):
    """Read manifest JSON, extract behavior signatures, write back.

    If tsfm is None, a FakeTSFM(L=12) is used.
    The manifest must contain "series" and "profile_0".."profile_11" fields,
    plus optionally "true_quality" and "true_difficulty" for synthetic data.
    """
    rng = np.random.RandomState(seed)
    with open(input_path, "r", encoding="utf-8") as f:
        rows = json.load(f)

    if tsfm is None:
        tsfm = FakeTSFM(L=12)

    for row in rows:
        series = np.array(row["series"], dtype=np.float64)
        if "true_quality" in row and "true_difficulty" in row:
            behavior = tsfm.extract_behavior_signature(
                series,
                quality=row["true_quality"],
                difficulty=row["true_difficulty"],
                seed=seed + row.get("window_id", 0),
            )
        else:
            behavior = extract_behavior_signature(tsfm, series)
        for d, val in enumerate(behavior):
            row[f"behavior_{d}"] = float(val)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    print(f"Behavior extraction done. {len(rows)} windows written to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--output", type=str, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    run_behavior_from_manifest(args.input, args.output, seed=args.seed)
