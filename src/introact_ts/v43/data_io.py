"""Metadata-first inventory and train/dev-only row access.

TIME uses the retained benchmark's common row index, not a claimed recovered
exchange calendar. No object channel array or held-out value array is loaded.
"""
import csv
import gzip
import hashlib
import json
from itertools import islice
from pathlib import Path
import zipfile
import numpy as np
from .data_contract import build_episode, origin_indices, split_intervals, ReadInterval, audit_reads
from .schemas import json_hash, require


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def npy_header(stream):
    version = np.lib.format.read_magic(stream)
    require(version in ((1, 0), (2, 0)), "unsupported NPY header version")
    reader = np.lib.format.read_array_header_1_0 if version == (1, 0) else np.lib.format.read_array_header_2_0
    shape, fortran, dtype = reader(stream)
    require(dtype.kind in "fiu" and not fortran, "non-numeric or non-row-major storage")
    return shape, dtype


def inventory(root):
    root = Path(root)
    records = []
    for name in ("ETTh1", "ETTh2", "ETTm1"):
        path = root / f"ETT-small_{name}.csv"
        with path.open(newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            require(header[0] == "date", "ETT timestamp column missing")
            # Read timestamps only; never convert measurement columns here.
            dates = [row[0] for row in reader]
        times = np.array(dates, dtype="datetime64[ns]").astype(np.int64)
        require(np.all(times[1:] > times[:-1]), "ETT timestamps not increasing")
        step = 15*60*10**9 if name == "ETTm1" else 60*60*10**9
        require(np.all(np.diff(times) == step), "ETT missing/irregular timestamp rows")
        records.append(dict(source=name, panel=name, path=str(path.resolve()), shape=[len(dates), len(header)-1],
                            channels=header[1:], time_mode="original_csv_timestamp_ns", freq="15min" if name == "ETTm1" else "h",
                            start=dates[0], file_sha256=file_hash(path), calendar_status="verified_csv_grid"))
    export = json.loads((root / "time_export.json").read_text())
    for record in export:
        name = record["name"]
        path = root / f"time_{name}.npz"
        with zipfile.ZipFile(path) as archive, archive.open("values.npy") as f:
            shape, dtype = npy_header(f)
        require(list(shape) == record["shape"] and shape[1] == len(record["channels"]), "TIME export metadata mismatch")
        # Scalar metadata is safe; channels.npy deliberately has legacy object dtype.
        with np.load(path, allow_pickle=False) as archive:
            require(str(archive["freq"]) == record["freq"] and str(archive["start"]) == record["start"], "TIME time metadata mismatch")
        records.append(dict(source=name, panel=name, path=str(path.resolve()), shape=list(shape), channels=record["channels"],
                            time_mode="benchmark_common_row_index", freq=record["freq"], start=record["start"],
                            file_sha256=file_hash(path), calendar_status="original_calendar_unrecovered",
                            dtype=dtype.str, provenance="retained_time_export_and_exporter_code"))
    for r in records:
        r["split_bounds"] = split_intervals(r["shape"][0])
        r["pilot_capacity"] = {s: len(v) for s, v in origin_indices(r["shape"][0]).items()}
    return records


def select_pilot(records, count=32, context=512, horizon=32):
    """Round-robin sources; nonoverlapping complete read intervals per panel.

    Alternate train/dev within source when both support a full window. Source
    scarcity is reported, not repaired with overlapping or cross-split windows.
    """
    queues = {}
    for record in records:
        by_split = origin_indices(record["shape"][0], context, horizon)
        queue = []
        for i in range(max(map(len, by_split.values()), default=0)):
            for split in ("train", "dev"):
                if i < len(by_split[split]):
                    queue.append((split, by_split[split][i]))
        queues[record["source"]] = queue
    selected = []
    while len(selected) < count:
        progress = False
        for record in records:
            queue = queues[record["source"]]
            if queue and len(selected) < count:
                split, origin = queue.pop(0)
                identity = dict(source=record["source"], panel=record["panel"], split=split,
                                raw_start=origin-context, context_end=origin, horizon=horizon,
                                target_channel=0, data_hash=record["file_sha256"])
                uid = json_hash(identity)
                selected.append(dict(identity, uid=uid, parent_group=f"{record['panel']}:{origin-context}:{origin+horizon}"))
                progress = True
        require(progress, "insufficient independent train/dev origins")
    audit_reads([ReadInterval(r["source"], r["panel"], r["parent_group"], r["split"],
                             r["raw_start"], r["context_end"]+horizon) for r in selected])
    return selected


def read_rows(record, start, stop, split):
    """Convert only authorized rows to numeric values; no np.load(values)."""
    require(split in ("train", "dev"), "held-out data reader disabled")
    lo, hi = record["split_bounds"][split]
    require(lo <= start < stop <= hi, "data read crosses split")
    path = Path(record["path"])
    if path.suffix == ".gz":
        # Benchmark rows have no embedded calendar. Decode only the allowed
        # interval; skipped rows, including held-out measurements, stay text.
        with gzip.open(path, "rt", newline="") as f:
            rows = islice(csv.reader(f), start, stop)
            values = np.asarray([[float(x) if x else np.nan for x in row] for row in rows], dtype=np.float64)
        timestamps = np.arange(start, stop, dtype=np.int64)
    elif path.suffix == ".csv":
        values, times = [], []
        with path.open(newline="") as f:
            reader = csv.reader(f)
            next(reader)
            for i, row in enumerate(islice(reader, stop)):
                if i >= start:
                    times.append(row[0])
                    values.append([float(x) if x else np.nan for x in row[1:]])
        values = np.asarray(values, dtype=np.float64)
        timestamps = np.asarray(times, dtype="datetime64[ns]").astype(np.int64)
    else:
        with zipfile.ZipFile(path) as archive, archive.open("values.npy") as stream:
            shape, dtype = npy_header(stream)
            row_bytes = shape[1]*dtype.itemsize
            # Compressed seeking consumes bytes but no skipped numeric labels
            # are decoded, returned, used for normalization or sample selection.
            stream.seek(stream.tell()+start*row_bytes)
            payload = stream.read((stop-start)*row_bytes)
            require(len(payload) == (stop-start)*row_bytes, "truncated data shard")
            values = np.frombuffer(payload, dtype=dtype).reshape(stop-start, shape[1]).copy()
        timestamps = np.arange(start, stop, dtype=np.int64)
    require(values.shape == (stop-start, record["shape"][1]), "row shape mismatch")
    return timestamps, values


def load_context(record, origin):
    require(origin["data_hash"] == record["file_sha256"], "origin data hash mismatch")
    times, values = read_rows(record, origin["raw_start"], origin["context_end"], origin["split"])
    channel = origin["target_channel"]
    require(0 <= channel < values.shape[1], "invalid target channel")
    siblings = [i for i in range(values.shape[1]) if i != channel]
    return build_episode(uid=origin["uid"], source=record["source"], panel=record["panel"],
                         parent_group=origin["parent_group"], split=origin["split"], target_channel=channel,
                         timestamps=times, target=values[:, channel], covariates=values[:, siblings],
                         availability=np.broadcast_to(times[:, None], values.shape), raw_start=origin["raw_start"],
                         context_end=origin["context_end"], horizon=origin["horizon"], split_bounds=record["split_bounds"][origin["split"]])
