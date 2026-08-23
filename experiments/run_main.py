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
from introact_ts.verify import VerifyConfig  # noqa: E402

#: Strata whose windows must not be edited. `clean_ood` is the synthetic probe
#: layer of the 4.1.2 ruling and is scored separately, never summed in here.
PROTECTED = ("clean", "hard", "rare_valid", "changepoint")
PROBE_LAYER = "clean_ood"

#: Every row of the main table, in the order it is printed. The third field says
#: which family the row belongs to, which decides how its prepared corpus is
#: produced.
ROWS = [
    ("no_action", "reference", "none"),
    ("screen", "repair", "classic"),
    ("imr", "repair", "classic"),
    ("mtcsc", "repair", "classic"),
    ("timeinf", "valuation", "scores"),
    ("data_oob", "valuation", "scores"),
    ("data_shapley", "valuation", "scores"),
    ("ltsv", "valuation", "scores"),
    ("tsrating", "valuation", "unavailable"),
    ("soft_penalty", "contrast", "agent"),
    ("utility_only", "contrast", "agent"),
    ("spec_veto", "contrast", "agent"),
    ("no_shield", "contrast", "agent"),
    ("introact", "ours", "agent"),
    ("oracle", "reference", "oracle"),
]

#: Reasons a cell is not applicable, keyed by row. Printed in the table note.
NOT_APPLICABLE = {
    "tsrating": (
        "the substituted judgment backend is not stable enough to distil a "
        "rater from, flip rate 0.508 with reasoning off and an unscorable rate "
        "of 0.333 with reasoning on, see docs/baseline_year_gap.md"),
}

#: Columns every row must fill, so a missing one is an error rather than a gap.
COLUMNS = ("downstream_error", "protected_mis_edits", "damage_rate",
           "repair_gain", "compute_seconds", "probes_saved", "missed_windows")


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
    if len(have) < 0.05 * len(windows):
        raise SystemExit(
            f"only {len(have)} of {len(windows)} windows carry a score, "
            f"the score file was computed on a different corpus")
    have.sort(key=lambda ws: -ws[1])
    keep_n = int(round(fraction * len(windows)))
    kept = [w for w, _ in have[:keep_n]]
    return kept, len(unscored)


def score_rows(traces, windows):
    """The corpus level columns, from one arm's traces."""
    from audit import _nmse
    byid = {w.window_id: w for w in windows}
    dmg, before, after = [], [], []
    mis = 0
    committed, harmful = 0, 0
    for t in traces:
        w = byid[t.window_id]
        if w.stratum in PROTECTED and t.modified:
            mis += 1
        if w.clean_series is None:
            continue
        ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))
        a = _nmse(t.final_series, w.clean_series[t.crop_offset:], ref_var)
        b = _nmse(w.series, w.clean_series, ref_var)
        if t.modified:
            committed += 1
            harmful += int(a > b + 1e-9)
        if w.stratum in PROTECTED:
            dmg.append(a)
        elif w.stratum == "contaminated":
            before.append(b)
            after.append(a)
    bb = float(np.mean(before)) if before else 0.0
    aa = float(np.mean(after)) if after else 0.0
    return {
        "protected_mis_edits": int(mis),
        "damage_rate": (harmful / committed) if committed else 0.0,
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
            if name not in val_scores:
                table[name] = {c: "not_applicable" for c in COLUMNS}
                table[name]["reason"] = "scores not yet computed on this corpus"
                print(f"  {name:14s} deferred, no scores", flush=True)
                continue
            row = {"selection": {}}
            for frac in args.fractions:
                kept, unscored = selection_corpus(windows, val_scores[name], frac)
                kept_ids = {w.window_id for w in kept}
                # A selection arm commits no edit, so its damage and mis edit
                # counts are zero by construction. What it can lose is coverage,
                # which is what the retention numbers record.
                retained = {s: sum(1 for w in windows
                                   if w.stratum == s and w.window_id in kept_ids)
                            for s in PROTECTED + (PROBE_LAYER, "contaminated")}
                total = {s: sum(1 for w in windows if w.stratum == s)
                         for s in retained}
                row["selection"][f"{frac:g}"] = {
                    "kept": len(kept), "unscored": unscored,
                    "retention": {s: retained[s] / total[s] if total[s] else None
                                  for s in retained},
                }
            row.update({"protected_mis_edits": 0, "damage_rate": 0.0,
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

        # Every remaining row runs the agent loop under a different setting.
        table[name] = {c: "deferred" for c in COLUMNS}
        table[name]["reason"] = "arm not yet wired, see run_main.py"
        print(f"  {name:14s} deferred", flush=True)

    payload = {
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
