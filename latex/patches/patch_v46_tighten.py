"""Tighten the generated readings: the confidence-interval sentence and the
per-backbone sentence were listing the same numbers twice.
"""
import io

PATH = "latex/fill_v46.py"
READING = "latex/fill_v46_reading.py"

OLD_CI = '''    out["MAIN_DELTA_CI"] = (
        "Against the untouched input the paired difference is "
        + "; ".join(keep_parts) + ", " + tail_keep
        + ". Against the best fixed intervention it is "
        + "; ".join(fixed_parts) + ", " + tail_fixed)'''
NEW_CI = '''    out["MAIN_DELTA_CI"] = (
        "Against the untouched input the paired difference is "
        + "; ".join(keep_parts) + ", " + tail_keep
        + ", and against the best fixed intervention " + tail_fixed)'''

OLD_BACK = '''    if lost:
        names = " and ".join(BACKBONE_NAME[b] for b in lost)
        out["MAIN_BACKBONE"] = (
            f"Per backbone, against the untouched input and the best fixed intervention, the "
            f"numbers are {detail}. It is the lowest deployable row on "
            + " and ".join(BACKBONE_NAME[b] for b in won)
            + f", and on {names} one fixed repair reaches a lower macro average; "
              f"\\\\S\\\\ref{{sec:exp-robust}} returns to when that happens")
    else:
        out["MAIN_BACKBONE"] = (
            f"Per backbone, against the untouched input and the best fixed intervention, the "
            f"numbers are {detail}, so it is the lowest deployable row everywhere")'''
NEW_BACK = '''    if lost:
        out["MAIN_BACKBONE"] = (
            "It is the lowest deployable row on "
            + " and ".join(BACKBONE_NAME[b] for b in won) + ", and on "
            + " and ".join(BACKBONE_NAME[b] for b in lost)
            + " one fixed repair reaches a lower macro average, which \\\\S\\\\ref{sec:exp-robust}"
              " returns to")
    else:
        out["MAIN_BACKBONE"] = "It is the lowest deployable row on every backbone"'''

OLD_R2 = '''        out["MAIN_R2CART"] = ("Against the simple selector the paired difference is "
                              + "; ".join(parts) + ", " + tail)'''
NEW_R2 = '''        out["MAIN_R2CART"] = "Against the simple selector " + tail'''

OLD_SPREAD = '''    out["MAIN_BASELINE_SPREAD"] = (
        f"The deployable rows span {lo[1]:.3f} to {hi[1]:.3f} and the catalog oracle sits at "
        f"{oracle:.3f}, so the room a per-request decision can recover is bounded and the "
        f"differences between rows are a visible part of it")'''
NEW_SPREAD = '''    out["MAIN_BASELINE_SPREAD"] = (
        f"The deployable rows span {lo[1]:.3f} to {hi[1]:.3f} and the catalog oracle sits at "
        f"{oracle:.3f}, so the room to recover is bounded and the gaps between rows are a "
        f"visible part of it")'''

OLD_TRANSFER_TAIL = '''            f"requests while leaving "
            f"{rows_ch2['FULL_INTROACT']['missed_opportunity'] * 100:.0f}{PCT} of the episodes "
            f"that had a positive opportunity untouched. So the frozen procedure carries over in "
            f"the sense that it still beats leaving the input alone and still wins more cells "
            f"than any other deployable row, and not in the sense that it beats every fixed "
            f"policy on every backbone")'''
NEW_TRANSFER_TAIL = '''            f"requests while leaving "
            f"{rows_ch2['FULL_INTROACT']['missed_opportunity'] * 100:.0f}{PCT} of the "
            f"positive-opportunity episodes untouched. The frozen procedure carries over in the "
            f"sense that it still beats leaving the input alone and wins more cells than any "
            f"other deployable row, and not in the sense that it beats every fixed policy "
            f"everywhere")'''


def main() -> None:
    fill = io.open(PATH, encoding="utf-8").read()
    assert OLD_CI in fill, "ci"
    io.open(PATH, "w", encoding="utf-8").write(fill.replace(OLD_CI, NEW_CI))

    text = io.open(READING, encoding="utf-8").read()
    for old, new in ((OLD_BACK, NEW_BACK), (OLD_R2, NEW_R2), (OLD_SPREAD, NEW_SPREAD),
                     (OLD_TRANSFER_TAIL, NEW_TRANSFER_TAIL)):
        assert old in text, old[:50]
        text = text.replace(old, new)
    io.open(READING, "w", encoding="utf-8").write(text)
    print("readings tightened")


if __name__ == "__main__":
    main()
