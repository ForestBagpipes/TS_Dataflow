"""Main experiment: IntroAct-TS against baselines and its own ablations.

Perception is computed once and shared by every method, so the comparison
isolates what each method *does* with the same evidence rather than how much
evidence it gathered.

Usage:
    python experiments/run_agent.py --scale small
    python experiments/run_agent.py --scale full --source ett --out results/
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from baselines import BASELINES  # noqa: E402
from corpus import CorpusSpec, build_corpus  # noqa: E402
from metrics import summarise  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.policy import PolicyConfig  # noqa: E402
from introact_ts.probe import ProbeConfig  # noqa: E402
from introact_ts.tsfm import make_model_pool  # noqa: E402
from introact_ts.verify import VerifyConfig  # noqa: E402

#: Curation is judged by models 0-2; models 3-4 never take part and are used
#: only to test whether the benefit transfers.
CURATION_SEEDS = (0, 1, 2)
TRANSFER_SEEDS = (7, 11)

SCALES = {
    "small": CorpusSpec(
        n_contaminated=35, n_clean=20, n_hard=10, n_rare_valid=10,
        n_changepoint=10, n_clean_ood=10,
    ),
    "medium": CorpusSpec(
        n_contaminated=70, n_clean=40, n_hard=20, n_rare_valid=20,
        n_changepoint=20, n_clean_ood=20,
    ),
    "full": CorpusSpec(),
}


def ablation_configs() -> dict:
    """IntroAct-TS variants, each disabling exactly one mechanism."""
    base = dict(probe=ProbeConfig(), K_peers=40)
    return {
        "introact_full": AgentConfig(**base),
        # No structural veto: utility improvement alone decides.
        "ablate_no_structure": AgentConfig(
            **base, verification=VerifyConfig(require_structure=False)
        ),
        # No post-intervention re-probe: the structural check still runs, but
        # the agent never finds out whether the model actually benefited.
        "ablate_no_reprobe": AgentConfig(
            **base, verification=VerifyConfig(require_reprobe=False)
        ),
        # No verification at all: whatever the policy proposes is committed.
        "ablate_no_verify": AgentConfig(
            **base,
            verification=VerifyConfig(
                require_structure=False, require_reprobe=False, require_risk=False
            ),
        ),
        # No peer calibration: behaviour is z-scored against the whole corpus.
        "ablate_no_peer_calibration": AgentConfig(**base, peer_calibration=False),
        # No protection: hard / rare-valid / OOD windows are fair game.
        "ablate_no_protection": AgentConfig(**base, policy=PolicyConfig(protect=())),
    }


def run_all(spec: CorpusSpec, source: str, verbose: bool = True) -> dict:
    windows = build_corpus(spec, source=source)
    curation_models = make_model_pool(CURATION_SEEDS)
    transfer_models = make_model_pool(TRANSFER_SEEDS)
    if verbose:
        print(f"corpus: {len(windows)} windows from {source}")

    results, traces_by_method = {}, {}

    # Shared perception, computed once by the full agent.
    reference_agent = IntroActAgent(curation_models, ablation_configs()["introact_full"])
    t0 = time.time()
    states = reference_agent.perceive(windows)
    if verbose:
        print(f"perception: {time.time() - t0:.1f}s")

    for name, fn in BASELINES.items():
        t0 = time.time()
        traces = fn(windows, states, curation_models)
        traces_by_method[name] = traces
        results[name] = summarise(traces, windows, transfer_models)
        if verbose:
            print(f"  {name:28s} {time.time() - t0:6.1f}s")

    for name, cfg in ablation_configs().items():
        agent = IntroActAgent(curation_models, cfg)
        t0 = time.time()
        if cfg.peer_calibration:
            # Reuse the shared perception; nothing about it varies.
            agent._calib = reference_agent._calib
            agent._ood = reference_agent._ood
            agent._reference = reference_agent._reference
            run_states = states
        else:
            run_states = agent.perceive(windows)
        traces = [
            agent.curate_window(w, s, peer_idx=i)
            for i, (w, s) in enumerate(zip(windows, run_states))
        ]
        traces_by_method[name] = traces
        results[name] = summarise(traces, windows, transfer_models)
        if verbose:
            print(f"  {name:28s} {time.time() - t0:6.1f}s")

    return {
        "spec": vars(spec),
        "source": source,
        "curation_seeds": list(CURATION_SEEDS),
        "transfer_seeds": list(TRANSFER_SEEDS),
        "results": results,
        "corpus": {
            "n": len(windows),
            "strata": _counts(w.stratum for w in windows),
            "contaminations": _counts(
                w.contamination for w in windows if w.contamination
            ),
        },
    }, traces_by_method


def _counts(it) -> dict:
    out = {}
    for k in it:
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def render_report(payload: dict) -> str:
    """Markdown summary of the headline table plus per-family detail."""
    res = payload["results"]
    lines = ["# IntroAct-TS results", ""]
    lines.append(
        f"Corpus: {payload['corpus']['n']} windows, source `{payload['source']}`. "
        f"Curation models {payload['curation_seeds']}, "
        f"transfer models {payload['transfer_seeds']} (never consulted during curation)."
    )
    lines.append("")
    lines.append("## Headline")
    lines.append("")
    lines.append(
        "| method | detect F1 | action acc | repair NMSE red. | over-clean rate | "
        "damage to protected | rollbacks | abstain |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for name, r in res.items():
        lines.append(
            f"| {name} | {r['detection']['f1']:.3f} | {r['action']['action_accuracy']:.3f} "
            f"| {r['repair'].get('reduction', 0.0):.3f} "
            f"| {r['protection']['over_clean_rate']:.3f} "
            f"| {r['protection']['mean_damage']:.4f} "
            f"| {r['rollback']['n_rolled_back']} "
            f"| {r['rollback']['abstain_rate']:.3f} |"
        )

    lines += ["", "## Transfer to models that took no part in curation", ""]
    transfer_names = list(next(iter(res.values())).get("transfer", {}).keys())
    lines.append("| method | " + " | ".join(transfer_names) + " |")
    lines.append("|---" * (len(transfer_names) + 1) + "|")
    for name, r in res.items():
        cells = [
            f"{r['transfer'][m]['improvement']:+.4f}" for m in transfer_names
        ]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")

    lines += ["", "## Repair by contamination type (IntroAct-TS full)", ""]
    per = res["introact_full"]["repair"].get("per_contamination", {})
    lines.append("| contamination | NMSE before | NMSE after | reduction | action acc |")
    lines.append("|---|---|---|---|---|")
    per_action = res["introact_full"]["action"]["per_contamination"]
    for kind, v in sorted(per.items()):
        acc = per_action.get(kind, {})
        rate = acc.get("hit", 0) / max(acc.get("n", 1), 1)
        lines.append(
            f"| {kind} | {v['before']:.4f} | {v['after']:.4f} | {v['reduction']:+.3f} "
            f"| {rate:.3f} |"
        )

    lines += ["", "## Protection by stratum (IntroAct-TS full)", ""]
    lines.append("| stratum | n | modified | over-clean rate | mean damage |")
    lines.append("|---|---|---|---|---|")
    for k, v in sorted(res["introact_full"]["protection"]["per_stratum"].items()):
        lines.append(
            f"| {k} | {v['n']} | {v['modified']} | {v['over_clean_rate']:.3f} "
            f"| {v['mean_damage']:.4f} |"
        )

    lines += ["", "## Rollback reasons (IntroAct-TS full)", ""]
    rb = res["introact_full"]["rollback"]
    for reason, count in sorted(rb["by_reason"].items()):
        lines.append(f"- `{reason}`: {count}")
    lines.append(
        f"- protected windows saved by a rollback: "
        f"{rb['protected_windows_with_rollback']}"
    )
    lines.append(f"- mean probe calls per window: {rb['mean_probe_calls']:.2f}")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", choices=list(SCALES), default="small")
    ap.add_argument("--source", choices=["ett", "synthetic"], default="ett")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=str, default=str(ROOT / "results"))
    args = ap.parse_args()

    spec = SCALES[args.scale]
    spec.seed = args.seed
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    payload, traces = run_all(spec, args.source)
    payload["wall_time_s"] = time.time() - t0

    stem = f"{args.scale}_{args.source}_seed{args.seed}"
    (out_dir / f"{stem}.json").write_text(
        json.dumps(payload, indent=2, default=float), encoding="utf-8"
    )
    (out_dir / f"{stem}.md").write_text(render_report(payload), encoding="utf-8")

    traces_out = {
        m: [t.summary() for t in ts] for m, ts in traces.items()
    }
    (out_dir / f"{stem}_traces.json").write_text(
        json.dumps(traces_out, indent=2, default=float), encoding="utf-8"
    )

    print(f"\ndone in {payload['wall_time_s']:.0f}s -> {out_dir / (stem + '.md')}")
    print(render_report(payload))


if __name__ == "__main__":
    main()
