"""ETT dataset loading and window extraction.

The ETT-small CSVs live in ``data/``. Each row is one time step and each
column after the timestamp is one channel, so a window is a contiguous slice of
one channel. Windows containing missing values are dropped here rather than
imputed: the evaluation corpus needs a defect-free base to inject into, so that
"contaminated" means exactly "we put something there".
"""

from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ETT_FILES = {
    "ETTh1": "ETT-small_ETTh1.csv",
    "ETTh2": "ETT-small_ETTh2.csv",
    "ETTm1": "ETT-small_ETTm1.csv",
    "ETTm2": "ETT-small_ETTm2.csv",
}

ETT_FREQ = {"ETTh1": "H", "ETTh2": "H", "ETTm1": "15T", "ETTm2": "15T"}

MIRRORS = (
    "https://raw.githubusercontent.com/zhouhaoyi/ETDataset/main/ETT-small",
    "https://raw.githubusercontent.com/thuml/Time-Series-Library/main/dataset/ETT-small",
)


def ensure_ett(name: str) -> Path:
    """Path to one ETT CSV, downloading it on first use."""
    dest = DATA_DIR / ETT_FILES[name]
    if dest.exists():
        return dest
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    import urllib.request

    for mirror in MIRRORS:
        try:
            urllib.request.urlretrieve(f"{mirror}/{name}.csv", str(dest))
            return dest
        except Exception:
            continue
    raise FileNotFoundError(f"could not obtain {name}.csv; place it at {dest}")


def load_ett(name: str) -> tuple:
    """Return (values, channel_names) for one ETT file."""
    import pandas as pd

    df = pd.read_csv(ensure_ett(name))
    channels = [c for c in df.columns if c.lower() not in ("date", "unnamed: 0")]
    values = df[channels].to_numpy(dtype=np.float64)
    return values, channels


def sample_ett_windows(
    n_windows: int,
    window_len: int = 512,
    datasets: tuple = ("ETTh1", "ETTh2", "ETTm1", "ETTm2"),
    seed: int = 42,
    min_std: float = 1e-3,
) -> list:
    """Draw defect-free windows spread across ETT files and channels.

    Returns a list of dicts with ``series``, ``dataset``, ``channel``, ``freq``
    and ``start``. Sampling round-robins over (file, channel) pairs so no single
    channel dominates the corpus.
    """
    rng = np.random.RandomState(seed)
    pools = []
    for name in datasets:
        values, channels = load_ett(name)
        for ci, ch in enumerate(channels):
            pools.append((name, ch, ci, values[:, ci]))

    windows = []
    attempts = 0
    max_attempts = n_windows * 40
    while len(windows) < n_windows and attempts < max_attempts:
        attempts += 1
        name, ch, ci, col = pools[len(windows) % len(pools)]
        T = len(col)
        if T <= window_len:
            continue
        start = int(rng.randint(0, T - window_len))
        seg = col[start : start + window_len]
        if not np.isfinite(seg).all() or float(np.std(seg)) < min_std:
            continue
        windows.append(
            {
                "series": seg.astype(np.float64).copy(),
                "dataset": name,
                "channel": ch,
                "freq": ETT_FREQ[name],
                "start": start,
            }
        )
    if len(windows) < n_windows:
        raise RuntimeError(
            f"only found {len(windows)}/{n_windows} usable ETT windows"
        )
    return windows
