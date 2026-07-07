"""Thin IO shell for running statistical profiling on a corpus of UnifiedTSWindows.

Reads a list of UnifiedTSWindow records, computes 12-dim profiles, writes back.
All heavy lifting is in src/introspect_ts/profiling.py.
"""

import json
import numpy as np
import argparse
from src.introspect_ts.profiling import extract_statistical_profile
from tools.standardize import UnifiedTSWindow


def run_profiling(windows: list[UnifiedTSWindow]) -> list[UnifiedTSWindow]:
    """Compute statistical profiles for all windows. Modifies in place, returns list."""
    for w in windows:
        w.profile = extract_statistical_profile(w.series)
    return windows


def save_manifest(windows: list[UnifiedTSWindow], path: str, seed: int = 42):
    """Save windows as JSON lines manifest."""
    rows = []
    for w in windows:
        row = w.to_manifest_row()
        row["seed"] = seed
        rows.append(row)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, required=True, help="JSON input of serialized windows")
    parser.add_argument("--output", type=str, required=True, help="JSON manifest output path")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        raw = json.load(f)
    windows = [UnifiedTSWindow(**{k: np.array(v) if k == "series" else v for k, v in r.items()}) for r in raw]
    windows = run_profiling(windows)
    save_manifest(windows, args.output, seed=args.seed)
    print(f"Profiling done. {len(windows)} windows written to {args.output}")
