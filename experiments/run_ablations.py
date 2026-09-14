"""Ablation ladder, on the main table's corpus and in the main table's columns.

Section 4.2's ablation group. Seven rungs, with the full method as the reference
row rather than a rung.

**Three things about this file exist so its rows can sit beside the main
table's.** Each was a real mismatch before it was fixed, and each would have
cost a GPU pass to discover after the fact.

  the corpus     `--source` defaults to `mixed`, which is what the main table
                 runs on. This file used to hard code `ett`, so a rung and a
                 main table row were computed on different data
  the columns    `run_main.score_rows` produces the four columns, so a rung and
                 a row carry the same quantity under the same name. This file
                 used to call `metrics.summarise`, which does not produce the
                 protected mis edit rate or the repair nRMSD at all
  the traces     the same JSONL as the main table, so a口径 change is
                 recomputable offline for a rung exactly as it is for a row

**What the full method is, and what the main table's `introact` row is.** They
are not the same configuration and the difference has to be stated wherever
both appear. `run_main.agent_traces` calls `curate_window` without a policy,
which is the fixed proposer ordering, so **the main table's `introact` row is
the fixed rule**. The rung that matches it is `c_no_policy`, and that identity
is what the smoke test checks. `f_full` adds the learned ordering and the
candidate injection on top, and it is the row experiment three and this ladder
are about.

**A4 and the conformal threshold.** Conformal calibration reaches the run
offline rather than inside it: `experiments/run_conformal.py` produces
`results/conformal.json`, whose lambda star at alpha 0.03 is 0.02, and that is
the `--tau 0.02` every main table run was launched with. Removing the
calibration therefore means putting back the number it replaced, which
`src/introact_ts/conformal.py` records as the hand set 0.12. That is the whole
of rung `g_no_conformal`, and it is a fair statement of the counterfactual
because 0.12 is what this project actually used before the procedure existed,
not a value chosen now to lose.

Perception is computed once per seed and shared by every rung of that seed. A
seed whose rungs are all on disk is skipped before perception, which is the
expensive part.

Usage:
    python -u experiments/run_ablations.py --source mixed --scale xl --seeds 0,1,2
    python -u experiments/run_ablations.py --source mixed --scale small \
        --seeds 0 --levels c_no_policy      # the smoke test, see above
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
from run_agent import SCALES  # noqa: E402
from run_main import dump_window_traces, score_rows  # noqa: E402
from spo_feasibility import profile_matrix  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.spo import SPOConfig, SPOPolicy, ValueTables  # noqa: E402
from introact_ts.verify import VerifyConfig  # noqa: E402

#: The threshold this project used before conformal calibration existed, from
#: `src/introact_ts/conformal.py`. Rung `g_no_conformal` puts it back.
HAND_SET_TAU = 0.12

#: The columns a rung reports, in the main table's order and under the main
#: table's names. Anything else `score_rows` returns is kept in the file but not
#: printed.
HEADLINE = ("committed_edits", "protected_mis_edit_rate", "damage_rate",
            "repair_nrmsd")


def cluster_labels(windows, k, seed=42, n_jobs=32):
    """One profile clustering, shared by every rung that learns."""
    from sklearn.cluster import KMeans
    P = profile_matrix(windows, n_jobs=n_jobs)
    return KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(P)


def ladder(tau: float) -> dict:
    """Seven rungs, matching section 4.2's ablation group exactly.

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
    section 4.2's design and neither isolates a component the method claims.
    They are removed rather than carried as orphans.

    `tau` is threaded in rather than left at the config default so that every
    rung except `g_no_conformal` runs at the calibrated threshold the main table
    ran at, which is the only way a rung and a row are comparable.
    """
    return {
        # A1. every proposal committed unconditionally
        "a_no_shield": dict(
            matrix_id="A1",
            agent=AgentConfig(verification=VerifyConfig(
                tau=tau, require_structure=False, require_reprobe=False,
                require_risk=False)),
            policy=True, inject=True, shaped_reward=True),
        # A2. utility recheck only, no structural veto
        "b_no_structural": dict(
            matrix_id="A2",
            agent=AgentConfig(verification=VerifyConfig(
                tau=tau, require_structure=False)),
            policy=True, inject=True, shaped_reward=True),
        # A5. the fixed rule, so the shield stands but nothing is learned. This
        #     is also the main table's `introact` configuration, see the module
        #     docstring, and the smoke test relies on that identity.
        "c_no_policy": dict(
            matrix_id="A5",
            agent=AgentConfig(verification=VerifyConfig(tau=tau)),
            policy=False, inject=False, shaped_reward=True),
        # A6. the policy learns but cannot try what the proposer never offers
        "d_no_injection": dict(
            matrix_id="A6",
            agent=AgentConfig(verification=VerifyConfig(tau=tau)),
            policy=True, inject=False, shaped_reward=True),
        # A3. the policy learns from the raw utility change rather than the
        #     shielded reward. This is section 3.3's second claim, that the
        #     shield shapes what the policy learns as well as gating what it
        #     commits.
        "e_raw_reward": dict(
            matrix_id="A3",
            agent=AgentConfig(verification=VerifyConfig(tau=tau)),
            policy=True, inject=True, shaped_reward=False),
        # A4. the threshold is the hand set constant the calibration replaced,
        #     see the module docstring for where 0.12 comes from.
        "g_no_conformal": dict(
            matrix_id="A4",
            agent=AgentConfig(verification=VerifyConfig(tau=HAND_SET_TAU)),
            policy=True, inject=True, shaped_reward=True),
        # the reference row, everything on
        "f_full": dict(
            matrix_id="full",
            agent=AgentConfig(verification=VerifyConfig(tau=tau)),
            policy=True, inject=True, shaped_reward=True),
    }


def result_path(out_dir, level, seed):
    return Path(out_dir) / f"ablation_{level}_seed{seed}.json"


def run_one(level, rung, windows, states, models, reference, clusters, args):
    """One rung on one seed, in the main table's columns."""
    agent = IntroActAgent(models, rung["agent"])
    agent._calib = reference._calib
    agent._ood = reference._ood
    agent._reference = reference._reference

    policy = None
    if rung["policy"]:
        # A rung that learns starts from a cold table rather than the warm
        # start, so the rungs differ only by what this switches and not by what
        # history happened to be available to each.
        cfg = SPOConfig(reward_clip=args.reward_clip, t_cal=args.t_cal)
        tables = ValueTables(n_clusters=args.k, cfg=cfg)
        policy = SPOPolicy(tables, cfg,
                           p_inject=args.p_inject if rung["inject"] else 0.0,
                           seed=args.seed_of_run)
        policy.shaped_reward = rung["shaped_reward"]

    traces = [agent.curate_window(
                  w, s, peer_idx=i, policy=policy,
                  cluster=int(clusters[i]) if policy is not None else None)
              for i, (w, s) in enumerate(zip(windows, states))]

    row = score_rows(traces, windows)
    row["matrix_id"] = rung["matrix_id"]
    row["tau"] = float(rung["agent"].verification.tau)
    row["policy"] = bool(rung["policy"])
    row["inject"] = bool(rung["inject"])
    row["shaped_reward"] = bool(rung["shaped_reward"])
    if policy is not None:
        row["injections"] = int(sum(policy.injected.values()))
        row["theorem6"] = policy.theorem6_report()
    return row, traces


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="xl", choices=list(SCALES))
    #: Defaults to the main table's corpus. See the module docstring.
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--seeds", default="0",
                    help="comma separated, one full ladder per seed")
    ap.add_argument("--levels", nargs="*", default=None,
                    help="rung names to run, default every rung")
    #: The calibrated threshold, the same value every main table run used. See
    #: the module docstring for where it comes from.
    ap.add_argument("--tau", type=float, default=0.02)
    ap.add_argument("--k", type=int, default=12)
    ap.add_argument("--p-inject", dest="p_inject", type=float, default=0.05)
    ap.add_argument("--t-cal", dest="t_cal", type=int, default=500)
    ap.add_argument("--reward-clip", dest="reward_clip", type=float,
                    default=5.886732284690514)
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=32)
    ap.add_argument("--out", default=str(ROOT / "results" / "xl"))
    ap.add_argument("--fresh", action="store_true",
                    help="ignore results already on disk and recompute")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    seeds = [int(s) for s in str(args.seeds).replace(" ", "").split(",") if s]
    rungs_all = ladder(args.tau)
    levels = args.levels or list(rungs_all)
    unknown = [x for x in levels if x not in rungs_all]
    if unknown:
        raise SystemExit(f"unknown rung {unknown}, choose from {list(rungs_all)}")

    print(f"seeds {seeds}, rungs {levels}, source {args.source}, "
          f"scale {args.scale}, tau {args.tau}", flush=True)

    models = transfer = None
    for seed in seeds:
        todo = [lv for lv in levels
                if args.fresh or not result_path(out_dir, lv, seed).exists()]
        done = [lv for lv in levels if lv not in todo]
        if done:
            print(f"seed {seed}, already on disk, skipped: {done}", flush=True)
        if not todo:
            continue

        args.seed_of_run = seed
        spec = SCALES[args.scale]
        spec.seed = seed
        windows = build_corpus(spec, source=args.source)
        if models is None:
            models = make_pool(PRESETS[args.preset]["curation"],
                               device=args.device)
        print(f"seed {seed}, corpus {len(windows)} windows", flush=True)

        # Perception is the expensive part and is shared by every rung of this
        # seed, which is why the skip check above happens before it.
        reference = IntroActAgent(models, AgentConfig(
            verification=VerifyConfig(tau=args.tau), n_jobs=args.n_jobs))
        t0 = time.time()
        states = reference.perceive(windows)
        print(f"  perception {time.time() - t0:.0f}s", flush=True)

        clusters = cluster_labels(windows, args.k, seed=seed,
                                  n_jobs=args.n_jobs)

        for level in todo:
            t0 = time.time()
            row, traces = run_one(level, rungs_all[level], windows, states,
                                  models, reference, clusters, args)
            row["compute_seconds"] = time.time() - t0
            row["seed"] = seed
            row["scale"] = args.scale
            row["source"] = args.source
            row["n_windows"] = len(windows)

            tp = out_dir / f"ablation_{level}_seed{seed}_traces.jsonl"
            if tp.exists():
                tp.unlink()
            row["traces_written"] = dump_window_traces(traces, windows, tp,
                                                       level)
            result_path(out_dir, level, seed).write_text(
                json.dumps(row, indent=1, default=float), encoding="utf-8")

            rr = row.get("repair_nrmsd")
            print(f"  {level:16s}[{row['matrix_id']:4s}] "
                  f"edits {row['committed_edits']:5d}  "
                  f"mis rate {row['protected_mis_edit_rate']:.4f}  "
                  f"damage {row['damage_rate']:.4f}  "
                  f"nrmsd {rr:8.4f}  {row['compute_seconds']:6.0f}s"
                  if rr is not None else
                  f"  {level:16s}[{row['matrix_id']:4s}] "
                  f"edits {row['committed_edits']:5d}", flush=True)

    print("___ABLATIONS_DONE___", flush=True)


if __name__ == "__main__":
    main()
