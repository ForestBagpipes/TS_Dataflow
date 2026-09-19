"""Tighten the generated baseline discussion and the transfer paragraph.

The same facts, fewer words, and no semicolons.
"""
import io

PATH = "latex/fill_v46_reading.py"

OLD_SPREAD = '''        out["MAIN_BASELINE_SPREAD"] += (
            ". Both published baselines return a repaired or transformed context on every "
            "incomplete request, and on this protocol "
            + " and ".join(sorted(worse))
            + f" ends above the untouched input at {keep:.3f}. That is the premise of the paper "
              "seen from the outside: a repair applied unconditionally is not free, and the "
              "catalog shows the same thing from the inside, where the mean realised utility of "
              "a single action is negative on some backbones and positive on others "
              f"({chr(92)}{chr(92)}S{chr(92)}{chr(92)}ref{{sec:exp-exists}})")
        if detail:
            out["MAIN_BASELINE_SPREAD"] += (
                ". The loss is not uniform: " + "; ".join(detail)
                + ", so what costs a fixed repair its average is a minority of cells on which "
                  "it is badly wrong, which is the failure a per-request rule is able to avoid")'''

NEW_SPREAD = '''        out["MAIN_BASELINE_SPREAD"] += (
            ". Both published baselines repair or transform every incomplete request, and "
            + " and ".join(sorted(worse))
            + f" end above the untouched input at {keep:.3f}")
        if detail:
            out["MAIN_BASELINE_SPREAD"] += (
                ". The loss is concentrated rather than uniform, with " + ", ".join(detail)
                + ", so what costs a fixed repair its average is the minority of cells on which "
                  "it is badly wrong, and that is the failure a per-request rule can avoid")'''

OLD_DETAIL = '''            detail.append(f"{name} is below the untouched input on {wins} of the "
                          f"{wins + losses} source and backbone cells and above it on "
                          f"{losses}")'''
NEW_DETAIL = '''            detail.append(f"{name} below it on {wins} of {wins + losses} "
                          f"source and backbone cells")'''

OLD_CH2 = '''        out["ROBUST_CH2"] = (
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
            f"everywhere")'''

NEW_CH2 = '''        ch2_best = min(("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "SAITS", "TATO",
                        "FULL_INTROACT"),
                       key=lambda k: rows_ch2[k]["mase"] if k in rows_ch2 else 9e9)
        tail = ("and it reaches the lowest macro average of the deployable rows"
                if ch2_best == "FULL_INTROACT" else
                f"and the lowest macro average there belongs to "
                f"{DISPLAY.get(ch2_best, ch2_best)} at {rows_ch2[ch2_best]['mase']:.3f}")
        out["ROBUST_CH2"] = (
            f"On the held-out family the frozen procedure improves on the untouched input, "
            f"{rows_ch2['FULL_INTROACT']['mase']:.3f} against "
            f"{rows_ch2['NATIVE_KEEP']['mase']:.3f} with a paired interval that excludes zero, "
            f"it has the best average rank of the deployable rows at "
            f"{ch2['average_rank']['FULL_INTROACT']:.2f}, " + tail)'''


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    for old, new in ((OLD_SPREAD, NEW_SPREAD), (OLD_DETAIL, NEW_DETAIL), (OLD_CH2, NEW_CH2)):
        assert old in text, old[:60]
        text = text.replace(old, new)
    io.open(PATH, "w", encoding="utf-8").write(text)
    import ast
    ast.parse(text)
    print("generated readings tightened")


if __name__ == "__main__":
    main()
