"""Per-backbone bank-size anchors, so the appendix sentence cannot drift again.

The averaged RS keys hide the direction, because one backbone improving and
another flattening average into a line that moves very little.
"""
import io

PATH = "latex/fill_v46_extra.py"

ANCHOR = '''    # The severity reading, written from the sweep itself.'''

BLOCK = '''    # Per-backbone bank-size anchors.  The averaged rows above hide the
    # direction, and the appendix sentence is about the direction.
    for backbone, tag in (("bolt", "BOLT"), ("timesfm", "TF"), ("chronos2", "CH2")):
        path = ROOT / f"results/v46/ablations/banksize_test_{backbone}.json"
        if not path.exists():
            continue
        rows = sorted(json.loads(path.read_text())["rows"], key=lambda r: r["fraction"])
        values = [r["mase"] for r in rows if r.get("mase") is not None]
        if not values:
            continue
        out[f"BANK_Q_{tag}"] = num(values[0])
        out[f"BANK_F_{tag}"] = num(values[-1])
        out[f"BANK_SPREAD_{tag}"] = num(max(values) - min(values), 3)

    # The severity reading, written from the sweep itself.'''


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert ANCHOR in text, "anchor"
    text = text.replace(ANCHOR, BLOCK, 1)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("per-backbone bank-size anchors added")


if __name__ == "__main__":
    main()
