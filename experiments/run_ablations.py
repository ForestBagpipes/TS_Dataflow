"""Ablation ladder and acceptance threshold sweep, one perception pass.

Seven rungs plus the full agent. Two of them are new and are the reason this
runs separately from the main experiment: a single step policy that cannot
retry after a rejection, which isolates the value of being reversible from the
value of vetoing, and a policy with no refusal floor, which isolates ABSTAIN.

The tau sweep re runs the full agent at several structural thresholds. It could
in principle be replayed offline from cached probe results, but a change to tau
changes which candidates are accepted, which changes the state the next
candidate is judged against, so a replay would only be exact for the first
decision in each window. Re running is a few minutes and is exact.

Perception is computed once and shared by every configuration.

Usage:
    python -u experiments/run_ablations.py --scale heavy --taus 0.04 0.08 0.12 0.20 0.30
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from corpus import build_corpus  # noqa: E402
from metrics import summarise  # noqa: E402
from run_agent import SCALES  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.policy import PolicyConfig  # noqa: E402
from introact_ts.verify import VerifyConfig  # noqa: E402


def ladder() -> dict:
    """Eight configurations, ordered from doing nothing to doing everything."""
    return {
        # a. perception only, nothing is edited
        "a_no_action": None,
        # b. every proposal committed unconditionally
        "b_no_verification": AgentConfig(
            verification=VerifyConfig(
                require_structure=False, require_reprobe=False, require_risk=False
            )
        ),
        # c. structural veto only, model utility never consulted after the edit
        "c_no_utility_recheck": AgentConfig(
            verification=VerifyConfig(require_reprobe=False)
        ),
        # d. utility recheck only, no structural veto
        "d_no_structural_veto": AgentConfig(
            verification=VerifyConfig(require_structure=False)
        ),
        # e. behaviour z scored against the whole corpus rather than peers
        "e_no_peer_calibration": AgentConfig(peer_calibration=False),
        # f. one shot. a rejected candidate ends the episode, so vetoing still
        #    happens but recovering from a veto does not
        "f_single_step": AgentConfig(policy=PolicyConfig(max_candidates=1)),
        # g. no refusal floor, the agent must always name an action
        "g_no_abstain": AgentConfig(policy=PolicyConfig(min_confidence=0.0)),
        # h. everything on
        "h_full": AgentConfig(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="heavy", choices=list(SCALES))
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--taus", type=float, nargs="*",
                    default=[0.04, 0.08, 0.12, 0.20, 0.30])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(ROOT / "results" / "ablations"))
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    spec = SCALES[args.scale]
    spec.seed = args.seed
    windows = build_corpus(spec, source="ett")
    pools = PRESETS[args.preset]
    models = make_pool(pools["curation"], device=args.device)
    transfer = make_pool(pools["transfer"], device=args.device)
    print(f"corpus {len(windows)} windows, scale {args.scale}", flush=True)

    reference = IntroActAgent(models, AgentConfig())
    t0 = time.time()
    states = reference.perceive(windows)
    print(f"perception {time.time() - t0:.0f}s", flush=True)

    from baselines import run_no_action

    payload = {"scale": args.scale, "n_windows": len(windows), "rungs": {}, "tau": {}}

    for name, cfg in ladder().items():
        t0 = time.time()
        if cfg is None:
            traces = run_no_action(windows, states, models)
        else:
            agent = IntroActAgent(models, cfg)
            if cfg.peer_calibration:
                agent._calib = reference._calib
                agent._ood = reference._ood
                agent._reference = reference._reference
                run_states = states
            else:
                run_states = agent.perceive(windows)
            traces = [agent.curate_window(w, s, peer_idx=i)
                      for i, (w, s) in enumerate(zip(windows, run_states))]
        payload["rungs"][name] = summarise(traces, windows, transfer)
        print(f"  {name:24s} {time.time() - t0:6.0f}s", flush=True)
        (out_dir / "ablations.json").write_text(
            json.dumps(payload, indent=2, default=float), encoding="utf-8")

    for tau in args.taus:
        t0 = time.time()
        agent = IntroActAgent(models, AgentConfig(verification=VerifyConfig(tau=tau)))
        agent._calib = reference._calib
        agent._ood = reference._ood
        agent._reference = reference._reference
        traces = [agent.curate_window(w, s, peer_idx=i)
                  for i, (w, s) in enumerate(zip(windows, states))]
        payload["tau"][f"{tau:.2f}"] = summarise(traces, windows, transfer)
        print(f"  tau={tau:.2f}{'':17s} {time.time() - t0:6.0f}s", flush=True)
        (out_dir / "ablations.json").write_text(
            json.dumps(payload, indent=2, default=float), encoding="utf-8")

    print("___ABLATIONS_DONE___", flush=True)


if __name__ == "__main__":
    main()
