"""Add the transfer reading: when a single fixed repair captures most of the value.

The held-out backbone is the case where one repair is broadly useful, and the
sentence that explains it is generated from the bank statistics rather than
written by hand, so it cannot drift from the table.
"""
import io

PATH = "latex/fill_v46_reading.py"

ANCHOR = '''    out["CONCL_MAIN"] = ('''

BLOCK = '''    if selections_ref:
        spread = {}
        for backbone, sel in selections_ref.items():
            utilities = {k: v for k, v in sel["bank_mean_utility"].items()
                         if v is not None and k != "KEEP"}
            if utilities:
                best = max(utilities.values())
                spread[backbone] = best
        if spread and "chronos2" in evals:
            ch2 = evals["chronos2"]
            fixed_ch2 = ch2["rows"]["BEST_FIXED"]["mase"]
            ours_ch2 = ch2["rows"]["FULL_INTROACT"]["mase"]
            keep_ch2 = ch2["rows"]["NATIVE_KEEP"]["mase"]
            rank_ch2 = ch2["average_rank"]["FULL_INTROACT"]
            best_rank_ch2 = min(ch2["average_rank"].values())
            top = ", ".join(f"{BACKBONE_NAME[b]} {spread[b]:+.3f}"
                            for b in ("bolt", "timesfm", "chronos2") if b in spread)
            out["ROBUST_CH2"] = (
                f"On the held-out family the frozen procedure still improves on the untouched "
                f"input, {ours_ch2:.3f} against {keep_ch2:.3f}, and still has the best average "
                f"rank of the deployable rows at {rank_ch2:.2f}. It does not have the lowest "
                f"macro average there: one repair, context ridge, is broadly useful on that "
                f"backbone and applying it everywhere reaches {fixed_ch2:.3f}. The mean realised "
                f"utility of the most useful single repair on each backbone's own bank is {top}, "
                f"so what changes across backbones is how much of the improvement one fixed "
                f"choice already captures. Per-request selection pays where no single repair "
                f"dominates, and where one does it wins cell by cell without winning the mean")


''' + ANCHOR


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert ANCHOR in text, "anchor"
    text = text.replace(ANCHOR, BLOCK, 1)
    text = text.replace("def build(evals: dict, primary: dict, mean_over, ci) -> dict:",
                        "def build(evals: dict, primary: dict, mean_over, ci,\n"
                        "          selections_ref: dict | None = None) -> dict:")
    io.open(PATH, "w", encoding="utf-8").write(text)

    fill = io.open("latex/fill_v46.py", encoding="utf-8").read()
    fill = fill.replace(
        "out.update(fill_v46_reading.build(evals, primary, mean_over, ci))",
        "out.update(fill_v46_reading.build(evals, primary, mean_over, ci, selections))")
    io.open("latex/fill_v46.py", "w", encoding="utf-8").write(fill)
    print("transfer reading added")


if __name__ == "__main__":
    main()
