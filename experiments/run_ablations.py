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
from spo_feasibility import profile_matrix  # noqa: E402
from metrics import summarise  # noqa: E402
from run_agent import SCALES  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.policy import PolicyConfig  # noqa: E402
from introact_ts.spo import SPOConfig, SPOPolicy, ValueTables  # noqa: E402
from introact_ts.verify import VerifyConfig  # noqa: E402


def cluster_labels(windows, k, seed=42, n_jobs=32):
    """One profile clustering, shared by every rung that learns."""
    from sklearn.cluster import KMeans
    P = profile_matrix(windows, n_jobs=n_jobs)
    return KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(P)


def ladder() -> dict:
    """Six rungs, matching section 4.2's ablation group exactly.

    The eight rung version this replaces is described in
    `docs/CHANGELOG.md` under the 2026-08-22 consolidation. Three rungs were
    removed on measured grounds rather than for budget, and each reason is in
    section 4.2 so a reader does not have to take the list on trust:

      no utility condition   the utility condition vetoed 769 candidates against
                             the structural condition's 616, so removing it
                             leaves an acceptance set close to no shield at all
      no budget allocation   its effect already appears in the main table's cost
                             column and its two probe count columns
      no peer calibration    early measurement found no detectable difference in
                             discriminative power against global standardisation,
                             and that result stays in section 6.1

    Two rungs of the old ladder are gone for a different reason. `f_single_step`
    and `g_no_abstain` have no landing place in the document: neither appears in
    section 4.2's design and neither isolates a component the method claims. They
    are removed rather than carried as orphans.

    Three of the six rungs need the policy, so this module now builds one.
    """
    return {
        # a. every proposal committed unconditionally
        "a_no_shield": dict(
            agent=AgentConfig(verification=VerifyConfig(
                require_structure=False, require_reprobe=False,
                require_risk=False)),
            policy=True, inject=True, shaped_reward=True),
        # b. utility recheck only, no structural veto
        "b_no_structural": dict(
            agent=AgentConfig(verification=VerifyConfig(require_structure=False)),
            policy=True, inject=True, shaped_reward=True),
        # c. the fixed rule, so the shield stands but nothing is learned
        "c_no_policy": dict(
            agent=AgentConfig(), policy=False, inject=False, shaped_reward=True),
        # d. the policy learns but cannot try what the proposer never offers
        "d_no_injection": dict(
            agent=AgentConfig(), policy=True, inject=False, shaped_reward=True),
        # e. the policy learns from the raw utility change rather than the
        #    shielded reward. This is section 3.3's second claim, that the shield
        #    shapes what the policy learns as well as gating what it commits.
        "e_raw_reward": dict(
            agent=AgentConfig(), policy=True, inject=True, shaped_reward=False),
        # f. everything on
        "f_full": dict(
            agent=AgentConfig(), policy=True, inject=True, shaped_reward=True),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="heavy", choices=list(SCALES))
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--taus", type=float, nargs="*",
                    default=[0.04, 0.08, 0.12, 0.20, 0.30])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--k", type=int, default=12)
    ap.add_argument("--p-inject", dest="p_inject", type=float, default=0.05)
    ap.add_argument("--t-cal", dest="t_cal", type=int, default=500)
    ap.add_argument("--reward-clip", dest="reward_clip", type=float,
                    default=5.886732284690514)
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=32)
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

    # Cluster labels for the policy. Every rung that learns shares one
    # clustering, so a difference between rungs is the rung and not a different
    # partition of the corpus.
    clusters = cluster_labels(windows, args.k, seed=args.seed,
                              n_jobs=args.n_jobs)

    for name, rung in ladder().items():
        t0 = time.time()
        agent = IntroActAgent(models, rung["agent"])
        agent._calib = reference._calib
        agent._ood = reference._ood
        agent._reference = reference._reference

        policy = None
        if rung["policy"]:
            # A rung that learns starts from a cold table rather than the warm
            # start, so the six rungs differ only by what this loop switches and
            # not by what history happened to be available to each.
            cfg = SPOConfig(reward_clip=args.reward_clip,
                            t_cal=args.t_cal)
            tables = ValueTables(n_clusters=args.k, cfg=cfg)
            policy = SPOPolicy(tables, cfg,
                               p_inject=args.p_inject if rung["inject"] else 0.0,
                               seed=args.seed)
            policy.shaped_reward = rung["shaped_reward"]

        traces = [agent.curate_window(
                      w, s, peer_idx=i, policy=policy,
                      cluster=int(clusters[i]) if policy is not None else None)
                  for i, (w, s) in enumerate(zip(windows, states))]
        payload["rungs"][name] = summarise(traces, windows, transfer)
        if policy is not None:
            payload["rungs"][name]["injections"] = int(sum(policy.injected.values()))
            payload["rungs"][name]["theorem6"] = policy.theorem6_report()
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
