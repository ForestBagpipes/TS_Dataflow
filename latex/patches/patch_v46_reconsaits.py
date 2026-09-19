"""Put the published reconstruction baseline into the reconstruction comparison.

With five repairs instead of four, the chance level for picking the most useful
one by reconstruction accuracy is a fifth, and the measured agreement sits on
top of it.
"""
import io

PATH = "latex/IntroActTS_20260919_v46.tex"

OLD_ROW = ("    \\textsc{Context Ridge} & \\ph{REC_RIDGE_MSE}  & \\ph{REC_RIDGE_MAE}  & "
           "\\ph{REC_RIDGE_UTIL}  & \\ph{REC_RIDGE_N} " + "\\" * 2)
NEW_ROW = (OLD_ROW + "\n    SAITS                  & \\ph{REC_SAITS_MSE}  & "
           "\\ph{REC_SAITS_MAE}  & \\ph{REC_SAITS_UTIL}  & \\ph{REC_SAITS_N} " + "\\" * 2)

PAIRS = [
    ("""Reconstruction error is defined only where a
method emits an explicit estimate of the hidden positions, which the four interventions of the
catalog all do.""",
     """Reconstruction error is defined only where a
method emits an explicit estimate of the hidden positions, which the four catalog interventions
and the published reconstruction baseline all do."""),
    ("""  \\caption{Reconstruction quality against realised forecasting utility, over the four catalog
  interventions on the held-out evaluation episodes.""",
     """  \\caption{Reconstruction quality against realised forecasting utility, over the four catalog
  interventions and SAITS on the held-out evaluation episodes."""),
    ("""within-episode realised-utility rank over the four catalog interventions, row-normalised over""",
     """within-episode realised-utility rank over the four catalog interventions and SAITS,
  row-normalised over"""),
]


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert OLD_ROW in text, "ridge row"
    text = text.replace(OLD_ROW, NEW_ROW, 1)
    for old, new in PAIRS:
        if old in text:
            text = text.replace(old, new)
        else:
            print("  missed:", old[:50].replace("\n", " "))
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("SAITS added to the reconstruction comparison")


if __name__ == "__main__":
    main()
