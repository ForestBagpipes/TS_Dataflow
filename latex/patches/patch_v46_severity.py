"""Generate the severity reading from the sweep instead of asserting robustness.

At the main severity the per-request rule wins; as the context empties the
simple selector catches up.  The section should say so.
"""
import io

PATH = "latex/fill_v46_extra.py"

ANCHOR = "    return out\n"

BLOCK = '''    # The severity reading, written from the sweep itself.
    levels = [lv for lv in ("10", "30", "50") if lv in severity]
    if len(levels) >= 2:
        def row(level, key):
            values = severity[level].get(key)
            return sum(values) / len(values) if values else None

        parts = []
        for level in levels:
            keep, ours = row(level, "KEEP"), row(level, "OURS")
            if keep is not None and ours is not None:
                parts.append(f"{level}\\\\% {ours:.3f} against {keep:.3f}")
        out["ROBUST_READING"] = (
            "Against the untouched input the frozen configuration holds at every level: "
            + ", ".join(parts))
        beaten = []
        for level in levels:
            ours = row(level, "OURS")
            rivals = {k: row(level, k) for k in ("BF", "R2") if row(level, k) is not None}
            better = [k for k, v in rivals.items() if v < ours]
            if better:
                beaten.append((level, better, min(rivals.values())))
        name = {"BF": "the best fixed intervention", "R2": "the simple selector"}
        if beaten:
            worst = ", ".join(
                f"at {lv}\\\\% {' and '.join(name[b] for b in bs)} reaches {v:.3f}"
                for lv, bs, v in beaten)
            out["ROBUST_30"] = (
                "The ordering between the deployable rows does change with severity: " + worst)
            out["ROBUST_50"] = (
                "The configuration was frozen on a bank that mixes the three levels and is not "
                "retuned per level, so what the sweep shows is how far one frozen operating point "
                "carries, not how well the method could do at a severity it was tuned for")
        else:
            out["ROBUST_30"] = "The ordering between the deployable rows is unchanged by severity"
            out["ROBUST_50"] = (
                "The configuration is frozen on a bank that mixes the three levels and is not "
                "retuned per level")
    return out
'''


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    i = text.rfind(ANCHOR)
    assert i > 0, "anchor"
    text = text[:i] + BLOCK + text[i + len(ANCHOR):]
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("severity reading added")


if __name__ == "__main__":
    main()
