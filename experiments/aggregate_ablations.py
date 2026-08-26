"""Aggregate the ablation ladder over seeds, and test the two claims it makes.

Two questions, and they need different treatment.

**How far each rung falls from the full method.** The shield rungs are far
enough that a mean and a spread over three seeds says it. Reported as the
absolute value and the ratio to the reference row.

**Whether the policy rungs differ from the full method at all.** They do not
differ enough for three seed means to settle it, and three points cannot
support an ordering anyway. So this is tested where the evidence is, window by
window: the rungs ran on the same corpus with the same seed, so a window in one
has a counterpart in the other, and the question becomes how many windows ended
somewhere different. That count is exact and needs no test, which is the point
of using it.

The mis edit comparison is paired and binary, so it takes an exact McNemar over
the discordant windows.

Usage:
    python experiments/aggregate_ablations.py --results results/xl
"""

import argparse
import json
from collections import Counter
from math import comb
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent

#: Ladder order for printing, and the matrix id each maps to.
ORDER = ("a_no_shield", "b_no_structural", "g_no_conformal", "c_no_policy",
         "d_no_injection", "e_raw_reward", "f_full")
REFERENCE = "f_full"
HEADLINE = ("committed_edits", "protected_mis_edit_rate", "damage_rate",
            "repair_nrmsd")
PROTECTED = ("clean", "hard", "rare_valid", "changepoint")


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / (2 ** n))


def load(results_dir, levels, seeds):
    out = {}
    for lv in levels:
        rows = []
        for s in seeds:
            p = Path(results_dir) / f"ablation_{lv}_seed{s}.json"
            if p.exists():
                rows.append(json.loads(p.read_text(encoding="utf-8")))
        if rows:
            out[lv] = rows
    return out


def agg(rows, col):
    vals = [r[col] for r in rows if isinstance(r.get(col), (int, float))]
    if not vals:
        return None
    a = np.asarray(vals, dtype=np.float64)
    return {"mean": float(a.mean()),
            "std": float(a.std(ddof=1)) if len(a) > 1 else 0.0,
            "values": [float(x) for x in a]}


def trace_index(path, arm):
    out = {}
    if not Path(path).exists():
        return out
    for line in Path(path).open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("arm") == arm:
            out[int(r["window_id"])] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "results" / "xl"))
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--out", default=str(ROOT / "results" / "ablation_agg.json"))
    args = ap.parse_args()

    seeds = [int(s) for s in args.seeds.split(",") if s]
    data = load(args.results, ORDER, seeds)
    missing = [lv for lv in ORDER if lv not in data]
    if missing:
        print(f"levels with no result file: {missing}")
    for lv, rows in data.items():
        if len(rows) != len(seeds):
            print(f"  {lv}: only {len(rows)} of {len(seeds)} seeds present")

    table = {lv: {c: agg(rows, c) for c in HEADLINE}
             for lv, rows in data.items()}
    ref = table.get(REFERENCE)

    print()
    print(f"{'rung':16s}{'id':>5s}{'edits':>14s}{'mis edit rate':>20s}"
          f"{'damage rate':>20s}{'nRMSD':>20s}")
    for lv in ORDER:
        if lv not in table:
            continue
        mid = data[lv][0].get("matrix_id", "")
        cells = ""
        for c in HEADLINE:
            v = table[lv][c]
            if v is None:
                cells += f"{'n/a':>20s}"
                continue
            fmt = ("{:.0f}+-{:.0f}" if c == "committed_edits"
                   else "{:.4f}+-{:.4f}")
            w = 14 if c == "committed_edits" else 20
            cells += f"{fmt.format(v['mean'], v['std']):>{w}s}"
        print(f"{lv:16s}{mid:>5s}{cells}")

    # Degradation against the reference row.
    if ref:
        print()
        print("ratio to the full method, damage rate and mis edit rate")
        print(f"{'rung':16s}{'damage x':>12s}{'mis edit x':>13s}")
        for lv in ORDER:
            if lv not in table or lv == REFERENCE:
                continue
            out = []
            for c in ("damage_rate", "protected_mis_edit_rate"):
                a, b = table[lv][c], ref[c]
                out.append(a["mean"] / b["mean"]
                           if a and b and b["mean"] > 1e-12 else float("nan"))
            print(f"{lv:16s}{out[0]:12.2f}{out[1]:13.2f}")

    # The policy question, answered by counting windows rather than by a test
    # on three means.
    print()
    print("policy rungs against the full method, window by window")
    print(f"{'rung':16s}{'seed':>5s}{'windows':>9s}{'different end':>15s}"
          f"{'different order':>17s}{'mis edit b/c':>15s}{'McNemar p':>12s}")
    pair = {}
    for lv in ("c_no_policy", "d_no_injection", "e_raw_reward"):
        pair[lv] = []
        for s in seeds:
            a = trace_index(Path(args.results) /
                            f"ablation_{lv}_seed{s}_traces.jsonl", lv)
            b = trace_index(Path(args.results) /
                            f"ablation_{REFERENCE}_seed{s}_traces.jsonl",
                            REFERENCE)
            ids = sorted(set(a) & set(b))
            if not ids:
                continue
            def end(r):
                return (r["modified"], r["crop_offset"],
                        round(r["dist_after"], 12) if r["dist_after"] is not None
                        else None)
            diff_end = sum(1 for i in ids if end(a[i]) != end(b[i]))
            diff_ord = sum(1 for i in ids
                           if [x["action"] for x in a[i]["steps"]]
                           != [x["action"] for x in b[i]["steps"]])
            bo = co = 0
            for i in ids:
                if a[i]["stratum"] not in PROTECTED:
                    continue
                ea, eb = bool(a[i]["modified"]), bool(b[i]["modified"])
                if ea and not eb:
                    bo += 1
                elif eb and not ea:
                    co += 1
            p = mcnemar_exact(bo, co)
            rec = {"seed": s, "n": len(ids), "different_end": diff_end,
                   "different_order": diff_ord, "mis_edit_b": bo,
                   "mis_edit_c": co, "mcnemar_p": p}
            pair[lv].append(rec)
            print(f"{lv:16s}{s:5d}{len(ids):9d}{diff_end:15d}{diff_ord:17d}"
                  f"{bo:8d} {co:6d}{p:12.3g}")

    # Cross reconciliation, check four. The damage rate is recomputed from the
    # traces with the table's own definition, which is not the distance the
    # trace field stores. `docs/number_selfchecks.md` records why the two differ,
    # so what is checked here is the edit count and the mis edit rate, which the
    # traces do carry exactly.
    print()
    print("cross reconciliation against the traces, edits and mis edit rate")
    print(f"{'rung':16s}{'seed':>5s}{'edits file':>12s}{'edits trace':>13s}"
          f"{'mis file':>10s}{'mis trace':>11s}")
    recon = []
    for lv in ORDER:
        if lv not in data:
            continue
        for row in data[lv]:
            s = row["seed"]
            t = trace_index(Path(args.results) /
                            f"ablation_{lv}_seed{s}_traces.jsonl", lv)
            if not t:
                continue
            edits = sum(1 for r in t.values() if r["modified"])
            prot = [r for r in t.values() if r["stratum"] in PROTECTED]
            mis = sum(1 for r in prot if r["modified"])
            rate = mis / len(prot) if prot else float("nan")
            ok = (edits == row["committed_edits"]
                  and abs(rate - row["protected_mis_edit_rate"]) < 1e-9)
            recon.append({"level": lv, "seed": s, "agrees": bool(ok),
                          "edits_file": row["committed_edits"],
                          "edits_trace": edits,
                          "mis_file": row["protected_mis_edit_rate"],
                          "mis_trace": rate})
            flag = "" if ok else "   <-- differs"
            print(f"{lv:16s}{s:5d}{row['committed_edits']:12d}{edits:13d}"
                  f"{row['protected_mis_edit_rate']:10.4f}{rate:11.4f}{flag}")
    bad = [r for r in recon if not r["agrees"]]
    print(f"{len(recon) - len(bad)} of {len(recon)} agree")

    Path(args.out).write_text(json.dumps(
        {"seeds": seeds, "table": table, "policy_pairs": pair,
         "reconciliation": recon}, indent=1, default=float), encoding="utf-8")
    print()
    print("___ABLATION_AGG_DONE___")


if __name__ == "__main__":
    main()
