"""Dataset loading for LTSF benchmarks.

Downloads from HuggingFace or mirrors, generates sliding windows,
returns UnifiedTSWindow records.

Data is cached in the data/ directory under work2.
"""

import numpy as np
from pathlib import Path
import json
import hashlib
from tools.standardize import UnifiedTSWindow

DATA_DIR = Path(__file__).parent.parent / "data"

DATASET_CONFIGS = {
    "Electricity": {"freq": "H", "expected_series": 321},
    "Traffic": {"freq": "H", "expected_series": 862},
    "Weather": {"freq": "10T", "expected_series": 21},
    "ETTh1": {"freq": "H", "expected_series": 7},
    "ETTh2": {"freq": "H", "expected_series": 7},
    "ETTm1": {"freq": "15T", "expected_series": 7},
    "ETTm2": {"freq": "15T", "expected_series": 7},
    "Exchange": {"freq": "D", "expected_series": 8},
    "ILI": {"freq": "W", "expected_series": 7},
}


def _download_file(url: str, dest: Path) -> bool:
    """Download a file with simple retry. Returns True on success."""
    import urllib.request
    if dest.exists():
        return True
    try:
        urllib.request.urlretrieve(url, str(dest))
        return True
    except Exception as e:
        print(f"  Download failed: {url[:80]}... {e}")
        return False


def download_ltsf_datasets() -> dict[str, Path]:
    """Download LTSF datasets. Returns dict of dataset_name -> file_path.

    Uses multiple mirror sources. Falls back gracefully.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    mirrors = [
        "https://raw.githubusercontent.com/zhouhaoyi/ETDataset/main",
        "https://raw.githubusercontent.com/thuml/Autoformer/main/dataset",
        "https://raw.githubusercontent.com/thuml/Time-Series-Library/main/dataset",
    ]

    datasets = {}
    files = {
        "Electricity": "electricity.csv",
        "Traffic": "traffic.csv",
        "Weather": "weather.csv",
        "ETTh1": "ETT-small/ETTh1.csv",
        "ETTh2": "ETT-small/ETTh2.csv",
        "ETTm1": "ETT-small/ETTm1.csv",
        "ETTm2": "ETT-small/ETTm2.csv",
        "Exchange": "exchange_rate.csv",
        "ILI": "illness/national_illness.csv",
    }

    for name, rel_path in files.items():
        dest = DATA_DIR / rel_path.replace("/", "_")
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists():
            datasets[name] = dest
            continue

        ok = False
        for mirror in mirrors:
            url = f"{mirror}/{rel_path}"
            if _download_file(url, dest):
                ok = True
                break

        if ok:
            datasets[name] = dest
            print(f"  Downloaded {name} -> {dest}")
        else:
            print(f"  FAILED to download {name}")

    return datasets


def load_dataset_csv(path: Path, config: dict) -> list[UnifiedTSWindow]:
    """Load a single CSV dataset, generate sliding windows.

    Each row in the CSV is a separate time series (column 0 = date, cols 1+ = values).
    For datasets where each row is a time step (ETT format), adjust accordingly.
    """
    try:
        data = np.loadtxt(path, delimiter=",", skiprows=1)
    except Exception:
        import pandas as pd
        df = pd.read_csv(path)
        data = df.values

    if data.shape[1] <= 2:
        # Single series: first column is date
        values = data[:, 1:].astype(np.float64)
    else:
        values = data[:, 1:].astype(np.float64)

    # For datasets where each row is a separate series (rows = series, cols = time)
    # like Electricity, Traffic, Weather
    # vs datasets where each row is a time step (ETT format)
    n_series = values.shape[0]
    n_timesteps = values.shape[1]

    # If many rows with few columns, each row is likely a time step
    if n_series > n_timesteps and n_series > 1000:
        values = values.T
        values = values.astype(np.float64)
        n_series, n_timesteps = values.shape

    windows = []
    window_len = 512
    stride = 128
    wid = 0

    for s in range(n_series):
        series = values[s, :]
        series = series[~np.isnan(series)]
        T_s = len(series)
        if T_s < window_len:
            continue
        for start in range(0, T_s - window_len, stride):
            chunk = series[start:start + window_len].astype(np.float64)
            windows.append(UnifiedTSWindow(
                window_id=wid,
                series=chunk,
                freq=config["freq"],
                dataset=Path(path).stem.split("_")[0] if "_" in Path(path).stem else Path(path).stem,
                split="train",
            ))
            wid += 1

    return windows


def generate_real_windows(dataset_filter: list[str] = None) -> list[UnifiedTSWindow]:
    """Download datasets, generate windows. Returns flat list of UnifiedTSWindow."""
    file_paths = download_ltsf_datasets()
    if dataset_filter:
        file_paths = {k: v for k, v in file_paths.items() if k in dataset_filter}

    all_windows = []
    for name, path in file_paths.items():
        config = DATASET_CONFIGS.get(name, {"freq": "H", "expected_series": 1})
        windows = load_dataset_csv(path, config)
        for w in windows:
            w.dataset = name
        all_windows.extend(windows)
        print(f"  {name}: {len(windows)} windows from {config['expected_series']} series")

    print(f"Total windows: {len(all_windows)}")
    return all_windows


if __name__ == "__main__":
    windows = generate_real_windows()
    manifest_path = DATA_DIR / "real_windows_manifest.json"
    serialized = []
    for w in windows:
        row = w.to_manifest_row()
        row["series"] = w.series.tolist()
        serialized.append(row)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(serialized)} windows to {manifest_path}")
