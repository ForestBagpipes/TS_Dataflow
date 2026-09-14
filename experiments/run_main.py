"""The main experiment, every baseline in one table under the corpus protocol.

Section 4.2's first group. It is the only place where all eight baselines and
this paper's method are compared on the same corpus with the same downstream
model, so its job is to make the rows commensurable rather than to be clever.

**Rows.** Section 4.1.3's list, plus the two references and the four
adjudication contrasts:

    no_action, oracle                     the lower and upper reference
    screen, imr, mtcsc                    the repair family
    timeinf, data_oob, data_shapley, ltsv the valuation family
    soft_penalty, utility_only,           the adjudication contrasts
    spec_veto, no_shield
    introact                              this paper
    tsrating                              a retained row, marked not applicable

TSRating keeps its row. `docs/baseline_year_gap.md` records why it carries no
numbers: the substituted judgment backend flips its preference on half of all
pairs with reasoning off, and with reasoning on a third of pairs return no
parseable answer because reasoning exhausts the token budget, so the surviving
pairs are the easy ones. A row that is dropped is a row a reader cannot check.

**Columns.** Section 4.1.4's five, plus the two the budget mechanism needs:

    downstream error        PatchTST and DLinear on the prepared corpus
    protected mis edits     windows touched in clean, hard, rare_valid, changepoint
    damage rate             definition 1, over committed edits
    repair gain             distance reduction to the clean reference
    compute cost            seconds and accelerator occupancy to prepare the corpus
    probes saved            probes avoided by skipping settled windows
    missed windows          of those skipped, how many actually carried a defect

The last two are reported together always. Reporting the saving without the miss
would make the mechanism look free.

**Two protocols, and which column comes from which.** The valuation family
produces a smaller corpus and no per action verdict, the repair family rewrites
in place. All seven columns above are corpus level and every row can produce
them. Anything that needs a per action verdict, acceptance rate or rollback
reason, is analysis and lives in the text rather than here.

A row that genuinely cannot produce a cell gets `not_applicable` with a reason
string, never a blank and never a silently omitted row.

Usage:
    python -u experiments/run_main.py --scale xl --device cuda
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
sys.path.insert(0, str(ROOT / "tools"))

from monitor import Monitor  # noqa: E402

from corpus import build_corpus  # noqa: E402
from run_agent import SCALES  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.structure import _discard_distortion  # noqa: E402
from introact_ts.verify import VerifyConfig  # noqa: E402
from introact_ts.types import GovernanceTrace  # noqa: E402

#: Strata whose windows must not be edited. `clean_ood` is the synthetic probe
#: layer of the 4.1.2 ruling and is scored separately, never summed in here.
PROTECTED = ("clean", "hard", "rare_valid", "changepoint")
PROBE_LAYER = "clean_ood"

#: Every row of the main table, in the order it is printed. The third field says
#: which family the row belongs to, which decides how its prepared corpus is
#: produced.
#: Baselines carry an L prefix, fixed in docs/experiment-matrix.md. The B
#: numbering that appears in docs/CHANGELOG.md refers to work items and stays
#: valid, the two are different registers and neither is retired.
#:
#: `no_shield` is no longer a baseline row. It changes one component of this
#: paper's method rather than being an independently published method, so it
#: belongs with the ablation and with experiment two's contrast. Learn2Clean
#: takes its place as L7, which is the published work that actually holds the
#: position no_shield was standing in for.
ROWS = [
    ("L0_no_action", "reference", "none"),
    ("L1_screen", "repair", "classic"),
    ("L2_imr", "repair", "classic"),
    ("L3_mtcsc", "repair", "classic"),
    ("L4_data_oob", "valuation", "scores"),
    ("L5_timeinf", "valuation", "scores"),
    ("L6_ltsv", "valuation", "scores"),
    ("L7_learn2clean", "learning", "l2c"),
    ("L8_tsrating", "valuation", "unavailable"),
    ("soft_penalty", "contrast", "soft"),
    ("utility_only", "contrast", "agent"),
    ("spec_veto", "contrast", "agent"),
    ("introact", "ours", "agent"),
    ("oracle", "reference", "oracle"),
]

#: Row name to the key its scores are stored under, since the score files
#: predate the L prefix.
SCORE_KEY = {"L4_data_oob": "data_oob", "L5_timeinf": "timeinf",
             "L6_ltsv": "ltsv", "L7_learn2clean": None}

#: Reasons a cell is not applicable, keyed by row. Printed in the table note.
NOT_APPLICABLE = {
    "L8_tsrating": (
        "the substituted judgment backend is not stable enough to distil a "
        "rater from. Three backend configurations were tried and all three "
        "failed: deepseek-v4-pro with reasoning off gives a 0.508 order flip "
        "rate, the same model with reasoning on gives zero flips but a 0.333 "
        "unscorable rate whose survivors are the easy pairs, and "
        "deepseek-v4-flash gives 0.833. The repository publishes no rater "
        "weights and no annotations, last pushed 2025-05-27 with zero "
        "releases, so there is no path that avoids generating judgments. "
        "See docs/baseline_year_gap.md"),
}

#: Columns every row must fill, so a missing one is an error rather than a gap.
COLUMNS = ("downstream_error", "protected_mis_edit_rate", "damage_rate",
           "repair_nrmsd", "compute_seconds", "probes_saved", "missed_windows")


def rank_within_dataset(windows, scores):
    """Replace each score by its rank inside its own dataset, normalised to [0, 1].

    Measured on the xl corpus, the raw scores are not scale free and the corpus
    now spans quantities three orders of magnitude apart. Selecting on them
    degenerates into selecting by magnitude: Data-OOB's raw top half takes zero
    percent of Crypto and one hundred percent of the staircase probe, and LTSV's
    takes zero percent of Crypto and eighty percent of ETTh1. Ranking inside a
    dataset first and merging the ranks removes that without touching what each
    method computes.

    This is the same device the changepoint and hard layers already use, and for
    the same reason: two families whose statistics do not share a scale cannot be
    merged by a single threshold or a single global order.

    Note that a global z score would change nothing at all. It is a monotone
    transform, selection depends only on the order, and the two give identical
    selections. Measured, not assumed.
    """
    from collections import defaultdict
    by_ds = defaultdict(list)
    ds_of = {int(w.window_id): w.dataset for w in windows}
    for wid in scores:
        by_ds[ds_of.get(int(wid), "unknown")].append(int(wid))
    out = {}
    for _, ids in by_ds.items():
        order = sorted(ids, key=lambda i: scores[i])
        n = len(order)
        for r, i in enumerate(order):
            out[i] = r / max(n - 1, 1)
    return out


def selection_corpus(windows, scores, fraction):
    """A valuation arm's prepared corpus, keeping the top fraction by score.

    Windows the method could not score are kept as not selected rather than
    dropped, which is the rule fixed in docs/valuation_family_protocol.md. A
    scorer that cannot score a window cannot retain it, and dropping them from
    the comparison would score the valuation arms on an easier corpus than the
    repair arms see.
    """
    scored = [(w, scores.get(int(w.window_id))) for w in windows]
    have = [(w, s) for w, s in scored if s is not None]
    unscored = [w for w, s in scored if s is None]
    # A score file computed on a different corpus shares no window id with this
    # one, and the arithmetic then produces a row of zeros rather than an error.
    # A silently empty selection arm is worse than a crash because it looks like
    # a result. The floor is well under the expected overlap, which is the
    # training split times the blockable share, so it fires only on a genuine
    # mismatch.
    overlap = len(have) / max(len(windows), 1)
    print(f"    score overlap {overlap:.3f} ({len(have)} of {len(windows)})",
          flush=True)
    if len(have) < 0.05 * len(windows):
        raise SystemExit(
            f"only {len(have)} of {len(windows)} windows carry a score, "
            f"the score file was computed on a different corpus")
    have.sort(key=lambda ws: -ws[1])
    keep_n = int(round(fraction * len(windows)))
    kept = [w for w, _ in have[:keep_n]]
    return kept, len(unscored)


def repair_traces(windows, states, name):
    """One repair family arm, run over the corpus.

    These rewrite in place and issue no probe, so they produce a trace whose
    edits are already committed. The speed bounds SCREEN and MTCSC need are
    estimated once over the whole corpus rather than per window, which is what
    their papers do and what stops each window from calibrating to itself.
    """
    from proposers_classic import (estimate_speed_bounds, imr_repair,
                                   mtcsc_uni_repair, screen_repair)
    s_min, s_max = estimate_speed_bounds([w.series for w in windows])
    out = []
    for w, st in zip(windows, states):
        x = np.asarray(w.series, dtype=np.float64)
        if name == "screen":
            y = screen_repair(x, s_min, s_max)
        elif name == "imr":
            y = imr_repair(x)
        elif name == "mtcsc":
            y = mtcsc_uni_repair(x, s_min, s_max)
        else:
            raise ValueError(name)
        y = np.asarray(y, dtype=np.float64)
        changed = bool(np.any(np.abs(y - x) > 1e-9))
        out.append(GovernanceTrace(
            window_id=w.window_id, stratum=w.stratum,
            contamination=w.contamination,
            initial_series=x.copy(), final_series=y,
            records=[], final_state="COMMIT" if changed else "KEEP",
            initial_utility=float(st.utility), final_utility=float(st.utility),
            risk_state={}, probe_calls=0, crop_offset=0))
    return out


def oracle_traces(windows, states):
    """The upper reference, which knows the clean series and restores it.

    It edits contaminated windows only and leaves every protected window alone,
    so its damage is zero and its repair gain is the ceiling. It is a bound
    rather than a method and is labelled as one.
    """
    out = []
    for w, st in zip(windows, states):
        x = np.asarray(w.series, dtype=np.float64)
        if w.stratum == "contaminated" and w.clean_series is not None:
            y = np.asarray(w.clean_series, dtype=np.float64).copy()
            state = "COMMIT"
        else:
            y, state = x.copy(), "KEEP"
        out.append(GovernanceTrace(
            window_id=w.window_id, stratum=w.stratum,
            contamination=w.contamination,
            initial_series=x.copy(), final_series=y, records=[],
            final_state=state, initial_utility=float(st.utility),
            final_utility=float(st.utility), risk_state={},
            probe_calls=0, crop_offset=0))
    return out


#: The four adjudication contrasts, as VerifyConfig overrides. They share the
#: proposer and therefore the candidate set, so the only thing that differs is
#: what the verdict is computed from. That shared candidate set is what makes
#: them comparable to each other and to the full method.
CONTRASTS = {
    "utility_only": dict(require_structure=False, require_risk=False),
    "spec_veto": dict(require_reprobe=False, require_risk=False),
    "no_shield": dict(require_structure=False, require_reprobe=False,
                      require_risk=False),
    # The competing design, decided by a weighted sum rather than a
    # conjunction. It runs through the same `agent_traces` as every other
    # contrast, so it differs from ours in the decision rule and in nothing
    # else. See `VerifyConfig.soft_mu`.
    "soft_penalty": dict(soft_mu=None),   # filled from SOFT_MU at call time
}


#: Penalty coefficient for the soft arm. `experiments/soft_vs_hard.py` sweeps
#: the whole range, and the main table carries one point from that sweep so the
#: row is a method rather than a family. The value is the one that swept best on
#: damage, which is the strongest form of the competing design rather than a
#: convenient one.
SOFT_MU = 10.0


def agent_traces(models, windows, states, name, tau, n_jobs, reference,
                 soft_mu=None):
    """One agent arm, all of them driven by VerifyConfig overrides."""
    over = dict(CONTRASTS.get(name, {}))
    if name == "soft_penalty":
        over["soft_mu"] = SOFT_MU if soft_mu is None else float(soft_mu)
    cfg = AgentConfig(verification=VerifyConfig(tau=tau, **over), n_jobs=n_jobs)
    agent = IntroActAgent(models, cfg)
    agent._calib = reference._calib
    agent._ood = reference._ood
    agent._reference = reference._reference
    return [agent.curate_window(w, s, peer_idx=i)
            for i, (w, s) in enumerate(zip(windows, states))]


def dump_window_traces(traces, windows, path, arm):
    """Append one line per candidate to a JSONL file.

    Written line by line rather than as one JSON document so that an
    interruption keeps whatever was already flushed. Every口径 change so far has
    needed the per candidate record and not had it, which cost two full reruns,
    so the fields below are the ones a recomputation needs rather than the ones
    that happen to be convenient:

      the operator, its parameters and the verdict
      the utility change and the structural distortion the shield saw
      the distance to the clean reference before and after the candidate

    The distances are what make a metric change recomputable offline. They are
    measured on the sandbox result, so a rolled back candidate carries the
    distance it would have produced had it been committed, which is exactly the
    counterfactual `shield_replay.py` has to reconstruct by re executing.
    """
    from introact_ts.actions import robust_scale
    byid = {w.window_id: w for w in windows}
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a", encoding="utf-8") as fh:
        for t in traces:
            w = byid.get(t.window_id)
            if w is None:
                continue
            src = np.asarray(w.series, dtype=np.float64)
            scale = max(float(robust_scale(src)), 1e-9)
            base = _dist(src, w.clean_series)
            final = _dist(t.final_series, w.clean_series, t.crop_offset)
            rec = {
                "arm": arm, "window_id": int(t.window_id),
                "stratum": w.stratum, "dataset": w.dataset,
                "contamination": w.contamination,
                "robust_scale": scale,
                "dist_before": base, "dist_after": final,
                "nrmsd_after": (final / scale) if final is not None else None,
                "final_state": t.final_state,
                "crop_offset": int(t.crop_offset),
                "modified": bool(t.content_modified(w.series)),
                "probe_calls": int(t.probe_calls),
                "steps": [
                    {"action": getattr(r.action, "value", str(r.action)),
                     "params": {k: (float(v) if isinstance(v, (int, float)) else v)
                                for k, v in dict(r.params).items()},
                     "verdict": getattr(r.verdict, "value", str(r.verdict)),
                     "delta_utility": float(r.delta_utility),
                     "struct_distortion": float(r.struct_distortion),
                     "risk": float(r.risk), "cost": float(r.cost)}
                    for r in t.records],
            }
            fh.write(json.dumps(rec, default=float) + chr(10))
            n += 1
    return n


def _dist(series, clean, crop=0):
    """Root mean square distance to the clean reference over the shared span."""
    if clean is None:
        return None
    a = np.asarray(series, dtype=np.float64)
    b = np.asarray(clean, dtype=np.float64)[crop:crop + len(a)]
    n = min(len(a), len(b))
    if n == 0:
        return None
    d = a[:n] - b[:n]
    d = d[np.isfinite(d)]
    return float(np.sqrt(np.mean(d ** 2))) if d.size else None


def score_rows(traces, windows):
    """The corpus level columns, from one arm's traces.

    Two of these changed口径 with the frozen matrix and the change is not
    cosmetic.

    **Repair accuracy is a normalised distance.** It was `1 - after / before`, a
    relative improvement, which hides how far from correct the result still is
    and is unstable when `before` is small. A plain root mean square distance
    fixes that and introduces a worse problem on this corpus: the distance
    carries the data's units, and the corpus spans a bitcoin price near 26000
    beside a rate near 3.4, so a handful of high magnitude windows dominate the
    column. Measured on the mixed corpus, plain RMSD put SCREEN at 2109 against
    no action at 1382, which reads as SCREEN being worse and is really SCREEN
    having touched a few large magnitude windows.

    Each window's distance is therefore divided by that window's own robust
    scale before averaging, using the same blockwise measure the operators and
    SIR already use. This is the same move the valuation family's within dataset
    rank makes and for the same reason: on a corpus of mixed provenance a
    quantity carrying units cannot be aggregated directly.

    The reference is the pre injection series that `corpus.build_corpus` stored
    on the window, not the corpus's current value, which is the corrupted one.

    **Protected mis edits is a rate.** A count cannot be read across corpus
    sizes, and this paper reports on two. The denominator is the four protected
    layers, `clean`, `hard`, `rare_valid` and `changepoint`. The synthetic probe
    layer is excluded by the 4.1.2 ruling and is reported on its own.
    """
    from audit import _nmse
    from introact_ts.actions import robust_scale
    byid = {w.window_id: w for w in windows}
    dmg, before, after = [], [], []
    nrmsd = []
    mis = 0
    n_protected = sum(1 for w in windows if w.stratum in PROTECTED)
    probe_mis = 0
    n_probe = sum(1 for w in windows if w.stratum == PROBE_LAYER)
    committed, harmful = 0, 0
    for t in traces:
        w = byid[t.window_id]
        # The strict reading. `t.modified` is permissive, it counts an admitted
        # operator that left the series unchanged, and the two disagreed by 71
        # against 62 on one run. Every reported edit count uses the strict one.
        # It also matters here for a second reason: the reference arms carry no
        # action records at all, so the permissive property returns False for
        # them and the whole column would read zero while repair gain read one.
        edited = t.content_modified(w.series)
        if w.stratum in PROTECTED and edited:
            mis += 1
        if w.stratum == PROBE_LAYER and edited:
            probe_mis += 1
        if w.clean_series is None:
            continue
        ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))
        a = _nmse(t.final_series, w.clean_series[t.crop_offset:], ref_var)
        b = _nmse(w.series, w.clean_series, ref_var)
        # Discarding data is damage. The distance comparison above cannot see a
        # crop, because cropping leaves the surviving span point wise correct,
        # so a protected window can lose 40 percent of itself at zero measured
        # damage. Same blind spot, same fix, as `structure._discard_distortion`
        # and `conformal.damage_loss`. See docs/version_ledger.md for what this
        # does to the v1 numbers.
        lo = int(t.crop_offset)
        hi = lo + len(np.asarray(t.final_series))
        disc = _discard_distortion(np.asarray(w.series, dtype=np.float64),
                                   {"lo": lo, "hi": hi})
        if edited:
            committed += 1
            harmful += int(a > b + 1e-9 or disc > 1e-9)
        if w.stratum in PROTECTED:
            dmg.append(a)
        elif w.stratum == "contaminated":
            before.append(b)
            after.append(a)
            # Repair accuracy, one normalised distance per window then averaged
            # over windows. Normalising per window and averaging over windows,
            # rather than pooling squared error over points, is what keeps a
            # long window from outweighing a short one as well.
            fin = np.asarray(t.final_series, dtype=np.float64)
            ref = np.asarray(w.clean_series, dtype=np.float64)[t.crop_offset:]
            n = min(len(fin), len(ref))
            if n:
                dd = fin[:n] - ref[:n]
                dd = dd[np.isfinite(dd)]
                if dd.size:
                    # Scale from the window's own input. A constant window has no
                    # scale, hence the floor.
                    sc = max(float(robust_scale(
                        np.asarray(w.series, dtype=np.float64))), 1e-9)
                    nrmsd.append(float(np.sqrt(np.mean(dd ** 2))) / sc)
    bb = float(np.mean(before)) if before else 0.0
    aa = float(np.mean(after)) if after else 0.0
    return {
        "protected_mis_edits": int(mis),
        "n_protected_windows": int(n_protected),
        "protected_mis_edit_rate": (mis / n_protected) if n_protected else None,
        "probe_layer_mis_edits": int(probe_mis),
        "n_probe_windows": int(n_probe),
        "damage_rate": (harmful / committed) if committed else 0.0,
        "repair_nrmsd": float(np.mean(nrmsd)) if nrmsd else None,
        "repair_nrmsd_median": float(np.median(nrmsd)) if nrmsd else None,
        "n_injected_scored": int(len(after)),
        # Kept beside the RMSD for one release so the two口径 can be compared,
        # and because the earlier tables report it.
        "repair_gain": (1.0 - aa / bb) if bb > 1e-9 else 0.0,
        "committed_edits": int(committed),
        "mean_protected_damage": float(np.mean(dmg)) if dmg else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="xl", choices=list(SCALES))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--tau", type=float, default=0.02)
    ap.add_argument("--fractions", type=float, nargs="+", default=[0.5, 0.75])
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=32)
    #: Selection basis. The default is the within dataset rank, fixed after the
    #: three regime comparison recorded in section 4.1.3. The flag exists so the
    #: raw score comparison can be reproduced, not so the basis can be chosen
    #: after seeing a result.
    ap.add_argument("--raw-score-selection", dest="rank_within_dataset",
                    action="store_false", default=True)
    #: Per window traces, on by default. Without them a metric change costs a
    #: full rerun of the probe, which has already happened twice.
    ap.add_argument("--no-dump-traces", dest="dump_traces",
                    action="store_false", default=True)
    #: Penalty weight for the soft contrast row. None takes SOFT_MU, which is
    #: the point of the sweep the table carries. The flag exists so the sweep
    #: can drive this script rather than duplicating the arm.
    ap.add_argument("--soft-mu", dest="soft_mu", type=float, default=None)
    ap.add_argument("--l2c-episodes", dest="l2c_episodes", type=int, default=3)
    ap.add_argument("--probe-cost", dest="probe_cost", type=float, default=2.0,
                    help="probes an abstained window would have consumed")
    ap.add_argument("--rows", nargs="+", default=[r[0] for r in ROWS])
    ap.add_argument("--valuation-scores", dest="val_scores",
                    default=str(ROOT / "results" / "valuation_scores_xl.json"))
    ap.add_argument("--ltsv-scores", dest="ltsv_scores",
                    default=str(ROOT / "results" / "ltsv_scores_xl.json"))
    ap.add_argument("--expect-code-hash", dest="expect_code_hash", default=None)
    ap.add_argument("--expect-config-hash", dest="expect_config_hash", default=None)
    ap.add_argument("--require-pool", dest="require_pool", type=int, default=None)
    ap.add_argument("--allow-dirty-tree", dest="require_clean_tree",
                    action="store_false", default=True)
    ap.add_argument("--out", default=str(ROOT / "results" / "main_table.json"))
    args = ap.parse_args()

    # A relative --out is resolved against the repository root, otherwise the
    # monitor's writable check cannot express it and relative_to raises. Same
    # fix the learning loop already carries.
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    args.out = str(out_path)

    spec = SCALES[args.scale]
    spec.seed = args.seed
    windows = build_corpus(spec, source=args.source)
    models = make_pool(PRESETS[args.preset]["curation"], device=args.device)

    mon = Monitor(
        "run_main", expects=[str(out_path.relative_to(ROOT)).replace("\\", "/")],
        config={"scale": args.scale, "seed": args.seed, "source": args.source,
                "tau": args.tau, "preset": args.preset,
                "fractions": ",".join(f"{f:g}" for f in args.fractions)},
        expect_config_hash=args.expect_config_hash,
        require_pool=args.require_pool,
        require_clean_tree=args.require_clean_tree,
        expect_code_hash=args.expect_code_hash,
    )
    trace_path = ROOT / "results" / "xl" / f"seed_{args.seed}_window_traces.jsonl"
    if args.dump_traces and trace_path.exists():
        # A rerun starts a fresh file rather than appending to a stale one,
        # otherwise a resumed run would carry both versions.
        trace_path.unlink()

    mon.start(pool_size=len(models))
    print(f"{len(windows)} windows, source {args.source}, tau {args.tau}",
          flush=True)

    table = {}
    agent = IntroActAgent(models, AgentConfig(verification=VerifyConfig(tau=args.tau),
                                              n_jobs=args.n_jobs))
    t0 = time.time()
    states = agent.perceive(windows)
    perceive_seconds = time.time() - t0
    print(f"perception {perceive_seconds:.0f}s", flush=True)

    val_scores = {}
    for path, keys in ((args.val_scores, ("timeinf", "data_oob", "data_shapley")),
                       (args.ltsv_scores, ("ltsv",))):
        p = Path(path)
        if not p.exists():
            print(f"  scores absent, {p.name}", flush=True)
            continue
        blob = json.loads(p.read_text(encoding="utf-8"))
        if "methods" in blob:
            for k in keys:
                if k in blob["methods"]:
                    val_scores[k] = {int(i): v for i, v
                                     in blob["methods"][k]["window_scores"].items()}
        elif "window_scores" in blob:
            val_scores[keys[0]] = {int(i): v for i, v
                                   in blob["window_scores"].items()}

    for name, family, how in ROWS:
        if name not in args.rows:
            continue
        t0 = time.time()
        if how == "unavailable":
            table[name] = {c: "not_applicable" for c in COLUMNS}
            table[name]["reason"] = NOT_APPLICABLE[name]
            print(f"  {name:14s} not applicable", flush=True)
            continue

        if how == "scores":
            key = SCORE_KEY.get(name, name)
            if key not in val_scores:
                table[name] = {c: "not_applicable" for c in COLUMNS}
                table[name]["reason"] = "scores not yet computed on this corpus"
                print(f"  {name:14s} deferred, no scores", flush=True)
                continue
            raw = val_scores[key]
            ranked = (rank_within_dataset(windows, raw)
                      if args.rank_within_dataset else raw)
            row = {"selection": {},
                   "selection_basis": ("within dataset rank"
                                       if args.rank_within_dataset
                                       else "raw score")}
            for frac in args.fractions:
                kept, unscored = selection_corpus(windows, ranked, frac)
                kept_ids = {w.window_id for w in kept}
                # A selection arm commits no edit, so its damage and mis edit
                # counts are zero by construction. What it can lose is coverage,
                # which is what the retention numbers record.
                # Two denominators, and they answer different questions, so
                # both are reported and neither is mixed into the other. An
                # earlier version divided a corpus level numerator by a pool
                # level baseline and produced ratios that meant nothing.
                #
                # corpus level   how much of a stratum survives into the prepared
                #                corpus. Unscored windows count as dropped, per
                #                the protocol, so the baseline is the nominal
                #                fraction. This is what a downstream consumer
                #                sees.
                # pool level     within the windows this method could score, is
                #                the stratum ranked lower than average. The
                #                baseline is the effective rate inside that
                #                pool. This is what the protocol's prediction is
                #                about, since it is a claim about the scorer's
                #                judgement rather than about coverage.
                scored_ids = set(ranked)
                layers = PROTECTED + (PROBE_LAYER, "contaminated")
                retained = {s: sum(1 for w in windows
                                   if w.stratum == s and w.window_id in kept_ids)
                            for s in layers}
                total_all = {s: sum(1 for w in windows if w.stratum == s)
                             for s in layers}
                total_scored = {s: sum(1 for w in windows if w.stratum == s
                                       and int(w.window_id) in scored_ids)
                                for s in layers}
                n_scored = len(scored_ids)
                actual = len(kept) / max(n_scored, 1)
                row["selection"][f"{frac:g}"] = {
                    "kept": len(kept), "unscored": unscored,
                    "n_scored": n_scored,
                    "nominal_rate": frac,
                    "actual_rate": actual,
                    "retention_corpus": {
                        s: retained[s] / total_all[s] if total_all[s] else None
                        for s in layers},
                    "retention_corpus_ratio": {
                        s: (retained[s] / total_all[s] / frac)
                        if total_all[s] and frac else None for s in layers},
                    "retention_pool": {
                        s: retained[s] / total_scored[s] if total_scored[s] else None
                        for s in layers},
                    "retention_pool_ratio": {
                        s: (retained[s] / total_scored[s] / actual)
                        if total_scored[s] and actual else None for s in layers},
                }
            # The rate is written as an explicit zero rather than left absent.
            # A selection arm commits no edit at all, so zero is the measured
            # value and not a missing one, and an absent key was being rendered
            # as `n/a` in the aggregate, which reads as untested. The table note
            # states the distinction: zero here means the arm cannot mis edit by
            # construction, not that it was careful.
            n_protected = sum(1 for w in windows if w.stratum in PROTECTED)
            row.update({"protected_mis_edits": 0,
                        "n_protected_windows": int(n_protected),
                        "protected_mis_edit_rate": 0.0,
                        "probe_layer_mis_edits": 0,
                        "mis_edit_rate_note": (
                            "zero by construction, this family selects windows "
                            "and commits no edit"),
                        "damage_rate": 0.0,
                        "repair_gain": 0.0, "committed_edits": 0,
                        "probes_saved": "not_applicable",
                        "missed_windows": "not_applicable",
                        "downstream_error": "deferred",
                        "compute_seconds": "see valuation score run"})
            row["reason_probes"] = ("this family issues no probes, so the budget "
                                    "columns have no definition for it")
            table[name] = row
            print(f"  {name:14s} selection done", flush=True)
            continue

        if how == "none":
            from baselines import run_no_action
            traces = run_no_action(windows, states, models)
        elif how == "oracle":
            traces = oracle_traces(windows, states)
        elif how == "classic":
            traces = repair_traces(windows, states, name.split("_", 1)[1])
        elif how == "l2c":
            from learn2clean import run as run_l2c
            from introact_ts.profiling import extract_statistical_profile
            profiles = [extract_statistical_profile(
                np.nan_to_num(np.asarray(w.series, dtype=np.float64)))
                for w in windows]
            traces, l2c_history, _ = run_l2c(windows, profiles,
                                             episodes=args.l2c_episodes,
                                             seed=args.seed)
        elif how == "agent":
            traces = agent_traces(models, windows, states, name, args.tau,
                                  args.n_jobs, agent)
        elif how == "soft":
            # The soft arm now runs here rather than being deferred.
            # `VerifyConfig.soft_mu` expresses the weighted sum, so this arm
            # shares the corpus, the proposals, the sandbox and the probe with
            # every other contrast and differs only in the decision rule.
            # `experiments/run_soft_sweep.py` sweeps mu; the table carries the
            # point named in SOFT_MU and the table note says which and why.
            traces = agent_traces(models, windows, states, name, args.tau,
                                  args.n_jobs, agent, soft_mu=args.soft_mu)
        else:
            raise ValueError(how)
        row = score_rows(traces, windows)
        if args.dump_traces:
            n_dumped = dump_window_traces(traces, windows, trace_path, name)
            row["traces_written"] = n_dumped
        probes = sum(t.probe_calls for t in traces)
        row["compute_seconds"] = time.time() - t0
        row["probe_calls"] = probes
        if how in ("none", "oracle", "classic"):
            row["probes_saved"] = "not_applicable"
            row["missed_windows"] = "not_applicable"
            row["reason_probes"] = ("this arm issues no probe, so there is no "
                                    "budget to save")
        else:
            skipped = [t for t in traces if t.final_state == "ABSTAIN"]
            byid = {w.window_id: w for w in windows}
            row["probes_saved"] = int(len(skipped) * args.probe_cost)
            row["missed_windows"] = int(sum(
                1 for t in skipped
                if byid[t.window_id].stratum == "contaminated"))
        row["downstream_error"] = "deferred"
        if how == "l2c":
            # Harmful edits per episode, which accumulate because this arm has
            # no sandbox. This is the quantity the comparison exists for.
            row["learning_history"] = l2c_history
        table[name] = row
        rr = row.get("repair_nrmsd")
        rrs = f"{rr:.4f}" if rr is not None else "n/a"
        print(f"  {name:14s} edits {row['committed_edits']:5d}  "
              f"mis rate {row['protected_mis_edit_rate']:.4f}  "
              f"damage {row['damage_rate']:.4f}  "
              f"nrmsd {rrs:>8s}  {row['compute_seconds']:6.0f}s", flush=True)

    # A column that is entirely zero, or entirely one value, is usually a wiring
    # fault rather than a finding. The selection arm returning zeros on a corpus
    # mismatch was one, and the edit count reading zero under the permissive
    # `modified` property was another, both caught only by looking. This warns
    # at the end of every run so the next one does not need luck.
    warnings = []
    for col in ("committed_edits", "protected_mis_edits", "damage_rate",
                "repair_gain"):
        vals = [r.get(col) for r in table.values()
                if isinstance(r.get(col), (int, float))]
        if len(vals) >= 3 and len(set(vals)) == 1:
            warnings.append(f"column {col} is {vals[0]} for all {len(vals)} "
                            f"numeric rows, check the wiring before reporting")
    for w in warnings:
        print(f"  WARNING {w}", flush=True)

    payload = {
        "warnings": warnings,
        "scale": args.scale, "seed": args.seed, "source": args.source,
        "n_windows": len(windows), "tau": args.tau,
        "perceive_seconds": perceive_seconds,
        "protected": list(PROTECTED), "probe_layer": PROBE_LAYER,
        "columns": list(COLUMNS), "rows": table,
        "not_applicable_reasons": NOT_APPLICABLE,
    }
    Path(args.out).write_text(json.dumps(payload, indent=1, default=float),
                              encoding="utf-8")
    mon.finish(git_add=False)
    print("___MAIN_TABLE_DONE___", flush=True)


if __name__ == "__main__":
    main()
