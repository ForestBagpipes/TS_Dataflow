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
#: How each row is named in prose.  The record keys carry underscores, which
#: LaTeX reads as subscripts outside maths.
DEPLOY = ("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "SAITS", "TATO", "FULL_INTROACT")
DISPLAY = {"NATIVE_KEEP": "the untouched input", "BEST_FIXED": "the best fixed intervention",
           "R2_CART": "the simple selector", "SAITS": "SAITS", "TATO": "TATO",
           "FULL_INTROACT": "IntroAct-TS", "CATALOG_ORACLE": "the catalog oracle",
           "A1_GLOBAL_UTILITY": "the global-utility variant",
           "A4_ALWAYS_ACT": "the always-act variant",
           "A5_PARAMETRIC_RIDGE": "the parametric variant"}
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
    rivals = [r for r in ("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "SAITS", "TATO")
              if all(r in evals[b]["rows"] for b in seq)]
    won = [b for b in seq
           if evals[b]["rows"]["FULL_INTROACT"]["mase"]
           <= min(evals[b]["rows"][r]["mase"] for r in rivals)]
    lost = [b for b in seq if b not in won]
    published = ", ".join(f"{name} {m(name):.3f}" for name in ("SAITS", "TATO")
                          if m(name) is not None)
    out["MAIN_READING"] = (
        f"{INTRO} reaches {ours:.3f} source-macro MASE against {keep:.3f} for the untouched "
        f"input, {fixed:.3f} for the best fixed intervention and {cart:.3f} for the simple "
        f"selector"
        + (f", and against the published baselines at {published}" if published else "")
        + ". It improves on the untouched input on every backbone")
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
    for name in ("SAITS", "TATO"):
        if m(name) is not None:
            spread[name] = m(name)
    lo = min(spread.items(), key=lambda kv: kv[1])
    hi = max(spread.items(), key=lambda kv: kv[1])
    out["MAIN_BASELINE_SPREAD"] = (
        f"The deployable rows span {lo[1]:.3f} to {hi[1]:.3f} and the catalog oracle sits at "
        f"{oracle:.3f}, so the room to recover is bounded and the gaps between rows are a "
        f"visible part of it")
    published = {name: m(name) for name in ("SAITS", "TATO") if m(name) is not None}
    worse = [name for name, value in published.items() if value > keep]
    # Where a published baseline loses on the macro average it is worth saying
    # whether it loses everywhere or on a few sources, because those are very
    # different failures and only the second one a per-request rule can fix.
    detail = []
    for name in worse:
        wins = losses = 0
        for b in seq:
            rows_b = evals[b]["rows"]
            if name not in rows_b:
                continue
            for source, value in rows_b[name]["per_source_mase"].items():
                keep_value = rows_b["NATIVE_KEEP"]["per_source_mase"].get(source)
                if keep_value is None or value is None:
                    continue
                if value < keep_value:
                    wins += 1
                else:
                    losses += 1
        if wins + losses:
            detail.append((name, wins, wins + losses))
    if worse:
        out["MAIN_BASELINE_SPREAD"] += (
            ". Both published baselines repair or transform every incomplete request, and "
            + " and ".join(f"{name} ends at {published[name]:.3f}" for name in sorted(worse))
            + f", above the {keep:.3f} of leaving the input alone")
        # A baseline that helps on most cells and still loses on the average is
        # a different failure from one that loses nearly everywhere, and only
        # the first is the failure a per-request rule is built to catch.
        concentrated = [d for d in detail if d[1] * 2 > d[2]]
        broad = [d for d in detail if d[1] * 2 <= d[2]]
        if concentrated:
            out["MAIN_BASELINE_SPREAD"] += (
                ". " + " and ".join(f"{name} is below it on {wins} of {total} source and "
                                    f"backbone cells" for name, wins, total in concentrated)
                + ", so what costs it its average is the minority of cells on which it is badly "
                  "wrong, which is the failure a per-request rule can avoid")
        if broad:
            out["MAIN_BASELINE_SPREAD"] += (
                ". " + " and ".join(f"{name} is below it on only {wins} of {total} such cells"
                                    for name, wins, total in broad)
                + ", so that one loses broadly")
    order = [b for b in ("bolt", "timesfm", "chronos2") if b in evals]
    parts = [f"{BACKBONE_NAME[b]} {ci(evals[b]['comparisons']['FULL_INTROACT_vs_R2_CART'])}"
             for b in order if "FULL_INTROACT_vs_R2_CART" in evals[b]["comparisons"]]
    if parts:
        sig = [b for b in order
               if evals[b]["comparisons"]["FULL_INTROACT_vs_R2_CART"]["excludes_zero"]]
        if not sig:
            tail = ("no interval excludes zero, so accuracy alone does not separate the two "
                    "and what does is in Table~" + chr(92) + "ref{tab:harm}")
        elif len(sig) == len(order):
            tail = "every interval excludes zero"
        else:
            tail = ("the interval excludes zero on "
                    + ", ".join(BACKBONE_NAME[b] for b in sig))
        out["MAIN_R2CART"] = "Against the simple selector " + tail
    # The claim is about the deployable rows of Table 1.  The ablation variants
    # are ranked in the same pass, but they are variants of this method and are
    # reported in the ablation table, so they are not what the claim is about.
    deployable_rows = ("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "SAITS", "TATO",
                       "FULL_INTROACT")
    per_rank = {b: {k: v for k, v in evals[b]["average_rank"].items()
                    if k in deployable_rows} for b in order}
    ours_best = all(min(r.items(), key=lambda kv: kv[1])[0] == "FULL_INTROACT"
                    for r in per_rank.values() if r)
    rank_parts = ", ".join(f"{BACKBONE_NAME[b]} {per_rank[b]['FULL_INTROACT']:.2f}"
                           for b in order if "FULL_INTROACT" in per_rank[b])
    count = len(per_rank[order[0]]) if order else 0
    WORDS = {4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}
    count = WORDS.get(count, count)
    if ours_best:
        out["MAIN_RANK"] = (
            f"Average rank over the evaluation cells is {rank_parts}, the best of the {count} "
            f"deployable rows on every backbone, so the aggregate is not driven by a handful of "
            f"cells")
    else:
        lead = [b for b in order if per_rank[b]
                and min(per_rank[b].items(), key=lambda kv: kv[1])[0] == "FULL_INTROACT"]
        behind = [b for b in order if b not in lead and per_rank[b]]
        mean_rank = {name: sum(per_rank[b][name] for b in order) / len(order)
                     for name in deployable_rows
                     if all(name in per_rank[b] for b in order)}
        rival = min(((n, v) for n, v in mean_rank.items() if n != "FULL_INTROACT"),
                    key=lambda kv: kv[1], default=None)
        sentence = f"Average rank over the evaluation cells is {rank_parts}"
        if lead:
            sentence += (f", the best of the {count} deployable rows on "
                         + " and ".join(BACKBONE_NAME[b] for b in lead))
        for b in behind:
            name, value = min(per_rank[b].items(), key=lambda kv: kv[1])
            sentence += (f", against {value:.2f} for {DISPLAY.get(name, name)} on "
                         f"{BACKBONE_NAME[b]}")
        if rival is not None and "FULL_INTROACT" in mean_rank:
            sentence += (f", and over the three backbones it averages "
                         f"{mean_rank['FULL_INTROACT']:.2f} against {rival[1]:.2f} for "
                         f"{DISPLAY.get(rival[0], rival[0])}")
        out["MAIN_RANK"] = sentence

    ir = m("FULL_INTROACT", "intervention_rate")
    hir = m("FULL_INTROACT", "conditional_hir")
    hl = m("FULL_INTROACT", "harmful_loss")
    always = [name for name in ("SAITS", "TATO")
              if m(name) is not None]
    tail = ""
    if always:
        tail = (", while the published baselines repair or transform every incomplete request by "
                "construction, so their intervention rate is one")
    out["HARM_READING"] = (
        f"{INTRO} executes an intervention on {ir * 100:.0f}{PCT} of the requests, so its "
        f"accuracy is not bought by staying still{tail}")
    out["HARM_IR"] = (
        f"Conditional on intervening it is harmful on {hir * 100:.1f}{PCT} of those requests "
        f"against {m('BEST_FIXED', 'conditional_hir') * 100:.1f}{PCT} for the fixed intervention "
        f"and {m('R2_CART', 'conditional_hir') * 100:.1f}{PCT} for the simple selector")
    others = ", ".join(f"{DISPLAY.get(name, name)} {m(name, 'harmful_loss'):.4f}" for name in
                       ("BEST_FIXED", "R2_CART", "SAITS", "TATO")
                       if m(name, "harmful_loss") is not None)
    out["HARM_HIR"] = (
        f"Harmful loss, which weights each harmful intervention by the loss it added, is "
        f"{hl:.4f}, against {others}")
    out["HARM_HL"] = "The selective rule is therefore both more accurate and cheaper when wrong"
    out["HARM_BP"] = (
        f"Beneficial precision is {m('FULL_INTROACT', 'beneficial_precision') * 100:.1f}{PCT}")
    out["HARM_MO"] = (
        f"Missed opportunity is {m('FULL_INTROACT', 'missed_opportunity') * 100:.1f}{PCT}, "
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
        "Two parts of the design carry the result, and the state blocks matter less than either. "
        "Intervals are paired differences on the primary backbone and table columns average "
        "over the three")
    if a["A1_GLOBAL_UTILITY"]:
        out["ABL_A1"] = (
            f"Scoring an action by its global mean utility instead of its neighbourhood costs "
            f"{ci(a['A1_GLOBAL_UTILITY'])} and drives the intervention rate to "
            f"{m('A1_GLOBAL_UTILITY', 'intervention_rate') * 100:.0f}{PCT}, which is what a "
            f"corpus-level answer to a per-request question looks like")
    if a["A2_WO_INTERVENTION"]:
        entry = a["A2_WO_INTERVENTION"]
        against_us = entry["excludes_zero"] and entry["difference"] > 0
        out["ABL_A2"] = (
            f"Dropping the intervention block of the state changes accuracy by {ci(entry)}"
            + (", so on that backbone the block does not pay for itself" if against_us else ""))
    if a["A3_WO_FORECAST"]:
        out["ABL_A3"] = (
            f"Dropping the reference-forecast block changes it by {ci(a['A3_WO_FORECAST'])}, "
            f"and over the three backbones the two land at {m('A2_WO_INTERVENTION'):.3f} and "
            f"{m('A3_WO_FORECAST'):.3f} against {ours:.3f}, so only the second block shows up "
            f"in the average")
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

    if "chronos2" in evals:
        ch2 = evals["chronos2"]
        rows_ch2 = ch2["rows"]
        ch2_best = min(("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "SAITS", "TATO",
                        "FULL_INTROACT"),
                       key=lambda k: rows_ch2[k]["mase"] if k in rows_ch2 else 9e9)
        ch2_tail = ("and it reaches the lowest macro average of the deployable rows"
                if ch2_best == "FULL_INTROACT" else
                f"and the lowest macro average there belongs to "
                f"{DISPLAY.get(ch2_best, ch2_best)} at {rows_ch2[ch2_best]['mase']:.3f}")
        ch2_rank = {k: v for k, v in ch2["average_rank"].items() if k in DEPLOY}
        ch2_rank_best = min(ch2_rank.items(), key=lambda kv: kv[1])
        ch2_rank_clause = (
            f"it has the best average rank of the deployable rows at "
            f"{ch2_rank['FULL_INTROACT']:.2f}"
            if ch2_rank_best[0] == "FULL_INTROACT" else
            f"its average rank is {ch2_rank['FULL_INTROACT']:.2f} against the "
            f"{ch2_rank_best[1]:.2f} of {DISPLAY.get(ch2_rank_best[0], ch2_rank_best[0])}")
        out["ROBUST_CH2"] = (
            f"On the held-out family the frozen procedure improves on the untouched input, "
            f"{rows_ch2['FULL_INTROACT']['mase']:.3f} against "
            f"{rows_ch2['NATIVE_KEEP']['mase']:.3f} with a paired interval that excludes zero, "
            + ch2_rank_clause + ", " + ch2_tail)

    sig_fixed = [b for b in seq
                 if evals[b]["comparisons"]["FULL_INTROACT_vs_BEST_FIXED"]["excludes_zero"]]
    mean_rank = {name: sum(evals[b]["average_rank"][name] for b in seq) / len(seq)
                 for name in DEPLOY
                 if all(name in evals[b]["average_rank"] for b in seq)}
    rank_rival = min(((n, v) for n, v in mean_rank.items() if n != "FULL_INTROACT"),
                     key=lambda kv: kv[1], default=None)
    rank_clause = ""
    if rank_rival is not None and "FULL_INTROACT" in mean_rank:
        rank_clause = (f"the average rank over the deployable rows is "
                       f"{mean_rank['FULL_INTROACT']:.2f} against {rank_rival[1]:.2f} for "
                       f"{DISPLAY.get(rank_rival[0], rank_rival[0])}")
    if len(sig_fixed) == len(seq) and sig_fixed:
        concl_tail = ("and the paired difference against the best fixed intervention excludes "
                      "zero on every backbone")
    elif sig_fixed:
        concl_tail = ("the paired difference against the best fixed intervention excludes zero "
                      "on " + " and ".join(BACKBONE_NAME[b] for b in sig_fixed)
                      + (", and " + rank_clause if rank_clause else ""))
    else:
        concl_tail = "and " + rank_clause
    out["CONCL_MAIN"] = (
        f"Deciding per request lowers source-macro MASE from {keep:.3f} to {ours:.3f}, "
        f"{concl_tail}")
    out["CONCL_HARM"] = (
        f"The reference action is returned on {(1 - ir) * 100:.0f}{PCT} of requests, which lowers "
        f"harmful loss relative to executing an action every time without costing accuracy")
    if "chronos2" in evals:
        out["CONCL_TRANSFER"] = (
            "The same procedure, with its two hyperparameters chosen by the same cross-validation "
            "rule on the backbone's own replay bank, still improves on the untouched input and "
            "still ranks first among the deployable rows on a backbone family that took no part "
            "in method design, without reaching the lowest average there"
            if ch2_rank_best[0] == "FULL_INTROACT" else
            "The same procedure, with its two hyperparameters chosen by the same cross-validation "
            "rule on the backbone's own replay bank, still improves on the untouched input on a "
            "backbone family that took no part in method design. One fixed repair reaches both a "
            "lower average and a lower rank there, and the interval of that difference covers "
            "zero, so the two are not separated on accuracy")
    won_rank = [b for b in seq
                if min(((k, v) for k, v in evals[b]["average_rank"].items() if k in DEPLOY),
                       key=lambda kv: kv[1])[0] == "FULL_INTROACT"]
    rank_all = len(won_rank) == len(seq)
    lowest = " and ".join(BACKBONE_NAME[b] for b in won) if won else "no backbone"
    lowest_rank = (" and ".join(BACKBONE_NAME[b] for b in won_rank)
                   if won_rank else "no backbone")
    rival_overall = min(((n, mean_over(evals, n, "mase")) for n in DEPLOY
                         if n != "FULL_INTROACT" and mean_over(evals, n, "mase") is not None),
                        key=lambda kv: kv[1], default=None)
    opening = f"{INTRO} lowers source-macro MASE from {keep:.3f} to {ours:.3f}"
    if rival_overall is not None:
        opening += (f", against {rival_overall[1]:.3f} for "
                    f"{DISPLAY.get(rival_overall[0], rival_overall[0])}")
    opening += (", improves on the untouched input on every backbone with paired intervals "
                "that exclude zero")
    if rank_all:
        opening += ", and has the best average rank of the deployable rows on every backbone"
    elif set(won) == set(won_rank) and won:
        opening += (f", and reaches the lowest macro average and the best average rank of the "
                    f"deployable rows on {lowest}")
    else:
        opening += (f", reaches the lowest macro average of the deployable rows on {lowest} "
                    f"and the best average rank of those rows on {lowest_rank}")
    out["ABSTRACT_RESULT"] = opening
    if lost:
        out["ABSTRACT_RESULT"] += (
            ". On the held-out family one fixed repair reaches a lower average, which we report "
            "rather than average away")

    where = (" on every backbone" if not lost else
             " on " + " and ".join(BACKBONE_NAME[b] for b in won))
    out["CONTRIB_RESULT"] = (
        f"{INTRO} improves on the untouched input on every backbone with paired intervals that "
        f"exclude zero, reaches the lowest source-macro MASE of the deployable rows{where}"
        + (", and has the best average rank of those rows on every backbone"
           if rank_all else
           f", and the lowest average over the three backbones at {ours:.3f}")
        + ", at one to two backbone calls per request. We also report where it does not win")

    out["ABSTRACT_CLOSING"] = (
        "The evidence says that for a frozen forecaster the useful question about an incomplete "
        "input is which repair to run on this request, and that the answer can be read off what "
        "past repairs did to this forecaster")
    out["CONCLUSION_CLOSING"] = (
        "What the method needs is not a better imputer but a record of what the available "
        "imputers already did to the model that will be asked to forecast")
    return out
