"""Five semicolons that the earlier pass missed, because they sit in table cells
and in captions rather than in body paragraphs.
"""
import io

PAIRS_TEX = [
    ("""  request and equals one plus the intervention rate; candidate materialisation is reported
  separately in Appendix~\\ref{app:calls}.}""",
     """  request and equals one plus the intervention rate. Candidate materialisation is reported
  separately in Appendix~\\ref{app:calls}.}"""),
    ("""so the adapter fills them by linear interpolation before the pipeline runs; that bridging
step is part of what the row measures""",
     """so the adapter fills them by linear interpolation before the pipeline runs, and that
bridging step is part of what the row measures"""),
    ("""    Offline selector fit (amortised)           & --- & --- & no fit; the selector stores the bank and retrieves \\\\""",
     """    Offline selector fit (amortised)           & --- & --- & no fit, the selector stores the bank and retrieves \\\\"""),
]

PAIRS_PY = [
    ('"101; the selector has no fitted parameters"',
     '"101, and the selector has no fitted parameters"'),
    ('"recorded with the run; see the released artefact ledger"',
     '"recorded with the run, in the released artefact ledger"'),
]


def main() -> None:
    path = "latex/IntroActTS_20260919_v46.tex"
    text = io.open(path, encoding="utf-8").read()
    for old, new in PAIRS_TEX:
        if old in text:
            text = text.replace(old, new, 1)
        else:
            print("  missed in tex:", " ".join(old.split())[:60])
    io.open(path, "w", encoding="utf-8").write(text)

    path = "latex/fill_v46_env.py"
    text = io.open(path, encoding="utf-8").read()
    for old, new in PAIRS_PY:
        if old in text:
            text = text.replace(old, new, 1)
        else:
            print("  missed in env:", old[:60])
    io.open(path, "w", encoding="utf-8").write(text)
    print("semicolons removed from the table cells and captions")


if __name__ == "__main__":
    main()
