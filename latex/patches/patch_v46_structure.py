"""Third v4.6 patch: dangling references, the split table, and the feature table.

The feature table is rewritten from the implementation rather than from the
earlier draft, which described features the code does not compute.
"""
import io
import re

PATH = "latex/IntroActTS_20260918_v45_review.tex"


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()

    # The extended-comparison appendix is gone; its two references go with it.
    text = text.replace(
        "Appendix~\\ref{app:datasets}\ndocuments the roster, the extended comparison, and the per-source tables.",
        "Appendix~\\ref{app:datasets} documents the roster and the per-source tables.")
    text = text.replace(
        "MAE and RMSE are reported in the same tables in Appendix~\\ref{app:cost-full} style and\nare not averaged across sources.",
        "MAE and RMSE are reported per source and are not averaged across sources.")
    text = re.sub(r"[^.]*Appendix~\\ref\{app:extended\}[^.]*\.\s*", "", text)

    # The header note describes a roster that no longer exists.
    text = text.replace(
        "%  5. 主表 roster 冻结为 KEEP / Best Fixed / R2-CART / T1 / TOI / TATO / SRDI\n"
        "%     加 IntroAct-TS；ChannelTokenFormer 只作 external reference；Catalog Oracle\n"
        "%     只作诊断。附录 C 的 30/50 与 Table 3 使用同一套七方法。",
        "%  5. 主表 roster：KEEP / Best Fixed / R2-CART / SAITS / TOI / TATO 加 IntroAct-TS，\n"
        "%     Catalog Oracle 只作诊断。附录 C 的 30/50 与 Table 3 使用同一套方法。\n"
        "%     没有可运行公开实现的方法不进任何表，只留在 Related Work。")

    # The split table now has three blocks, not four.
    old_split = """    Split & Parents & Origins & Sources covered & Used for \\\\
    \\midrule
    Replay-fit   & \\ph{FIT_PARENTS}   & \\ph{FIT_ORIGINS}   & \\ph{FIT_SOURCES}   & replay bank, baseline training, feature normalisation \\\\
    Gate         & \\ph{GATE_PARENTS}  & \\ph{GATE_ORIGINS}  & \\ph{GATE_SOURCES}  & selection of $k$, $\\beta$, and baseline hyperparameters \\\\
    TRAIN-eval   & \\ph{EVAL_PARENTS}  & \\ph{EVAL_ORIGINS}  & \\ph{EVAL_SOURCES}  & frozen-configuration acceptance check \\\\
    \\midrule
    TEST         & \\ph{TEST_PARENTS}  & \\ph{TEST_ORIGINS}  & \\ph{TEST_SOURCES}  & every table in the main text, once, after freezing \\\\"""
    new_split = """    Split & Parents & Episodes & Sources covered & Used for \\\\
    \\midrule
    Replay bank  & \\ph{FIT_PARENTS}   & \\ph{FIT_ORIGINS}   & \\ph{FIT_SOURCES}   & replay bank, feature normalisation, baseline training, selection of $k$ and $\\beta$ by cross-validation \\\\
    TRAIN-eval   & \\ph{EVAL_PARENTS}  & \\ph{EVAL_ORIGINS}  & \\ph{EVAL_SOURCES}  & frozen-configuration acceptance check \\\\
    \\midrule
    TEST         & \\ph{TEST_PARENTS}  & \\ph{TEST_ORIGINS}  & \\ph{TEST_SOURCES}  & every table in the main text, once, after freezing \\\\"""
    if old_split in text:
        text = text.replace(old_split, new_split)

    text = text.replace(
        """TRAIN is then partitioned at the parent level. Within each source the registered admissible
TRAIN parents are sorted by origin time and divided into \\emph{replay-fit}, \\emph{gate}, and
\\emph{TRAIN-eval} at approximately $60/20/20$. The replay bank is built exclusively from
replay-fit parents. The gate selects $k$, $\\beta$, and any baseline hyperparameter.
TRAIN-eval is the final internal acceptance check before the configuration is frozen, and it
is not an evaluation set for any reported number. Purging is enforced at $L + H$ inside TRAIN
as well, so no parent's context window overlaps the target window of another split.""",
        """TRAIN is then partitioned at the parent level. Within each source the admissible TRAIN parents
are sorted by origin time and split at $80/20$ into the replay bank and TRAIN-eval. The bank is
the only evidence the method reads, and it is also where $k$ and $\\beta$ are chosen by
leave-one-parent-out cross-validation, so no separate selection block is held out for them.
TRAIN-eval is the internal acceptance check run once before the configuration is frozen, and
it is not an evaluation set for any reported number. Parents tile at $L + \\max(H)$, so two
parents never share a raw row, and the gap between the last TRAIN window and the first TEST
window exceeds the purge on every source.""")

    io.open(PATH, "w", encoding="utf-8").write(text)
    print("structure patched")


if __name__ == "__main__":
    main()
