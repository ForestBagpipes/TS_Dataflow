"""P0-A: audit calibration corpus determinism and build a frozen manifest.

Usage:
    # build one manifest
    python experiments/p0_corpus_determinism.py --mode build \
        --n 1600 --seed 101 --source mixed --out results/p0_corpus_manifest_a.json

    # compare two independent process builds
    python experiments/p0_corpus_determinism.py --mode compare \
        --n 1600 --seed 101 --source mixed --out results/p0_corpus_determinism_report.json
"""

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from build_calibration import build as build_calibration, SCALES  # noqa: E402


def _hash_array(a: np.ndarray) -> str:
    """Stable SHA-256 over full finite array, rounded to 6 decimals."""
    x = np.asarray(a, dtype=np.float64)
    finite = np.isfinite(x)
    if not finite.all():
        # Replace non-finite with a sentinel byte pattern so the hash reflects
        # their positions without breaking tobytes.
        x = x.copy()
        x[~finite] = np.nan
    return hashlib.sha256(np.round(x, 6).tobytes()).hexdigest()


def sample_uid(window) -> str:
    """Stable identity from dataset/stratum/true_kind and full series hashes."""
    clean = window.clean_series
    corrupted = window.series
    clean_hash = _hash_array(clean) if clean is not None else "no_clean"
    corrupted_hash = _hash_array(corrupted)
    true_kind = window.contamination or "null"
    return f"{window.dataset}:{window.stratum}:{true_kind}:{clean_hash}:{corrupted_hash}"


def build_manifest(n: int, seed: int, source: str, verbose: bool = False):
    """Build corpus and return manifest records plus diagnostic info."""
    # Capture global state before/after because build_calibration mutates SCALES.
    scales_before = {k: getattr(v, "seed", None) for k, v in SCALES.items()}
    windows, dropped = build_calibration(n=n, seed=seed, source=source, verbose=verbose)
    scales_after = {k: getattr(v, "seed", None) for k, v in SCALES.items()}

    records = []
    for w in windows:
        clean = w.clean_series
        rec = {
            "window_id": int(w.window_id),
            "sample_uid": sample_uid(w),
            "dataset": w.dataset,
            "stratum": w.stratum,
            "true_kind": w.contamination or "null",
            "clean_hash": _hash_array(clean) if clean is not None else None,
            "corrupted_hash": _hash_array(w.series),
            "seed": int(w.seed),
        }
        records.append(rec)

    diagnostics = {
        "scales_seed_before": scales_before,
        "scales_seed_after": scales_after,
        "scales_mutated": scales_before != scales_after,
        "dropped": dropped,
        "n_windows": len(records),
        "unique_uids": len({r["sample_uid"] for r in records}),
    }
    return records, diagnostics


def save_manifest(records, diagnostics, out_path: Path):
    out = {
        "schema_version": "p0-a-1",
        "generator": str(Path(__file__).name),
        "records": records,
        "diagnostics": diagnostics,
        "strata_counts": dict(Counter(r["stratum"] for r in records)),
        "true_kind_counts": dict(Counter(r["true_kind"] for r in records)),
        "dataset_counts": dict(Counter(r["dataset"] for r in records)),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def compare_manifests(path_a: Path, path_b: Path):
    a = json.loads(path_a.read_text(encoding="utf-8"))
    b = json.loads(path_b.read_text(encoding="utf-8"))
    rec_a = {r["sample_uid"]: r for r in a["records"]}
    rec_b = {r["sample_uid"]: r for r in b["records"]}

    uids_a = set(rec_a)
    uids_b = set(rec_b)
    common = uids_a & uids_b
    only_a = uids_a - uids_b
    only_b = uids_b - uids_a

    order_match = [rec_a[uid]["window_id"] == rec_b[uid]["window_id"] for uid in common]
    content_diffs = []
    for uid in common:
        ra, rb = rec_a[uid], rec_b[uid]
        if (ra["dataset"], ra["stratum"], ra["true_kind"],
            ra["clean_hash"], ra["corrupted_hash"]) != \
           (rb["dataset"], rb["stratum"], rb["true_kind"],
            rb["clean_hash"], rb["corrupted_hash"]):
            content_diffs.append(uid)

    report = {
        "n_a": len(rec_a),
        "n_b": len(rec_b),
        "common": len(common),
        "only_in_a": sorted(list(only_a)),
        "only_in_b": sorted(list(only_b)),
        "window_id_order_match": sum(order_match),
        "window_id_order_total": len(order_match),
        "content_differ": sorted(content_diffs),
        "deterministic": len(common) == len(rec_a) == len(rec_b)
                         and not content_diffs
                         and sum(order_match) == len(order_match),
    }
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["build", "compare"], default="build")
    ap.add_argument("--n", type=int, default=1600)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--out", default=str(ROOT / "results" / "p0_corpus_determinism_report.json"))
    ap.add_argument("--manifest-a", default=str(ROOT / "results" / "p0_corpus_manifest_a.json"))
    ap.add_argument("--manifest-b", default=str(ROOT / "results" / "p0_corpus_manifest_b.json"))
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.mode == "build":
        records, diagnostics = build_manifest(args.n, args.seed, args.source, args.verbose)
        save_manifest(records, diagnostics, Path(args.out))
        print(f"___P0_CORPUS_BUILD_DONE___ n={len(records)} unique_uids={diagnostics['unique_uids']}")
        print(f"  scales mutated: {diagnostics['scales_mutated']}")
        print(f"  wrote {args.out}")
    elif args.mode == "compare":
        py = sys.executable
        script = str(Path(__file__).resolve())
        base = Path(args.out).parent
        base.mkdir(parents=True, exist_ok=True)
        path_a = Path(args.manifest_a)
        path_b = Path(args.manifest_b)

        cmd_a = [py, script, "--mode", "build", "--n", str(args.n), "--seed", str(args.seed),
                 "--source", args.source, "--out", str(path_a)]
        cmd_b = [py, script, "--mode", "build", "--n", str(args.n), "--seed", str(args.seed),
                 "--source", args.source, "--out", str(path_b)]

        print("spawning build A", flush=True)
        proc_a = subprocess.Popen(cmd_a, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        print("spawning build B", flush=True)
        proc_b = subprocess.Popen(cmd_b, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        out_a, _ = proc_a.communicate()
        out_b, _ = proc_b.communicate()
        print(out_a)
        print(out_b)

        report = compare_manifests(path_a, path_b)
        report["build_a_exit"] = proc_a.returncode
        report["build_b_exit"] = proc_b.returncode
        report["build_a_stdout_tail"] = "\n".join(out_a.splitlines()[-10:])
        report["build_b_stdout_tail"] = "\n".join(out_b.splitlines()[-10:])

        Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(f"___P0_CORPUS_COMPARE_DONE___ deterministic={report['deterministic']}")
        print(f"  n_a={report['n_a']} n_b={report['n_b']} common={report['common']}")
        print(f"  only_in_a={len(report['only_in_a'])} only_in_b={len(report['only_in_b'])}")
        print(f"  content_differ={len(report['content_differ'])}")
        print(f"  wrote {args.out}")


if __name__ == "__main__":
    main()
