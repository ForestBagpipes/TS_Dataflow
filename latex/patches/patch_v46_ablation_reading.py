"""The ablation paragraph quoted intervals from one backbone next to a table of
averages, and it read a significant interval against the method as if it were
nothing.  Both are now said out loud.
"""
import io

PATH = "latex/fill_v46_reading.py"

OLD_LEAD = '''    out["ABL_READING"] = (
        "Two parts of the design carry the result, and the state blocks matter less than either")'''

NEW_LEAD = '''    out["ABL_READING"] = (
        "Two parts of the design carry the result, and the state blocks matter less than either. "
        "Each interval below is the paired difference on the primary backbone, while the table "
        "columns average over the three")'''

OLD_A2 = '''    if a["A2_WO_INTERVENTION"]:
        out["ABL_A2"] = (
            f"Dropping the intervention block of the state changes accuracy by "
            f"{ci(a['A2_WO_INTERVENTION'])}")
    if a["A3_WO_FORECAST"]:
        out["ABL_A3"] = (
            f"Dropping the reference-forecast block changes it by {ci(a['A3_WO_FORECAST'])}, so "
            f"neither state block is load bearing on its own")'''

NEW_A2 = '''    if a["A2_WO_INTERVENTION"]:
        entry = a["A2_WO_INTERVENTION"]
        against_us = entry["excludes_zero"] and entry["difference"] > 0
        out["ABL_A2"] = (
            f"Dropping the intervention block of the state changes accuracy by {ci(entry)}"
            + (", so on that backbone the block does not pay for itself" if against_us else ""))
    if a["A3_WO_FORECAST"]:
        out["ABL_A3"] = (
            f"Dropping the reference-forecast block changes it by {ci(a['A3_WO_FORECAST'])}. "
            f"Averaged over the three backbones the first ablation lands at "
            f"{m('A2_WO_INTERVENTION'):.3f} and the second at {m('A3_WO_FORECAST'):.3f} against "
            f"{ours:.3f} for the full method, so the reference-forecast block is the one that "
            f"shows up in the average")'''


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert OLD_LEAD in text, "ablation lead"
    assert OLD_A2 in text, "ablation state blocks"
    text = text.replace(OLD_LEAD, NEW_LEAD, 1)
    text = text.replace(OLD_A2, NEW_A2, 1)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("ablation paragraph now names the backbone and the direction")


if __name__ == "__main__":
    main()
