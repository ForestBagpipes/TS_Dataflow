"""The severity sentence claimed more than the sweep shows.

It only checked whether a rival passes us, and when none does it asserted that
the ordering of every deployable row is unchanged.  The rows below us do change
order between levels, so the sentence now says what it checked.
"""
import io

PATH = "latex/fill_v46_extra.py"

OLD = '''        else:
            out["ROBUST_30"] = "The ordering between the deployable rows is unchanged by severity"
            out["ROBUST_50"] = (
                "The configuration is frozen on a bank that mixes the three levels and is not "
                "retuned per level")'''

NEW = '''        else:
            # We lead at every level.  Whether the rows below keep their order is
            # a separate question, and the answer does not have to be yes.
            orders = []
            for level in levels:
                values = {k: row(level, k) for k in ("KEEP", "BF", "R2", "SAITS", "TATO")
                          if row(level, k) is not None}
                orders.append(tuple(sorted(values, key=values.get)))
            stable = len(set(orders)) == 1
            out["ROBUST_30"] = (
                "The method holds the lowest macro average at every level"
                + (", and the rows below it hold their order too" if stable else
                   ", and the rows below it change order between levels, so the sweep separates "
                   "the method from the roster rather than reproducing one ranking"))
            out["ROBUST_50"] = (
                "The configuration is frozen on a bank that mixes the three levels and is not "
                "retuned per level")'''


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert OLD in text, "ordering branch"
    io.open(PATH, "w", encoding="utf-8").write(text.replace(OLD, NEW, 1))
    print("severity ordering claim now matches what is checked")


if __name__ == "__main__":
    main()
