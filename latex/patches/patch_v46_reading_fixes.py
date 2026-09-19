"""Two repairs to the generated reading paragraphs.

The first is an escape that swallowed a reference: a plain Python string turns
the four characters of a LaTeX reference command into a carriage return, so the
sentence pointed at nothing.  The second is a claim that covered two baselines
with one explanation although they fail in opposite ways, one losing on a few
cells and the other losing on most of them.
"""
import io

PATH = "latex/fill_v46_reading.py"

OLD_REF = '''            tail = ("no interval excludes zero, so accuracy alone does not separate the two "
                    "and what does is in Table~\\ref{tab:harm}")'''
NEW_REF = '''            tail = ("no interval excludes zero, so accuracy alone does not separate the two "
                    "and what does is in Table~" + chr(92) + "ref{tab:harm}")'''

OLD_DETAIL = '''        if wins + losses:
            detail.append(f"{name} below it on {wins} of {wins + losses} "
                          f"source and backbone cells")
    if worse:
        out["MAIN_BASELINE_SPREAD"] += (
            ". Both published baselines repair or transform every incomplete request, and "
            + " and ".join(f"{name} ends at {published[name]:.3f}" for name in sorted(worse))
            + f", above the {keep:.3f} of leaving the input alone")
        if detail:
            out["MAIN_BASELINE_SPREAD"] += (
                ". The loss is concentrated rather than uniform, with " + ", ".join(detail)
                + ", so what costs a fixed repair its average is the minority of cells on which "
                  "it is badly wrong, and that is the failure a per-request rule can avoid")'''

NEW_DETAIL = '''        if wins + losses:
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
                + ", so what costs that repair its average is the minority of cells on which it "
                  "is badly wrong, and that is the failure a per-request rule can avoid")
        if broad:
            out["MAIN_BASELINE_SPREAD"] += (
                ". " + " and ".join(f"{name} is below it on only {wins} of {total} such cells"
                                    for name, wins, total in broad)
                + ", so that one loses broadly rather than on a few cells")'''


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert OLD_REF in text, "reference escape"
    assert OLD_DETAIL in text, "concentrated loss"
    text = text.replace(OLD_REF, NEW_REF, 1)
    text = text.replace(OLD_DETAIL, NEW_DETAIL, 1)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("reference escape and the concentrated-loss claim fixed")


if __name__ == "__main__":
    main()
