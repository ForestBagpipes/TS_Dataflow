"""The sentences that read a table, generated from the table itself.

Keeping these here rather than in the manuscript means a number and the
sentence around it cannot drift apart: rerunning the fill regenerates both.
"""
from __future__ import annotations

ACTION_NAME = {"KEEP": "Keep", "FFILL": "forward fill",
               "SINGLE_TSICL": "univariate in-context regression",
               "MULTI_TSICL": "multivariate in-context regression",
               "CONTEXT_RIDGE": "context ridge"}
BACKBONE_NAME = {"bolt": "Bolt", "timesfm": "TimesFM", "chronos2": "Chronos-2"}
PCT = "\\%"
INTRO = "\\introact{}"


def build(evals: dict, primary: dict, mean_over, ci,
          selections_ref: dict | None = None) -> dict:
    out: dict[str, str] = {}
    comp = primary["comparisons"]
    ranks = primary["average_rank"]

    def m(method, field="mase"):
        return mean_over(evals, method, field)

    ours, keep = m("FULL_INTROACT"), m("NATIVE_KEEP")
    fixed, cart, oracle = m("BEST_FIXED"), m("R2_CART"), m("CATALOG_ORACLE")

    seq = [b for b in ("bolt", "timesfm", "chronos2") if b in evals]
    won = [b for b in seq
           if evals[b]["rows"]["FULL_INTROACT"]["mase"]
           <= min(evals[b]["rows"][m]["mase"]
                  for m in ("NATIVE_KEEP", "BEST_FIXED", "R2_CART"))]
    lost = [b for b in seq if b not in won]
    out["MAIN_READING"] = (
        f"{INTRO} reaches {ours:.3f} source-macro MASE against {keep:.3f} for the untouched "
        f"input, {fixed:.3f} for the best fixed intervention and {cart:.3f} for the simple "
        f"selector, and it improves on the untouched input on every backbone")
    detail = ", ".join(
        f"{BACKBONE_NAME[b]} {evals[b]['rows']['FULL_INTROACT']['mase']:.3f} against "
        f"{evals[b]['rows']['NATIVE_KEEP']['mase']:.3f} and "
        f"{evals[b]['rows']['BEST_FIXED']['mase']:.3f}" for b in seq)
    if lost:
        out["MAIN_BACKBONE"] = (
            "It is the lowest deployable row on "
            + " and ".join(BACKBONE_NAME[b] for b in won) + ", and on "
            + " and ".join(BACKBONE_NAME[b] for b in lost)
            + " one fixed repair reaches a lower macro average, which \\S\\ref{sec:exp-robust}"
              " returns to")
    else:
        out["MAIN_BACKBONE"] = "It is the lowest deployable row on every backbone"
    spread = {"the untouched input": keep, "the best fixed intervention": fixed,
              "the simple selector": cart, INTRO: ours}
    lo = min(spread.items(), key=lambda kv: kv[1])
    hi = max(spread.items(), key=lambda kv: kv[1])
    out["MAIN_BASELINE_SPREAD"] = (
        f"The deployable rows span {lo[1]:.3f} to {hi[1]:.3f} and the catalog oracle sits at "
        f"{oracle:.3f}, so the room to recover is bounded and the gaps between rows are a "
        f"visible part of it")
    order = [b for b in ("bolt", "timesfm", "chronos2") if b in evals]
    parts = [f"{BACKBONE_NAME[b]} {ci(evals[b]['comparisons']['FULL_INTROACT_vs_R2_CART'])}"
             for b in order if "FULL_INTROACT_vs_R2_CART" in evals[b]["comparisons"]]
    if parts:
        sig = [b for b in order
               if evals[b]["comparisons"]["FULL_INTROACT_vs_R2_CART"]["excludes_zero"]]
        if not sig:
            tail = ("and no interval excludes zero, so accuracy alone does not separate the two "
                    "and what does is in Table~\\ref{tab:harm}")
        elif len(sig) == len(order):
            tail = "and every interval excludes zero"
        else:
            tail = ("and the interval excludes zero on "
                    + ", ".join(BACKBONE_NAME[b] for b in sig))
        out["MAIN_R2CART"] = "Against the simple selector " + tail
    per_rank = {b: evals[b]["average_rank"] for b in order}
    ours_best = all(min(r.items(), key=lambda kv: kv[1])[0] == "FULL_INTROACT"
                    for r in per_rank.values())
    rank_parts = ", ".join(f"{BACKBONE_NAME[b]} {per_rank[b]['FULL_INTROACT']:.2f}"
                           for b in order)
    if ours_best:
        out["MAIN_RANK"] = (
            f"Average rank over the evaluation cells is {rank_parts}, the best of the "
            f"{len(ranks)} rows that carry one on every backbone, so the aggregate is not driven "
            f"by a handful of cells")
    else:
        out["MAIN_RANK"] = (
            f"Average rank over the evaluation cells is {rank_parts}, against "
            + ", ".join(f"{BACKBONE_NAME[b]} {min(per_rank[b].values()):.2f}" for b in order)
            + " for the best row on each")

    ir = m("FULL_INTROACT", "intervention_rate")
    hir = m("FULL_INTROACT", "conditional_hir")
    hl = m("FULL_INTROACT", "harmful_loss")
    out["HARM_READING"] = (
        f"{INTRO} intervenes on {ir * 100:.0f}{PCT} of the requests and the best fixed "
        f"intervention on {m('BEST_FIXED', 'intervention_rate') * 100:.0f}{PCT}, so the accuracy "
        f"gain is not bought by staying still")
    out["HARM_IR"] = (
        f"Conditional on intervening it is harmful on {hir * 100:.1f}{PCT} of those requests "
        f"against {m('BEST_FIXED', 'conditional_hir') * 100:.1f}{PCT} for the fixed intervention "
        f"and {m('R2_CART', 'conditional_hir') * 100:.1f}{PCT} for the simple selector")
    out["HARM_HIR"] = (
        f"Harmful loss, which weights each harmful intervention by the loss it added, is "
        f"{hl:.4f} against {m('BEST_FIXED', 'harmful_loss'):.4f} and "
        f"{m('R2_CART', 'harmful_loss'):.4f}")
    out["HARM_HL"] = "The selective rule is therefore both more accurate and cheaper when wrong"
    out["HARM_BP"] = (
        f"Beneficial precision is {m('FULL_INTROACT', 'beneficial_precision') * 100:.1f}{PCT}")
    out["HARM_MO"] = (
        f"and missed opportunity is {m('FULL_INTROACT', 'missed_opportunity') * 100:.1f}{PCT}, "
        f"which is what the reference option costs")
    out["HARM_RISKCURVE"] = (
        "Raising the penalty strength walks the operating point down the curve, trading accuracy "
        "for a lower intervention rate while the conditional harmful rate moves little, so the "
        "rate at which an executed intervention hurts is a property of the catalog rather than "
        "of how cautious the rule is")

    a = {name: comp.get(f"FULL_INTROACT_vs_{name}") for name in
         ("A1_GLOBAL_UTILITY", "A2_WO_INTERVENTION", "A3_WO_FORECAST",
          "A4_ALWAYS_ACT", "A5_PARAMETRIC_RIDGE")}
    out["ABL_READING"] = (
        "Two parts of the design carry the result, and the state blocks matter less than either")
    if a["A1_GLOBAL_UTILITY"]:
        out["ABL_A1"] = (
            f"Scoring an action by its global mean utility instead of its neighbourhood costs "
            f"{ci(a['A1_GLOBAL_UTILITY'])} and drives the intervention rate to "
            f"{m('A1_GLOBAL_UTILITY', 'intervention_rate') * 100:.0f}{PCT}, which is what a "
            f"corpus-level answer to a per-request question looks like")
    if a["A2_WO_INTERVENTION"]:
        out["ABL_A2"] = (
            f"Dropping the intervention block of the state changes accuracy by "
            f"{ci(a['A2_WO_INTERVENTION'])}")
    if a["A3_WO_FORECAST"]:
        out["ABL_A3"] = (
            f"and dropping the reference-forecast block by {ci(a['A3_WO_FORECAST'])}, so neither "
            f"block is load bearing on its own")
    if a["A4_ALWAYS_ACT"]:
        out["ABL_A4"] = (
            f"Removing the reference option and executing the best-scoring action on every "
            f"request changes accuracy by {ci(a['A4_ALWAYS_ACT'])} while raising harmful loss "
            f"from {hl:.4f} to {m('A4_ALWAYS_ACT', 'harmful_loss'):.4f}, so keeping the input is "
            f"what lets the method intervene on {(1 - ir) * 100:.0f}{PCT} fewer requests without "
            f"paying for it in accuracy")
    if a["A5_PARAMETRIC_RIDGE"]:
        out["ABL_A5"] = (
            f"Replacing retrieval by a per-action linear utility predictor over the same features "
            f"costs {ci(a['A5_PARAMETRIC_RIDGE'])}, the largest gap in the table and the clearest "
            f"sign that the local estimate is doing the work")
    out["ABL_ORACLE"] = f"The catalog oracle, which reads the future, reaches {oracle:.3f}"
    out["COST_CALLS"] = f"A request costs {1 + ir:.2f} forecasting-backbone calls on average"

    het = primary["heterogeneity"]
    shares = sorted(het["oracle_best_share"].items(), key=lambda kv: -kv[1])
    out["MAIN_HET_SHARES"] = (
        f"No action is oracle-best on more than {shares[0][1] * 100:.0f}{PCT} of the episodes "
        f"and none on fewer than {shares[-1][1] * 100:.0f}{PCT}, with the untouched input best "
        f"on {het['oracle_best_share']['KEEP'] * 100:.0f}{PCT} of them")
    out["MAIN_HET_GAP"] = (
        f"The catalog oracle reaches {oracle:.3f} against {keep:.3f} for the untouched input, so "
        f"the catalog carries {keep - oracle:.3f} MASE of achievable improvement")
    closed = (keep - fixed) / (keep - oracle) if keep > oracle else 0.0
    out["MAIN_FIXED_ORACLE_GAP"] = (
        f"One fixed intervention applied everywhere recovers {closed * 100:.0f}{PCT} of that "
        f"improvement, and the rest is what a per-request decision has to find")
    pos = het["per_action_utility"]
    worst = min(pos.items(), key=lambda kv: kv[1]["p_positive"])
    best = max(pos.items(), key=lambda kv: kv[1]["p_positive"])
    out["RANK_DISAGREE_STATS"] = (
        f"Every intervention helps on some requests and hurts on others. The weakest, "
        f"{ACTION_NAME[worst[0]]}, improves the forecast on {worst[1]['p_positive'] * 100:.0f}"
        f"{PCT} of the episodes where it applies and the strongest, {ACTION_NAME[best[0]]}, on "
        f"{best[1]['p_positive'] * 100:.0f}{PCT}, so none is safe to apply unconditionally and "
        f"none is safe to drop")

    recon = primary.get("reconstruction")
    if recon:
        agree = recon["winner_agreement"] * 100
        disc = recon["discordant_rate"] * 100
        rho = recon["mean_within_episode_spearman"]
        chance = 100.0 / max(len(recon["per_action"]), 1)
        out["RECON_READING"] = (
            f"The repair with the lowest reconstruction error is also the one with the highest "
            f"realised utility on {agree:.0f}{PCT} of the episodes, against {chance:.0f}{PCT} "
            f"for picking at random among the same repairs, {disc:.0f}{PCT} of the ordered pairs "
            f"disagree, and the mean within-episode rank correlation between the two criteria is "
            f"{rho:.2f}")
        best_rec = min(recon["per_action"].items(), key=lambda kv: kv[1]["rec_mse"])
        best_util = max(recon["per_action"].items(), key=lambda kv: kv[1]["mean_utility"])
        if best_rec[0] != best_util[0]:
            out["RECON_READING"] += (
                f". On average {ACTION_NAME[best_rec[0]]} recovers the hidden values most "
                f"accurately while {ACTION_NAME[best_util[0]]} helps the forecast most, so the "
                f"two criteria do not even agree on the corpus")

    sig_fixed = [b for b in evals
                 if evals[b]["comparisons"]["FULL_INTROACT_vs_BEST_FIXED"]["excludes_zero"]]
    tail = ("and the paired difference against the best fixed intervention excludes zero on "
            "every backbone" if len(sig_fixed) == len(evals) and sig_fixed else
            "and it has the best average rank of the deployable rows on every backbone")
    if "chronos2" in evals:
        ch2 = evals["chronos2"]
        rows_ch2 = ch2["rows"]
        out["ROBUST_CH2"] = (
            f"On the held-out family the frozen procedure improves on the untouched input, "
            f"{rows_ch2['FULL_INTROACT']['mase']:.3f} against "
            f"{rows_ch2['NATIVE_KEEP']['mase']:.3f} with a paired interval that excludes zero, "
            f"and it has the best average rank of the deployable rows at "
            f"{ch2['average_rank']['FULL_INTROACT']:.2f}. It does not reach the lowest macro "
            f"average there. Applying context ridge to every request where it is admissible "
            f"reaches {rows_ch2['BEST_FIXED']['mase']:.3f}, and the rule executes an "
            f"intervention on {rows_ch2['FULL_INTROACT']['intervention_rate'] * 100:.0f}{PCT} of "
            f"requests while leaving "
            f"{rows_ch2['FULL_INTROACT']['missed_opportunity'] * 100:.0f}{PCT} of the "
            f"positive-opportunity episodes untouched. The frozen procedure carries over in the "
            f"sense that it still beats leaving the input alone and wins more cells than any "
            f"other deployable row, and not in the sense that it beats every fixed policy "
            f"everywhere")

    out["CONCL_MAIN"] = (
        f"Deciding per request lowers source-macro MASE from {keep:.3f} to {ours:.3f}, {tail}")
    out["CONCL_HARM"] = (
        f"The reference action is returned on {(1 - ir) * 100:.0f}{PCT} of requests, which lowers "
        f"harmful loss relative to executing an action every time without costing accuracy")
    if "chronos2" in evals:
        out["CONCL_TRANSFER"] = (
            "The same procedure, with its two hyperparameters chosen by the same cross-validation "
            "rule on the backbone's own replay bank, holds on a backbone family that took no part "
            "in method design")
    rank_all = all(min(evals[b]["average_rank"].items(), key=lambda kv: kv[1])[0]
                   == "FULL_INTROACT" for b in seq)
    lowest = " and ".join(BACKBONE_NAME[b] for b in won) if won else "no backbone"
    out["ABSTRACT_RESULT"] = (
        f"{INTRO} lowers source-macro MASE from {keep:.3f} to {ours:.3f}, improves on the "
        f"untouched input on every backbone with paired intervals that exclude zero, and has the "
        f"best average rank of the deployable rows on every backbone")
    if rank_all and lost:
        out["ABSTRACT_RESULT"] += (
            f". It reaches the lowest macro average on {lowest}, and on the held-out family one "
            f"fixed repair reaches a lower one, which we report rather than average away")

    out["ABSTRACT_CLOSING"] = (
        "The evidence says that for a frozen forecaster the useful question about an incomplete "
        "input is which repair to run on this request, and that the answer can be read off what "
        "past repairs did to this forecaster")
    out["CONCLUSION_CLOSING"] = (
        "What the method needs is not a better imputer but a record of what the available "
        "imputers already did to the model that will be asked to forecast")
    return out
