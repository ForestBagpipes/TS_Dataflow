"""The rank sentence has to survive the case where one backbone goes the other way.

The old alternative branch printed our rank and then the best rank on each
backbone without saying which row held it, which reads as an evasion when the
row is a baseline.  It now names where the method leads, names what leads where
it does not, and gives the mean over the three backbones.
"""
import io

PATH = "latex/fill_v46_reading.py"

OLD = '''    else:
        out["MAIN_RANK"] = (
            f"Average rank over the evaluation cells is {rank_parts}, against "
            + ", ".join(f"{BACKBONE_NAME[b]} {min(per_rank[b].values()):.2f}" for b in order)
            + " for the best deployable row on each")'''

NEW = '''    else:
        lead = [b for b in order if per_rank[b]
                and min(per_rank[b].items(), key=lambda kv: kv[1])[0] == "FULL_INTROACT"]
        behind = [b for b in order if b not in lead and per_rank[b]]
        mean_rank = {name: sum(per_rank[b][name] for b in order) / len(order)
                     for name in deployable_rows
                     if all(name in per_rank[b] for b in order)}
        rival = min(((n, v) for n, v in mean_rank.items() if n != "FULL_INTROACT"),
                    key=lambda kv: kv[1], default=None)
        sentence = f"Average rank over the evaluation cells is {rank_parts}"
        if lead:
            sentence += (f", the best of the {count} deployable rows on "
                         + " and ".join(BACKBONE_NAME[b] for b in lead))
        for b in behind:
            name, value = min(per_rank[b].items(), key=lambda kv: kv[1])
            sentence += (f". On {BACKBONE_NAME[b]} {DISPLAY.get(name, name)} ranks "
                         f"{value:.2f} against our {per_rank[b]['FULL_INTROACT']:.2f}")
        if rival is not None and "FULL_INTROACT" in mean_rank:
            sentence += (f". Averaged over the three backbones the rank is "
                         f"{mean_rank['FULL_INTROACT']:.2f} against {rival[1]:.2f} for "
                         f"{DISPLAY.get(rival[0], rival[0])}, which is the closest "
                         f"deployable row")
        out["MAIN_RANK"] = sentence'''


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert OLD in text, "rank branch"
    text = text.replace(OLD, NEW, 1)
    io.open(PATH, "w", encoding="utf-8").write(text)
    print("rank reading branch rewritten")


if __name__ == "__main__":
    main()
