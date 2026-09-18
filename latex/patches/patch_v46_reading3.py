"""Rewrite the main-comparison sentences so they state the result as it is.

The method has the lowest macro MASE on two of the three backbones and the best
average rank on all three.  The earlier wording implied a uniform win, which is
not what the table says.
"""
import io

PATH = "latex/fill_v46_reading.py"

OLD = '''    out["MAIN_READING"] = (
        f"{INTRO} reaches {ours:.3f} source-macro MASE, against {keep:.3f} for the untouched "
        f"input, {fixed:.3f} for the best fixed intervention and {cart:.3f} for the simple "
        f"selector")
    per_backbone = ", ".join(
        f"{BACKBONE_NAME[b]} {evals[b]['rows']['FULL_INTROACT']['mase']:.3f} against "
        f"{evals[b]['rows']['NATIVE_KEEP']['mase']:.3f}"
        for b in ("bolt", "timesfm", "chronos2") if b in evals)
    out["MAIN_BACKBONE"] = f"The same ordering holds on each backbone: {per_backbone}"
'''

NEW = '''    seq = [b for b in ("bolt", "timesfm", "chronos2") if b in evals]
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
            f"numbers are {detail}, so it is the lowest deployable row everywhere")
'''


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert OLD in text, "main reading block"
    io.open(PATH, "w", encoding="utf-8").write(text.replace(OLD, NEW))
    print("main reading rewritten")


if __name__ == "__main__":
    main()
