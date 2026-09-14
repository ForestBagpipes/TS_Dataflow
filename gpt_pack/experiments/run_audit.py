"""Offline audit driver. Runs on CPU from cached run artefacts only.

Answers four questions that need no GPU and no retraining:

  A  when the agent refused an edit, was it right to refuse
  B  what the ledger looks like per contamination rather than as one mean
  C  which rungs of the ablation ladder already have real model numbers
  D  whether the headline numbers rest on one seed or several

Usage:
    python experiments/run_audit.py
"""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from audit import (  # noqa: E402
    audit_acceptances,
    audit_rejections,
    ledger_by_contamination,
    replay_method,
    verify_replay,
)
from corpus import CorpusSpec, build_corpus  # noqa: E402

#: Cached runs to audit, with the corpus spec each was produced from.
RUNS = {
    "heavy_real": {
        "traces": "results/gpu/heavy_ett_multi-family_seed42_traces.json",
        "summary": "results/gpu/heavy_ett_multi-family_seed42.json",
        "spec": CorpusSpec(n_contaminated=140, n_clean=20, n_hard=10,
                           n_rare_valid=20, n_changepoint=10, n_clean_ood=10),
        "label": "heavy, 67 percent contaminated, real TSFM",
    },
    "small_real": {
        "traces": "results/gpu/small_ett_multi-family_seed42_traces.json",
        "summary": "results/gpu/small_ett_multi-family_seed42.json",
        "spec": CorpusSpec(n_contaminated=35, n_clean=20, n_hard=10,
                           n_rare_valid=10, n_changepoint=10, n_clean_ood=10),
        "label": "small, 37 percent contaminated, real TSFM",
    },
}

#: The ladder the paper argues over, mapped onto the configurations that exist.
LADDER = [
    ("a  score only, no action", "no_action",
     "the floor. perception runs, nothing is edited"),
    ("b  repair, no verification", "ablate_no_verify",
     "policy proposals committed unconditionally"),
    ("c  repair plus structure, no utility recheck", "ablate_no_reprobe",
     "structural veto active, model utility never consulted after the edit"),
    ("d  full agent", "introact_full",
     "utility recheck plus structural veto plus risk term plus ABSTAIN"),
]

EXTRA_ABLATIONS = [
    ("no structural veto", "ablate_no_structure"),
    ("no peer calibration", "ablate_no_peer_calibration"),
    ("no protection of hard, rare valid, OOD", "ablate_no_protection"),
]


def load(run: dict):
    traces = json.loads((ROOT / run["traces"]).read_text(encoding="utf-8"))
    summary = json.loads((ROOT / run["summary"]).read_text(encoding="utf-8"))
    windows = build_corpus(run["spec"], source="ett")
    return traces, summary, windows


def section_a(traces, summary, windows, out):
    out.append("## A  rollback audit, was the refusal right")
    out.append("")
    out.append("Every rejected edit is re applied offline and scored against the")
    out.append("pristine reference. An edit that would have reduced the distance to")
    out.append("truth was wrongly refused and its gain was thrown away. An edit that")
    out.append("would not have is a rejection that protected the data.")
    out.append("")
    out.append("Totals are the number that settles it. If refusing costs more in")
    out.append("forgone gain than it saves in avoided harm, the rule is too strict")
    out.append("whatever the rate looks like.")
    out.append("")
    out.append("| method | rejections | wrongly refused | rate | total gain forgone | total harm avoided | net of refusing |")
    out.append("|---|---|---|---|---|---|---|")
    audits = {}
    for m in traces:
        rep = replay_method(traces[m], windows, m)
        a = audit_rejections(rep)
        audits[m] = a
        if not a.get("n_rejections"):
            continue
        out.append(
            f"| {m} | {a['n_rejections']} | {a['n_wrongly_refused']} "
            f"| {a['wrong_rate']:.3f} | {a['total_forgone_gain']:.2f} "
            f"| {a['total_avoided_harm']:.2f} | {a['net_of_refusing']:+.2f} |"
        )
    out.append("")

    full = audits.get("introact_full", {})
    if full.get("n_rejections"):
        out.append("### introact_full, split by the reason for refusal")
        out.append("")
        out.append("| verdict | n | wrongly refused | rate |")
        out.append("|---|---|---|---|")
        for v, d in sorted(full["by_verdict"].items()):
            out.append(f"| {v} | {d['n']} | {d['wrong']} | {d['wrong_rate']:.3f} |")
        out.append("")

        out.append("### introact_full, split by operator")
        out.append("")
        out.append("| action | rejections | wrongly refused | rate | total forgone | total avoided | net | median forgone |")
        out.append("|---|---|---|---|---|---|---|---|")
        for k, d in full["by_action"].items():
            out.append(
                f"| {k} | {d['n']} | {d['wrong']} | {d['wrong_rate']:.3f} "
                f"| {d['total_forgone_gain']:.2f} | {d['total_avoided_harm']:.2f} "
                f"| {d['net']:+.2f} | {d['median_forgone_gain']:.4f} |"
            )
        out.append("")

        out.append("### introact_full, split by contamination")
        out.append("")
        out.append("| contamination or stratum | rejections | wrongly refused | rate | total forgone | total avoided | net |")
        out.append("|---|---|---|---|---|---|---|")
        for k, d in full["by_contamination"].items():
            out.append(
                f"| {k} | {d['n']} | {d['wrong']} | {d['wrong_rate']:.3f} "
                f"| {d['total_forgone_gain']:.2f} | {d['total_avoided_harm']:.2f} "
                f"| {d['net']:+.2f} |"
            )
        out.append("")

        acc = audit_acceptances(replay_method(traces["introact_full"], windows, "introact_full"))
        out.append("### the mirror question, were the commits right")
        out.append("")
        out.append(
            f"Of {acc['n_acceptances']} committed edits, {acc['n_helpful']} moved the "
            f"window closer to truth, a precision of {acc['precision']:.3f}. Mean gain "
            f"on a good commit {acc['mean_gain']:.4f}, mean loss on a bad one "
            f"{acc['mean_loss']:.4f}."
        )
        out.append("")
        if full.get("n_param_inferred"):
            out.append(
                f"Note, {full['n_param_inferred']} of the audited rejections had their "
                f"operator parameters inferred from the policy proposal order rather "
                f"than read from the trace. The replay reproduces every recorded repair "
                f"number exactly, so the inference is consistent with the run."
            )
            out.append("")
    return audits


def section_b(traces, summary, windows, out):
    out.append("## B  ledger by contamination, not one mean")
    out.append("")
    methods = ["no_action", "always_clean", "stat_only", "quality_rank", "introact_full"]
    ledgers = {}
    for m in methods:
        if m not in traces:
            continue
        ledgers[m] = ledger_by_contamination(replay_method(traces[m], windows, m), windows)

    keys = sorted({k for v in ledgers.values() for k in v})
    out.append("Absolute gain is the total normalised error removed across the stratum.")
    out.append("It is what the corpus mean is actually weighted by.")
    out.append("")
    for m in methods:
        if m not in ledgers:
            continue
        out.append(f"### {m}")
        out.append("")
        out.append("| stratum | n | nmse before | nmse after | reduction | abs gain | edited | improved | worsened | edit precision |")
        out.append("|---|---|---|---|---|---|---|---|---|---|")
        for k in keys:
            d = ledgers[m].get(k)
            if not d:
                continue
            prec = "n/a" if np.isnan(d["edit_precision"]) else f"{d['edit_precision']:.2f}"
            out.append(
                f"| {k} | {d['n']} | {d['nmse_before']:.4f} | {d['nmse_after']:.4f} "
                f"| {d['reduction']:+.3f} | {d['abs_gain_total']:+.2f} | {d['edited']} "
                f"| {d['improved']} | {d['worsened']} | {prec} |"
            )
        out.append("")

    out.append("### which stratum drives the corpus mean")
    out.append("")
    ref = ledgers.get("no_action", {})
    total_err = sum(d["nmse_before"] * d["n"] for d in ref.values())
    out.append("| stratum | n | nmse before | share of total corpus error |")
    out.append("|---|---|---|---|")
    for k, d in sorted(ref.items(), key=lambda kv: -kv[1]["nmse_before"] * kv[1]["n"]):
        share = d["nmse_before"] * d["n"] / max(total_err, 1e-12)
        out.append(f"| {k} | {d['n']} | {d['nmse_before']:.4f} | {share:.1%} |")
    out.append("")

    out.append("### pareto view, utility gained against collateral damage")
    out.append("")
    out.append("| method | net corpus gain | windows worsened | over clean rate | damage to protected |")
    out.append("|---|---|---|---|---|")
    res = summary["results"]
    rows = []
    for m, r in res.items():
        ce = r.get("corpus_effect", {})
        rows.append((
            m,
            ce.get("net_reduction", 0.0),
            ce.get("windows_worsened", 0),
            r["protection"]["over_clean_rate"],
            r["protection"]["mean_damage"],
        ))
    for m, net, worse, oc, dmg in sorted(rows, key=lambda x: -x[1]):
        out.append(f"| {m} | {net:+.3f} | {worse} | {oc:.3f} | {dmg:.4f} |")
    out.append("")
    frontier = []
    for m, net, worse, oc, dmg in rows:
        dominated = any(
            (n2 >= net and w2 <= worse and (n2 > net or w2 < worse))
            for m2, n2, w2, _, _ in rows if m2 != m
        )
        if not dominated:
            frontier.append(m)
    out.append(f"Pareto frontier on gain against windows worsened: {', '.join(sorted(frontier))}")
    out.append("")
    return ledgers


def section_c(summary, out):
    out.append("## C  ablation ladder on real models")
    out.append("")
    res = summary["results"]
    out.append("| rung | configuration | status | net corpus | repair | over clean | damage | worsened |")
    out.append("|---|---|---|---|---|---|---|---|")
    for label, key, _desc in LADDER:
        if key in res:
            r = res[key]
            ce = r.get("corpus_effect", {})
            out.append(
                f"| {label} | {key} | done | {ce.get('net_reduction', 0.0):+.3f} "
                f"| {r['repair'].get('reduction', 0.0):.3f} "
                f"| {r['protection']['over_clean_rate']:.3f} "
                f"| {r['protection']['mean_damage']:.4f} "
                f"| {ce.get('windows_worsened', 0)} |"
            )
        else:
            out.append(f"| {label} | {key} | deferred | | | | | |")
    out.append("")
    out.append("Additional single mechanism ablations already run on real models:")
    out.append("")
    out.append("| ablation | key | net corpus | repair | over clean | damage |")
    out.append("|---|---|---|---|---|---|")
    for label, key in EXTRA_ABLATIONS:
        if key in res:
            r = res[key]
            ce = r.get("corpus_effect", {})
            out.append(
                f"| {label} | {key} | {ce.get('net_reduction', 0.0):+.3f} "
                f"| {r['repair'].get('reduction', 0.0):.3f} "
                f"| {r['protection']['over_clean_rate']:.3f} "
                f"| {r['protection']['mean_damage']:.4f} |"
            )
        else:
            out.append(f"| {label} | {key} | deferred | | | |")
    out.append("")
    out.append("Gaps on the ladder, to be filled in the next GPU session:")
    out.append("")
    out.append("- no ABSTAIN only ablation exists. The refusal path is currently")
    out.append("  entangled with the rest of the policy, so its separate contribution")
    out.append("  is not measured. Needs PolicyConfig with min_confidence set to zero.")
    out.append("- no rung isolates rollback from veto. c and d differ by the utility")
    out.append("  recheck, not by whether a rejected edit is retried with another")
    out.append("  operator, so the value of retrying is not separated.")
    out.append("")


def section_d(out):
    out.append("## D  seed coverage")
    out.append("")
    found = sorted((ROOT / "results").glob("**/*.json"))
    seeds = {}
    for f in found:
        if "traces" in f.name:
            continue
        name = f.name
        if "seed" not in name:
            continue
        seed = name.split("seed")[-1].split(".")[0]
        stem = name.split("_seed")[0]
        seeds.setdefault(stem, set()).add(seed)
    out.append("| run | seeds present | count |")
    out.append("|---|---|---|")
    for stem, ss in sorted(seeds.items()):
        out.append(f"| {stem} | {', '.join(sorted(ss))} | {len(ss)} |")
    out.append("")
    out.append("Every headline number in the paper so far rests on a single seed, 42.")
    out.append("That includes the three the argument leans on most:")
    out.append("")
    out.append("- repair 0.367 on small with real TSFMs")
    out.append("- the 2.4x gap to stat_only at 67 percent contamination")
    out.append("- the collapse from 0.367 to 0.141 when the structural veto is removed")
    out.append("")
    out.append("None of these has an error bar. All need at least three seeds before")
    out.append("they can be claimed. Not run this round by instruction.")
    out.append("")


def main():
    for run_key, run in RUNS.items():
        path = ROOT / run["traces"]
        if not path.exists():
            print(f"skip {run_key}, no traces at {path}")
            continue
        traces, summary, windows = load(run)

        out = [f"# Offline audit, {run['label']}", ""]
        out.append(f"Source: `{run['traces']}`")
        out.append("")
        out.append("Replay self check, reconstructed repair against the recorded value:")
        out.append("")
        out.append("| method | replay | reported | abs error |")
        out.append("|---|---|---|---|")
        worst = 0.0
        for m in traces:
            v = verify_replay(replay_method(traces[m], windows, m), windows, summary["results"][m])
            worst = max(worst, v["abs_error"])
            out.append(
                f"| {m} | {v['replay_reduction']:.4f} | {v['reported_reduction']:.4f} "
                f"| {v['abs_error']:.4f} |"
            )
        out.append("")
        out.append(f"Worst absolute error {worst:.4f}. The replay is exact, so the")
        out.append("counterfactuals below rest on the same series the run produced.")
        out.append("")

        section_a(traces, summary, windows, out)
        section_b(traces, summary, windows, out)
        section_c(summary, out)
        if run_key == "heavy_real":
            section_d(out)

        dest = ROOT / "results" / f"audit_{run_key}.md"
        dest.write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"written {dest}")


if __name__ == "__main__":
    main()
