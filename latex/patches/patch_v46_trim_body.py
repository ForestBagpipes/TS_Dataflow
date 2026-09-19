"""Three tighter sentences so the conclusion stays on the ninth page.

Nothing is dropped, only said in fewer words.
"""
import io

PATH = "latex/fill_v46_reading.py"

PAIRS = [
    ('''        "Two parts of the design carry the result, and the state blocks matter less than either. "
        "Each interval below is the paired difference on the primary backbone, while the table "
        "columns average over the three")''',
     '''        "Two parts of the design carry the result, and the state blocks matter less than either. "
        "Intervals are paired differences on the primary backbone and table columns average "
        "over the three")'''),
    ('''            f"Dropping the reference-forecast block changes it by {ci(a['A3_WO_FORECAST'])}. "
            f"Averaged over the three backbones the first ablation lands at "
            f"{m('A2_WO_INTERVENTION'):.3f} and the second at {m('A3_WO_FORECAST'):.3f} against "
            f"{ours:.3f} for the full method, so the reference-forecast block is the one that "
            f"shows up in the average")''',
     '''            f"Dropping the reference-forecast block changes it by {ci(a['A3_WO_FORECAST'])}, "
            f"and over the three backbones the two land at {m('A2_WO_INTERVENTION'):.3f} and "
            f"{m('A3_WO_FORECAST'):.3f} against {ours:.3f}, so only the second block shows up "
            f"in the average")'''),
    ('''                + ", so that one loses broadly rather than on a few cells")''',
     '''                + ", so that one loses broadly")'''),
]


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    for index, (old, new) in enumerate(PAIRS):
        assert old in text, f"pair {index}"
        text = text.replace(old, new, 1)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("body sentences trimmed")


if __name__ == "__main__":
    main()
