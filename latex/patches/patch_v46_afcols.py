"""The full ablation table carried raw-error columns the metric convention
forbids averaging across sources; it now carries the two scaled metrics.
"""
import io
import re

PATH = "latex/IntroActTS_20260919_v46.tex"


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()

    old_head = ("    Variant & MASE $\\downarrow$ & MAE $\\downarrow$ & RMSE $\\downarrow$ & "
                "MSE $\\downarrow$ & Intervention rate & Conditional HIR $\\downarrow$ & "
                "Harmful loss $\\downarrow$ & Calls $\\downarrow$ \\\\")
    new_head = ("    Variant & MASE $\\downarrow$ & RMSSE $\\downarrow$ & Intervention rate & "
                "Conditional HIR $\\downarrow$ & Harmful loss $\\downarrow$ & Calls $\\downarrow$ \\\\")
    assert old_head in text, "ablation header"
    text = text.replace(old_head, new_head)

    def fix(match):
        tag = match.group(1)
        return (f"\\ph{{AF_{tag}_MASE}} & \\ph{{AF_{tag}_RMSSE}} & \\ph{{AF_{tag}_IR}} & "
                f"\\ph{{AF_{tag}_CHIR}} & \\ph{{AF_{tag}_HL}} & \\ph{{AF_{tag}_CALLS}}")

    text = re.sub(
        r"\\ph\{AF_([A-Z0-9]+)_MASE\} & \\ph\{AF_[A-Z0-9]+_MAE\} & \\ph\{AF_[A-Z0-9]+_RMSE\} & "
        r"\\ph\{AF_[A-Z0-9]+_MSE\} & \\ph\{AF_[A-Z0-9]+_IR\} & \\ph\{AF_[A-Z0-9]+_CHIR\} & "
        r"\\ph\{AF_[A-Z0-9]+_HL\} & \\ph\{AF_[A-Z0-9]+_CALLS\}", fix, text)

    text = text.replace(
        "\\resizebox{\\textwidth}{!}{\\begin{tabular}{lcccccccc}\n    \\toprule\n    Variant & MASE",
        "\\resizebox{\\textwidth}{!}{\\begin{tabular}{lcccccc}\n    \\toprule\n    Variant & MASE")
    text = text.replace(
        "  \\caption{Ablation, full outcome vector. Calls counts forecasting-backbone calls per request,\n  and harmful loss is measured relative to \\textsc{Keep}.}",
        "  \\caption{Ablation, full outcome vector in the two scaled metrics. Raw errors are not\n"
        "  averaged across sources anywhere in this paper, so they are not shown here either. Calls\n"
        "  counts forecasting-backbone calls per request and harmful loss is relative to\n"
        "  \\textsc{Keep}.}")
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("ablation table columns fixed")


if __name__ == "__main__":
    main()
