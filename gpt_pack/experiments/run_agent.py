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
from downstream import compare as downstream_compare  # noqa: E402
from downstream import evaluate as downstream_evaluate  # noqa: E402
from downstream import split_windows  # noqa: E402
from metrics import summarise  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool, probe_signature  # noqa: E402
from introact_ts.policy import PolicyConfig  # noqa: E402
from introact_ts.probe import ProbeConfig  # noqa: E402
from introact_ts.verify import VerifyConfig  # noqa: E402

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
    # A heavily contaminated corpus. Downstream transfer is insensitive to a
    # conservative method at low contamination -- a handful of repaired windows
    # is diluted across thousands of training pairs -- so the regime where
    # curation can actually move the number has to be tested explicitly.
    # Publication scale. 210 windows cannot carry a claim, and the strata that
    # matter most for the protection argument had only ten members each.
    "xl": CorpusSpec(
        n_contaminated=740, n_clean=420, n_hard=210,
        n_rare_valid=210, n_changepoint=210, n_clean_ood=210,
    ),
    "heavy": CorpusSpec(
        n_contaminated=140, n_clean=20, n_hard=10, n_rare_valid=20,
        n_changepoint=10, n_clean_ood=10,
    ),
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


def run_all(
    spec: CorpusSpec,
    source: str,
    preset: str = "offline",
    device: str = "cpu",
    downstream: bool = True,
    downstream_deep: bool = False,
    verbose: bool = True,
) -> dict:
    windows = build_corpus(spec, source=source)
    pools = PRESETS[preset]
    curation_models = make_pool(pools["curation"], device=device)
    transfer_models = make_pool(pools["transfer"], device=device)
    if verbose:
        print(f"corpus: {len(windows)} windows from {source}")
        print(f"curation: {[probe_signature(m)['name'] for m in curation_models]}")
        print(f"transfer: {[probe_signature(m)['name'] for m in transfer_models]}")

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

    downstream_results = {}
    if downstream:
        # Split before curation so no test window can influence a model that is
        # later scored on it, and use the same split for every method.
        train_ids, test_ids = split_windows(windows, seed=spec.seed)
        if verbose:
            deep = " (+patchtst)" if downstream_deep else ""
            print(
                f"\ndownstream: {len(train_ids)} train / "
                f"{len(test_ids)} test windows{deep}"
            )
        for name, traces in traces_by_method.items():
            t0 = time.time()
            downstream_results[name] = downstream_evaluate(
                traces, windows, train_ids, test_ids,
                include_deep=downstream_deep, seed=spec.seed,
            )
            if verbose:
                print(f"  {name:28s} {time.time() - t0:6.1f}s")
        downstream_results = {
            "absolute": downstream_results,
            "relative_to_no_action": downstream_compare(downstream_results),
            "n_train_windows": len(train_ids),
            "n_test_windows": len(test_ids),
        }

    return {
        "spec": vars(spec),
        "source": source,
        "preset": preset,
        "downstream": downstream_results,
        "curation_models": [probe_signature(m) for m in curation_models],
        "transfer_models": [probe_signature(m) for m in transfer_models],
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
    cur = ", ".join(f"`{m['name']}`" for m in payload["curation_models"])
    tra = ", ".join(f"`{m['name']}`" for m in payload["transfer_models"])
    lines.append(
        f"Corpus: {payload['corpus']['n']} windows, source `{payload['source']}`, "
        f"backend preset `{payload['preset']}`."
    )
    lines.append("")
    lines.append(f"- Curation (judge + disagreement pool): {cur}")
    lines.append(f"- Transfer (never consulted during curation): {tra}")
    caps = {m["name"]: m["capabilities"] for m in payload["curation_models"]}
    lines.append(f"- Capabilities: {caps}")
    lines.append("")
    lines.append("## Headline")
    lines.append("")
    lines.append(
        "| method | **net corpus** | repair (contaminated) | over-clean rate | "
        "damage to protected | detect F1 | action acc | rollbacks | abstain |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for name, r in res.items():
        ce = r.get("corpus_effect", {})
        lines.append(
            f"| {name} | **{ce.get('net_reduction', 0.0):+.3f}** "
            f"| {r['repair'].get('reduction', 0.0):.3f} "
            f"| {r['protection']['over_clean_rate']:.3f} "
            f"| {r['protection']['mean_damage']:.4f} "
            f"| {r['detection']['f1']:.3f} | {r['action']['action_accuracy']:.3f} "
            f"| {r['rollback']['n_rolled_back']} "
            f"| {r['rollback']['abstain_rate']:.3f} |"
        )
    lines += [
        "",
        "`net corpus` is the reduction in mean normalised distance-to-truth over "
        "*every* window with a pristine reference, contaminated and protected "
        "alike. Repair and damage are trade-offs against each other and neither "
        "column alone can say whether running the pipeline was worth it; this "
        "one can.",
        "",
        "| method | windows improved | windows worsened |",
        "|---|---|---|",
    ]
    for name, r in res.items():
        ce = r.get("corpus_effect", {})
        lines.append(
            f"| {name} | {ce.get('windows_improved', 0)} "
            f"| {ce.get('windows_worsened', 0)} |"
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

    down = payload.get("downstream") or {}
    if down.get("absolute"):
        lines += [
            "",
            "## Downstream transfer: train on curated data, test on pristine data",
            "",
            f"Models are trained from scratch on each method's output "
            f"({down['n_train_windows']} windows) and scored on the untouched "
            f"reference series of {down['n_test_windows']} held-out windows. "
            f"Values are test MSE; the arrow is the change against `no_action`.",
            "",
        ]
        ref_scores = down["absolute"]["no_action"]
        model_names = [
            k for k, v in ref_scores.items()
            if isinstance(v, dict) and v.get("trainable", True)
        ]
        untrained = [
            (k, v) for k, v in ref_scores.items()
            if isinstance(v, dict) and not v.get("trainable", True)
        ]
        for k, v in untrained:
            lines.append(
                f"Training-independent reference on the same test split: "
                f"`{k}` MSE {v['mse']:.4f}."
            )
            lines.append("")
        lines.append("| method | " + " | ".join(model_names) + " |")
        lines.append("|---" * (len(model_names) + 1) + "|")
        for name, scores in down["absolute"].items():
            rel = down["relative_to_no_action"].get(name, {})
            cells = []
            for m in model_names:
                if m not in scores or "error" in scores:
                    cells.append("n/a")
                    continue
                imp = rel.get(m, {}).get("improvement", 0.0)
                cells.append(f"{scores[m]['mse']:.4f} ({imp:+.1%})")
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
    ap.add_argument("--preset", choices=list(PRESETS), default="offline",
                    help="which frozen backends to use; see introact_ts.backends.PRESETS")
    ap.add_argument("--device", default="cpu", help="cpu or cuda")
    ap.add_argument("--no-downstream", action="store_true",
                    help="skip train-on-curated / test-on-clean evaluation")
    ap.add_argument("--downstream-deep", action="store_true",
                    help="also train a PatchTST per method (slower)")
    ap.add_argument("--out", type=str, default=str(ROOT / "results"))
    args = ap.parse_args()

    spec = SCALES[args.scale]
    spec.seed = args.seed
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    payload, traces = run_all(
        spec, args.source, preset=args.preset, device=args.device,
        downstream=not args.no_downstream, downstream_deep=args.downstream_deep,
    )
    payload["wall_time_s"] = time.time() - t0

    stem = f"{args.scale}_{args.source}_{args.preset}_seed{args.seed}"
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
