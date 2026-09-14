"""Sweep the soft penalty weight, in the main table's columns.

Experiment one's second sub table, and the source of the main table's
`soft_penalty` row. The competing design puts structural preservation in the
objective as a weighted penalty rather than in a veto, so a large enough utility
gain buys a structurally damaging edit. Sweeping the weight traces the whole
soft design space, which is what makes the comparison one against the best soft
variant rather than against a strawman.

**Why this shares everything but the decision rule.** The arm runs through
`run_main.agent_traces` with `VerifyConfig.soft_mu` set, so the corpus, the
proposals, the sandbox, the probe and the scoring are the main table's. The only
difference from our row is the acceptance rule. An earlier version of this
comparison lived in `soft_vs_hard.py` on its own corpus, its own proposer and
its own damage definition, and a row produced that way could not be put in the
table beside ours. That script keeps its frontier analysis, which asks a
different question.

**Crash safety.** Every (mu, seed) writes its own file through a temporary name
and a rename, which is atomic, so an interrupted run leaves either a complete
result or no file. A combination whose file already parses is skipped. A file
that exists but does not parse is deleted and recomputed, since that is what a
half written file from an older, non atomic version looks like.

Perception is the expensive part and is computed once per seed, shared by every
weight in that seed. A seed whose weights are all on disk skips perception too.

Usage:
    python -u experiments/run_soft_sweep.py --source mixed --scale xl \
        --seeds 0,1,2
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from corpus import build_corpus  # noqa: E402
from run_agent import SCALES  # noqa: E402
from run_main import agent_traces, dump_window_traces, score_rows  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.verify import VerifyConfig  # noqa: E402

#: The weights to sweep, matching `soft_vs_hard.MUS` so the two analyses are on
#: the same grid. Zero is the degenerate case with no structural term at all,
#: which should reproduce the utility only contrast and is kept as a check.
MUS = [0.0, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0]


def atomic_write(path: Path, blob: dict) -> None:
    """Write through a temporary name and rename, which is atomic.

    A power cut during the write leaves the temporary file, never a truncated
    result, so the skip check below can trust any file it can parse.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(blob, indent=1, default=float), encoding="utf-8")
    os.replace(tmp, path)


def already_done(path: Path) -> bool:
    """True if a complete result is on disk. A corrupt one is removed."""
    if not path.exists():
        return False
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return True
    except Exception:
        print(f"  {path.name} does not parse, removing and recomputing",
              flush=True)
        path.unlink(missing_ok=True)
        return False


def result_path(out_dir: Path, mu: float, seed: int) -> Path:
    return out_dir / f"soft_mu{mu:g}_seed{seed}.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="xl", choices=list(SCALES))
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--mus", nargs="*", type=float, default=None)
    ap.add_argument("--tau", type=float, default=0.02)
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=32)
    ap.add_argument("--out", default=str(ROOT / "results" / "xl"))
    ap.add_argument("--no-dump-traces", dest="dump_traces",
                    action="store_false", default=True)
    args = ap.parse_args()

    out_dir = Path(args.out)
    seeds = [int(s) for s in args.seeds.replace(" ", "").split(",") if s]
    mus = args.mus if args.mus is not None else MUS
    print(f"seeds {seeds}, mus {mus}, source {args.source}, scale {args.scale}",
          flush=True)

    models = None
    for seed in seeds:
        todo = [m for m in mus if not already_done(result_path(out_dir, m, seed))]
        done = [m for m in mus if m not in todo]
        if done:
            print(f"seed {seed}, already on disk, skipped mu {done}", flush=True)
        if not todo:
            continue

        spec = SCALES[args.scale]
        spec.seed = seed
        windows = build_corpus(spec, source=args.source)
        if models is None:
            models = make_pool(PRESETS[args.preset]["curation"],
                               device=args.device)
        print(f"seed {seed}, corpus {len(windows)} windows", flush=True)

        reference = IntroActAgent(models, AgentConfig(
            verification=VerifyConfig(tau=args.tau), n_jobs=args.n_jobs))
        t0 = time.time()
        states = reference.perceive(windows)
        print(f"  perception {time.time() - t0:.0f}s", flush=True)

        for mu in todo:
            t0 = time.time()
            traces = agent_traces(models, windows, states, "soft_penalty",
                                  args.tau, args.n_jobs, reference, soft_mu=mu)
            row = score_rows(traces, windows)
            row.update({"soft_mu": float(mu), "seed": seed, "tau": args.tau,
                        "scale": args.scale, "source": args.source,
                        "n_windows": len(windows),
                        "compute_seconds": time.time() - t0})
            if args.dump_traces:
                tp = out_dir / f"soft_mu{mu:g}_seed{seed}_traces.jsonl"
                tp.unlink(missing_ok=True)
                row["traces_written"] = dump_window_traces(
                    traces, windows, tp, f"soft_mu{mu:g}")
            atomic_write(result_path(out_dir, mu, seed), row)

            rr = row.get("repair_nrmsd")
            print(f"  mu {mu:6g}  edits {row['committed_edits']:5d}  "
                  f"mis rate {row['protected_mis_edit_rate']:.4f}  "
                  f"damage {row['damage_rate']:.4f}  "
                  f"nrmsd {rr if rr is not None else float('nan'):8.4f}  "
                  f"{row['compute_seconds']:6.0f}s", flush=True)

    print("___SOFT_SWEEP_DONE___", flush=True)


if __name__ == "__main__":
    main()
