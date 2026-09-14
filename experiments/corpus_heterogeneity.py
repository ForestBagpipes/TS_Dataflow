"""Does adding the financial half actually make the corpus heterogeneous.

Section 4.1.1 takes two scene families rather than one, and the stated reason is
that peer calibration and abstention both presuppose the corpus carries
structural heterogeneity. That is a claim about the data, so it is measured
here rather than asserted.

Three read outs, all on the twelve dimensional statistical profile CDP extracts,
so they speak in the same space the method's nearest neighbour retrieval uses.

  spread        mean pairwise cosine distance between profiles. Higher means
                the corpus covers more distinct shapes
  separability  how well a family label can be recovered from the profile
                alone, by leave one out nearest neighbour. If the two families
                were indistinguishable in profile space, adding one to the
                other would enlarge the corpus without diversifying it
  neighbourhood the share of a window's K nearest neighbours drawn from its own
                family. Peer calibration compares a window against these, so
                this is the quantity that decides whether the two halves
                actually calibrate against each other or stay apart

Usage:
    python -u experiments/corpus_heterogeneity.py --n 600
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from corpus import CorpusSpec, build_corpus  # noqa: E402
from datasets import FINANCIAL, INDUSTRIAL  # noqa: E402
from spo_feasibility import profile_matrix  # noqa: E402

FIN = set(FINANCIAL)
IND = set(INDUSTRIAL)


def family_of(dataset: str) -> str:
    if dataset in FIN:
        return "financial"
    if dataset in IND:
        return "industrial"
    return "synthetic"


def cosine_distances(P: np.ndarray) -> np.ndarray:
    """Pairwise cosine distance on L2 normalised profiles, CDP's metric."""
    N = P / np.maximum(np.linalg.norm(P, axis=1, keepdims=True), 1e-12)
    return 1.0 - (N @ N.T)


def measure(profiles: np.ndarray, families: list, k: int = 50) -> dict:
    D = cosine_distances(profiles)
    n = len(families)
    off = ~np.eye(n, dtype=bool)
    fam = np.asarray(families)

    # Nearest neighbour, excluding self.
    Dm = D.copy()
    np.fill_diagonal(Dm, np.inf)
    nn = np.argmin(Dm, axis=1)
    order = np.argsort(Dm, axis=1)[:, :min(k, n - 1)]
    own = np.mean([np.mean(fam[order[i]] == fam[i]) for i in range(n)])

    out = {
        "n": n,
        "families": dict(Counter(families)),
        "mean_pairwise_distance": float(D[off].mean()),
        "nn_family_agreement": float(np.mean(fam[nn] == fam)),
        "own_family_share_in_k": float(own),
        "k": int(min(k, n - 1)),
    }
    # Baseline for the neighbourhood share: what it would be if family carried
    # no information at all. Without it the raw share is unreadable, since an
    # unbalanced corpus pushes it up for free.
    counts = np.array([np.mean(fam == f) for f in fam])
    out["own_family_share_if_random"] = float(counts.mean())
    out["excess_own_family_share"] = (
        out["own_family_share_in_k"] - out["own_family_share_if_random"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--k", type=int, default=50)
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=8)
    ap.add_argument("--out", default=str(ROOT / "results" / "corpus_heterogeneity.json"))
    args = ap.parse_args()

    n = args.n
    spec = CorpusSpec(
        n_contaminated=int(n * 0.35), n_clean=int(n * 0.20),
        n_hard=int(n * 0.1125), n_rare_valid=int(n * 0.1125),
        n_changepoint=int(n * 0.1125), n_clean_ood=int(n * 0.1125),
        seed=args.seed,
    )

    report = {}
    for source in ("ett", "finance", "mixed"):
        windows = build_corpus(spec, source=source)
        P = profile_matrix(windows, n_jobs=args.n_jobs)
        fams = [family_of(w.dataset) for w in windows]
        report[source] = measure(P, fams, k=args.k)
        report[source]["datasets"] = dict(Counter(w.dataset for w in windows))
        r = report[source]
        print(f"{source:8s} n={r['n']:4d}  spread={r['mean_pairwise_distance']:.4f}  "
              f"nn family agreement={r['nn_family_agreement']:.4f}  "
              f"own share in {r['k']}={r['own_family_share_in_k']:.4f} "
              f"(chance {r['own_family_share_if_random']:.4f}, "
              f"excess {r['excess_own_family_share']:+.4f})", flush=True)

    # Per channel count and profile summary of each financial source, which the
    # document's dataset table has to be able to quote.
    per_source = {}
    fin_windows = build_corpus(spec, source="finance")
    Pf = profile_matrix(fin_windows, n_jobs=args.n_jobs)
    for name in FINANCIAL:
        idx = [i for i, w in enumerate(fin_windows) if w.dataset == name]
        if not idx:
            continue
        per_source[name] = {
            "windows": len(idx),
            "profile_mean": [round(float(x), 4) for x in Pf[idx].mean(axis=0)],
            "profile_std": [round(float(x), 4) for x in Pf[idx].std(axis=0)],
        }
    report["per_financial_source"] = per_source

    Path(args.out).write_text(json.dumps(report, indent=1, default=float),
                              encoding="utf-8")
    print("___HETEROGENEITY_DONE___", flush=True)


if __name__ == "__main__":
    main()
