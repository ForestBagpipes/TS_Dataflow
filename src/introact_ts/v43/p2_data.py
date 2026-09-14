"""Frozen development intervals and text-only public Solar metadata."""
from dataclasses import replace
import gzip
from pathlib import Path
import numpy as np
from .data_contract import split_intervals
from .data_io import file_hash, inventory, read_rows
from .schemas import json_hash, require

SOLAR_SHA256 = "1ae9329c3e1032acbb8dd080bfc397c44507006812a715d2788f172820489a1c"


def inventory_p2(root, sources):
    records = inventory(root)
    if "Solar" in sources:
        path = Path(root) / "solar.txt.gz"
        digest = file_hash(path)
        require(digest == SOLAR_SHA256, "Solar frozen public file hash mismatch")
        # Count raw rows/columns, without converting any measurement to numeric.
        with gzip.open(path, "rb") as stream:
            widths = [line.count(b",")+1 for line in stream]
        require(len(widths) == 52560 and set(widths) == {137}, "Solar layout mismatch")
        records.append(dict(source="Solar", panel="Solar", path=str(path.resolve()),
                            shape=[52560, 137], channels=[f"pv_{i}" for i in range(137)],
                            file_sha256=digest, freq="10min", time_mode="benchmark_common_row_index",
                            calendar_status="original_timestamps_not_embedded", start=None,
                            provenance="LSTNet_author_repository_exact_git_blob_08a1f235546b3708309ff4fb544a54bb82e4f5e7",
                            split_bounds=split_intervals(52560)))
    lookup = {r["source"]: r for r in records}
    require(len(set(sources)) == len(sources) and set(sources) <= lookup.keys(), "unknown/duplicate P2 source")
    return [lookup[s] for s in sources]


def select_dev(records, *, context=512, horizons=(96, 192), maximum=64):
    """Same base intervals for both horizons; variants share the parent ID."""
    require(context == 512 and tuple(horizons) == (96, 192) and 0 < maximum <= 64, "unsupported P2 geometry")
    origins = []
    for record in records:
        lo, hi = record["split_bounds"]["dev"]
        ends = list(range(lo+context, hi-max(horizons)+1, context+max(horizons)))[:maximum]
        require(ends, f"no complete dev origin: {record['source']}")
        for end in ends:
            parent = f"{record['panel']}:{end-context}:{end+max(horizons)}"
            for horizon in horizons:
                fields = dict(source=record["source"], panel=record["panel"], split="dev", raw_start=end-context,
                              context_end=end, horizon=horizon, target_channel=0, data_hash=record["file_sha256"])
                origins.append(dict(fields, uid=json_hash(fields), parent_group=parent))
    return origins


def corrupt_context(raw, condition, block, seed):
    require(condition in ("raw", "target_block_10", "shared_block_10"), "unregistered corruption")
    x, z = raw.target.copy(), raw.covariates.copy()
    lo, hi = block
    require(0 <= lo < hi <= len(x), "invalid corruption block")
    if condition != "raw":
        x[lo:hi] = np.nan
    if condition == "shared_block_10":
        z[lo:hi] = np.nan
    uid = json_hash(dict(origin=raw.uid, condition=condition, block=block, seed=seed))
    return replace(raw, uid=uid, target=x, covariates=z)


def legal_history(record, episode, reader=read_rows):
    """Same-split full history; never reopen this context's hidden gap truth."""
    require(episode.split == "dev", "P2 only reads development history")
    lo, hi = record["split_bounds"][episode.split]
    require(lo <= episode.raw_start < episode.context_end <= hi, "history bounds mismatch")
    if lo == episode.raw_start:
        return episode.target.copy(), episode.covariates.copy(), [lo, episode.context_end]
    _, past = reader(record, lo, episode.raw_start, episode.split)
    c = episode.target_channel
    siblings = [i for i in range(past.shape[1]) if i != c]
    return (np.concatenate((past[:, c], episode.target)),
            np.concatenate((past[:, siblings], episode.covariates)), [lo, episode.context_end])
