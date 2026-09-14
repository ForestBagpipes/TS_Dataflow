"""Convert the TIME benchmark's arrow shards into plain npz arrays.

The benchmark ships as HuggingFace datasets, which pull in `datasets` and
`pyarrow`. Those are present in the `timebench` environment and absent from the
curation environment, and adding them there would put a heavyweight dependency
on the critical path of every run for the sake of a one time read. So this
script runs once in `timebench` and writes npz files that `datasets.py` opens
with numpy alone.

Each source is one item holding a (C, T) target matrix, so the export is a
transpose into the (T, C) layout the ETT loader already returns, plus the
channel names and the sampling frequency.

Non finite entries are kept as they are. Dropping them here would silently
shift the time axis and break the alignment between channels, and the window
sampler already refuses any window that is not finite throughout.

Usage, in the timebench environment:
    python -u experiments/time_export.py --root /root/autodl-tmp/TIME_data
"""

import argparse
import json
from pathlib import Path

import numpy as np

#: The three financial sources of section 4.1.1, with the frequency directory
#: each one is stored under. D is daily, B is business day.
SOURCES = {
    "Crypto": "D",
    "US_Term_Structure": "B",
    "Oil_Price": "B",
}


def _read_shard(path: Path) -> dict:
    """First row of a HuggingFace arrow shard, read with pyarrow directly.

    `datasets.load_from_disk` is the obvious call and cannot be used: this
    package sits next to `experiments/datasets.py`, which shadows the library on
    `sys.path` and turns the import into a confusing AttributeError. Reading the
    IPC stream is a few lines and removes the ambiguity.
    """
    import pyarrow as pa

    with pa.memory_map(str(path), "r") as src:
        table = pa.ipc.open_stream(src).read_all()
    if table.num_rows != 1:
        raise RuntimeError(f"{path} holds {table.num_rows} rows, expected one")
    return {c: table.column(c)[0].as_py() for c in table.column_names}


def export_one(root: Path, out_dir: Path, name: str, freq: str) -> dict:
    shard = root / name / freq / "data-00000-of-00001.arrow"
    row = _read_shard(shard)
    target = np.asarray(row["target"], dtype=np.float64)
    if target.ndim != 2:
        raise RuntimeError(f"{name} target has shape {target.shape}, expected 2d")
    values = np.ascontiguousarray(target.T)
    channels = [str(c) for c in row["variate_names"]]
    if len(channels) != values.shape[1]:
        raise RuntimeError(
            f"{name} has {len(channels)} names for {values.shape[1]} channels")

    out = out_dir / f"time_{name}.npz"
    np.savez_compressed(
        out, values=values, channels=np.array(channels, dtype=object),
        freq=str(row["freq"]), start=str(row["start"]),
    )
    finite = float(np.isfinite(values).mean())
    return {
        "name": name, "path": str(out), "shape": list(values.shape),
        "channels": channels, "freq": str(row["freq"]),
        "start": str(row["start"]), "finite_fraction": round(finite, 6),
        # Channel scales differ by three orders of magnitude inside a single
        # source, which is why the window sampler cannot use an absolute spread
        # floor on this data.
        "median_abs_by_channel": [
            round(float(np.nanmedian(np.abs(values[:, i]))), 4)
            for i in range(values.shape[1])
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/root/autodl-tmp/TIME_data")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    root = Path(args.root)
    out_dir = Path(args.out) if args.out else (
        Path(__file__).resolve().parent.parent / "data")
    out_dir.mkdir(parents=True, exist_ok=True)

    report = [export_one(root, out_dir, n, f) for n, f in SOURCES.items()]
    for r in report:
        print(f"{r['name']:20s} {r['shape'][0]:6d} steps x {r['shape'][1]:3d} "
              f"channels  freq {r['freq']:2s}  finite {r['finite_fraction']:.4f}")
    (out_dir / "time_export.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print("___TIME_EXPORT_DONE___", flush=True)


if __name__ == "__main__":
    main()
