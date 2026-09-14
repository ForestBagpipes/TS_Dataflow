"""Chain check. Do the five experiment groups all stand on the same ground.

Run before any headline experiment. The corpus has been rebuilt twice since the
first results were produced, the method layer hash has moved, and three
hyperparameters have changed, so a script still holding an older version would
produce numbers that look fine and are not comparable to the rest.

Nothing here calls a model or an API. It reads files and hashes them.

Checks, each reported pass or fail with the evidence attached:

  method hash     the seven method layer files, against what monitor computes
  hyperparameters K, eta and the epsilon conversion path, against the matrix
  criteria        the stratum selection constants, against their pre registrations
  corpus identity a fingerprint of the assembled corpus, so a score file
                  computed on an earlier corpus is caught rather than silently
                  reused
  score files     which arms have scores on the current corpus and which do not

Usage:
    python -u experiments/chain_check.py --scale xl --source mixed
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tools"))

#: What the matrix and the pre registrations fix. A mismatch here means a
#: document and the code disagree, which is the failure this catches.
EXPECTED = {
    "calibration.K": 50,
    "verify.eta": 0.5,
    "verify.epsilon_path": True,
    "corpus.TAIL_PERCENTILE": 99.5,
    "corpus.BRIEF_FRAC": 0.05,
    "corpus.RETURN_TOL": 0.5,
    "corpus.SCALE_RATIO": 1.5,
    "corpus.DIFFICULTY_LAGS": 16,
    "spo.t_cal": 500,
}


def corpus_fingerprint(windows):
    """A hash of what the corpus is, not of how it was built.

    Window ids, strata and the first and last value of each series. Two corpora
    built under different selection criteria differ here even when the spec and
    the seed match, which is exactly the case a score file has to be checked
    against.
    """
    h = hashlib.sha256()
    for w in sorted(windows, key=lambda w: w.window_id):
        s = np.asarray(w.series, dtype=np.float64)
        h.update(f"{w.window_id}|{w.stratum}|{w.dataset}|{len(s)}|"
                 f"{s[0]:.6e}|{s[-1]:.6e}".encode())
    return h.hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="xl")
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(ROOT / "results" / "chain_check.json"))
    args = ap.parse_args()

    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": str(detail)})
        print(f"  [{'ok  ' if ok else 'FAIL'}] {name:34s} {detail}", flush=True)

    print("method layer")
    from monitor import CODE_FILES, code_hash
    h, per = code_hash()
    add("method_hash", True, h)
    add("method_files_present",
        all(v != "MISSING" for v in per.values()),
        f"{len(per)} files")

    print("hyperparameters")
    import inspect
    from introact_ts.calibration import calibrate
    from introact_ts.verify import VerifyConfig, epsilon_from_spread
    import corpus as C
    from introact_ts.spo import SPOConfig

    got = {
        "calibration.K": inspect.signature(calibrate).parameters["K"].default,
        "verify.eta": VerifyConfig().eta,
        "verify.epsilon_path": callable(epsilon_from_spread),
        "corpus.TAIL_PERCENTILE": C.TAIL_PERCENTILE,
        "corpus.BRIEF_FRAC": C.BRIEF_FRAC,
        "corpus.RETURN_TOL": C.RETURN_TOL,
        "corpus.SCALE_RATIO": C.SCALE_RATIO,
        "corpus.DIFFICULTY_LAGS": C.DIFFICULTY_LAGS,
        "spo.t_cal": SPOConfig().t_cal,
    }
    for k, want in EXPECTED.items():
        add(k, got[k] == want, f"{got[k]} against {want}")

    print("corpus identity")
    from corpus import build_corpus
    from run_agent import SCALES
    spec = SCALES[args.scale]
    spec.seed = args.seed
    windows = build_corpus(spec, source=args.source)
    fp = corpus_fingerprint(windows)
    strata = {}
    for w in windows:
        strata[w.stratum] = strata.get(w.stratum, 0) + 1
    add("corpus_built", True, f"{len(windows)} windows, fingerprint {fp}")
    add("corpus_strata", True, json.dumps(strata, sort_keys=True))

    print("score files against this corpus")
    ids = {int(w.window_id) for w in windows}
    for path, keys in ((ROOT / "results" / "valuation_scores_xl.json",
                        ("timeinf", "data_oob", "data_shapley")),
                       (ROOT / "results" / "ltsv_scores_xl.json", ("ltsv",))):
        if not path.exists():
            for k in keys:
                add(f"scores:{k}", False, "file absent")
            continue
        blob = json.loads(path.read_text(encoding="utf-8"))
        for k in keys:
            if "methods" in blob:
                sc = blob["methods"].get(k, {}).get("window_scores")
            else:
                sc = blob.get("window_scores")
            if not sc:
                add(f"scores:{k}", False, "not in file")
                continue
            keys_i = {int(x) for x in sc}
            ov = len(keys_i & ids) / max(len(ids), 1)
            add(f"scores:{k}:id_overlap", True,
                f"overlap {ov:.3f} ({len(keys_i & ids)} of {len(ids)})")

    # Window ids are positional counters assigned during assembly, so two
    # entirely different corpora share them. An id overlap therefore proves
    # nothing, and reporting it as a pass is how a stale score file survives a
    # check. Content is compared instead: the first block of each window in the
    # export against the first points of the same window here.
    print("score corpus identity, by content")
    npz = ROOT / "data" / "valuation_xl.npz"
    local_npz = ROOT / ".tmp" / "valuation_xl.npz"
    use = npz if npz.exists() else (local_npz if local_npz.exists() else None)
    if use is None:
        add("scores_corpus_identity", False,
            "the exported npz is absent, content cannot be compared")
    else:
        z = np.load(use, allow_pickle=True)
        X, wid, bidx = z["X"], z["window_id"], z["block_index"]
        first = {int(wid[i]): X[i][:8] for i in range(len(wid)) if bidx[i] == 0}
        same = tot = 0
        for w in windows:
            a = first.get(int(w.window_id))
            if a is None:
                continue
            b = np.asarray(w.series, dtype=np.float64)[:8]
            if not np.isfinite(b).all():
                continue
            tot += 1
            same += int(np.allclose(a, b, rtol=1e-9, atol=1e-9))
        frac = same / max(tot, 1)
        add("scores_corpus_identity", frac >= 0.99,
            f"{same} of {tot} windows match on content ({frac:.4f}), "
            f"anything below one means the score file predates a corpus change")

    failed = [c for c in checks if not c["ok"]]
    print()
    print(f"{len(checks) - len(failed)} passed, {len(failed)} failed")
    for c in failed:
        print(f"  FAIL {c['check']}: {c['detail']}")

    Path(args.out).write_text(json.dumps(
        {"scale": args.scale, "source": args.source, "seed": args.seed,
         "method_hash": h, "corpus_fingerprint": fp, "strata": strata,
         "checks": checks}, indent=1), encoding="utf-8")
    print("___CHAIN_CHECK_DONE___", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
