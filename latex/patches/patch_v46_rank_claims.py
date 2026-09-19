"""Four claims about average rank were written as text rather than read off the data.

They said the method held the best average rank of the deployable rows on every
backbone, which stopped being true once the selection rule changed.  Each one now
computes what it asserts, so the sentence follows the numbers instead of the
other way round.
"""
import io

PATH = "latex/fill_v46_reading.py"

OLD_DEAD = '''    sig_fixed = [b for b in evals
                 if evals[b]["comparisons"]["FULL_INTROACT_vs_BEST_FIXED"]["excludes_zero"]]
    tail = ("and the paired difference against the best fixed intervention excludes zero on "
            "every backbone" if len(sig_fixed) == len(evals) and sig_fixed else
            "and it has the best average rank of the deployable rows on every backbone")
    if "chronos2" in evals:'''

NEW_DEAD = '''    if "chronos2" in evals:'''

OLD_CH2 = '''        out["ROBUST_CH2"] = (
            f"On the held-out family the frozen procedure improves on the untouched input, "
            f"{rows_ch2['FULL_INTROACT']['mase']:.3f} against "
            f"{rows_ch2['NATIVE_KEEP']['mase']:.3f} with a paired interval that excludes zero, "
            f"it has the best average rank of the deployable rows at "
            f"{ch2['average_rank']['FULL_INTROACT']:.2f}, " + ch2_tail)'''

NEW_CH2 = '''        ch2_rank = {k: v for k, v in ch2["average_rank"].items() if k in DEPLOY}
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
            + ch2_rank_clause + ", " + ch2_tail)'''

OLD_CONCL = '''    sig_fixed = [b for b in seq
                 if evals[b]["comparisons"]["FULL_INTROACT_vs_BEST_FIXED"]["excludes_zero"]]
    concl_tail = ("and the paired difference against the best fixed intervention excludes zero "
                  "on every backbone" if len(sig_fixed) == len(seq) and sig_fixed else
                  "and it has the best average rank of the deployable rows on every backbone")
    out["CONCL_MAIN"] = (
        f"Deciding per request lowers source-macro MASE from {keep:.3f} to {ours:.3f}, "
        f"{concl_tail}")'''

NEW_CONCL = '''    sig_fixed = [b for b in seq
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
        f"{concl_tail}")'''

OLD_TRANSFER = '''        out["CONCL_TRANSFER"] = (
            "The same procedure, with its two hyperparameters chosen by the same cross-validation "
            "rule on the backbone's own replay bank, still improves on the untouched input and "
            "still ranks first among the deployable rows on a backbone family that took no part "
            "in method design, without reaching the lowest average there")'''

NEW_TRANSFER = '''        out["CONCL_TRANSFER"] = (
            "The same procedure, with its two hyperparameters chosen by the same cross-validation "
            "rule on the backbone's own replay bank, still improves on the untouched input and "
            "still ranks first among the deployable rows on a backbone family that took no part "
            "in method design, without reaching the lowest average there"
            if ch2_rank_best[0] == "FULL_INTROACT" else
            "The same procedure, with its two hyperparameters chosen by the same cross-validation "
            "rule on the backbone's own replay bank, still improves on the untouched input on a "
            "backbone family that took no part in method design. One fixed repair reaches both a "
            "lower average and a lower rank there, and the interval of that difference covers "
            "zero, so the two are not separated on accuracy")'''

OLD_ABS = '''    deployable_rows = ("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "SAITS", "TATO",
                       "FULL_INTROACT")
    rank_all = all(
        min(((k, v) for k, v in evals[b]["average_rank"].items() if k in deployable_rows),
            key=lambda kv: kv[1])[0] == "FULL_INTROACT" for b in seq)
    lowest = " and ".join(BACKBONE_NAME[b] for b in won) if won else "no backbone"
    out["ABSTRACT_RESULT"] = (
        f"{INTRO} lowers source-macro MASE from {keep:.3f} to {ours:.3f}, improves on the "
        f"untouched input on every backbone with paired intervals that exclude zero, and has the "
        f"best average rank of the deployable rows on every backbone")
    if rank_all and lost:
        out["ABSTRACT_RESULT"] += (
            f". It reaches the lowest macro average on {lowest}, and on the held-out family one "
            f"fixed repair reaches a lower one, which we report rather than average away")'''

NEW_ABS = '''    won_rank = [b for b in seq
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
            "rather than average away")'''

OLD_CONTRIB = '''    deployable_rows = ("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "SAITS", "TATO",
                       "FULL_INTROACT")
    rank_best = all(
        min(((k, v) for k, v in evals[b]["average_rank"].items() if k in deployable_rows),
            key=lambda kv: kv[1])[0] == "FULL_INTROACT" for b in seq)
    where = (" on every backbone" if not lost else
             " on " + " and ".join(BACKBONE_NAME[b] for b in won))
    out["CONTRIB_RESULT"] = (
        f"{INTRO} improves on the untouched input on every backbone with paired intervals that "
        f"exclude zero, reaches the lowest source-macro MASE of the deployable rows{where}"
        + (", and has the best average rank of those rows on every backbone"
           if rank_best else "")
        + ", at one to two backbone calls per request. We also report where it does not win")'''

NEW_CONTRIB = '''    where = (" on every backbone" if not lost else
             " on " + " and ".join(BACKBONE_NAME[b] for b in won))
    out["CONTRIB_RESULT"] = (
        f"{INTRO} improves on the untouched input on every backbone with paired intervals that "
        f"exclude zero, reaches the lowest source-macro MASE of the deployable rows{where}"
        + (", and has the best average rank of those rows on every backbone"
           if rank_all else
           f", and the lowest average over the three backbones at {ours:.3f}")
        + ", at one to two backbone calls per request. We also report where it does not win")'''

DEPLOY_CONST = '''DEPLOY = ("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "SAITS", "TATO", "FULL_INTROACT")
DISPLAY = '''


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    for name, old in (("dead tail", OLD_DEAD), ("chronos2", OLD_CH2),
                      ("conclusion", OLD_CONCL), ("transfer", OLD_TRANSFER),
                      ("abstract", OLD_ABS), ("contribution", OLD_CONTRIB)):
        assert old in text, name
    text = text.replace("DISPLAY = ", DEPLOY_CONST, 1)
    text = text.replace(OLD_DEAD, NEW_DEAD, 1)
    text = text.replace(OLD_CH2, NEW_CH2, 1)
    text = text.replace(OLD_CONCL, NEW_CONCL, 1)
    text = text.replace(OLD_TRANSFER, NEW_TRANSFER, 1)
    text = text.replace(OLD_ABS, NEW_ABS, 1)
    text = text.replace(OLD_CONTRIB, NEW_CONTRIB, 1)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("rank claims now read off the data")


if __name__ == "__main__":
    main()
