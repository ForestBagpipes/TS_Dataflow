"""Second v4.6 patch: appendix rosters, the severity text, and the removed tables."""
import io
import re

PATH = "latex/IntroActTS_20260918_v45_review.tex"


def cut_block(text: str, start_marker: str, end_marker: str) -> str:
    i = text.find(start_marker)
    if i < 0:
        return text
    j = text.find(end_marker, i)
    if j < 0:
        return text
    return text[:i] + text[j + len(end_marker):]


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()

    # The cost table still carries the old reconstruction key prefix.
    text = text.replace("\\ph{T1_", "\\ph{SAITS_")

    # Section 4.5 no longer runs a reduced roster and no longer owns a held-out column.
    old = ("which omits SRDI so that the high-severity runs stay bounded, and the "
           "full core set is\ncompared at $10\\%$ in Table~\\ref{tab:main}. "
           "Table~\\ref{tab:robust} reports the severity trend,\nthe worst pattern "
           "cell, and the held-out Chronos-2 backbone under an unchanged configuration.")
    new = ("and the roster is the one of Table~\\ref{tab:main}.\n"
           "Table~\\ref{tab:robust} reports the severity trend and the worst pattern cell, and "
           "the\nheld-out backbone is the Chronos-2 column of Table~\\ref{tab:main}.")
    if old in text:
        text = text.replace(old, new)
    text = text.replace("The sweep uses a reduced but type-complete set of seven methods,\n", "")

    # The extended comparison held only methods without a runnable implementation.
    text = cut_block(text, "\\subsubsection{Extended Comparison}",
                     "\\subsubsection{Per-Pattern Results}")
    if "\\subsubsection{Per-Pattern Results}" not in text:
        text = text.replace("\\label{app:pattern}", "\\subsubsection{Per-Pattern Results}\n\\label{app:pattern}", 1)

    # Appendix references to baselines that no longer appear in any table.
    text = text.replace(
        "because the replay bank already samples from the same three levels. SRDI is the one published",
        "because the replay bank already samples from the same three levels. The one published")
    text = text.replace(
        "external reference ChannelTokenFormer are not placed on a common reconstruction scale. The",
        "and a transformation pipeline are not placed on a common reconstruction scale. The")

    # Reconstruction diagnostics: only the methods that emit a reconstruction stay.
    text = text.replace("\\ph{REC_T1_", "\\ph{REC_SAITS_")
    out = []
    for line in text.split("\n"):
        st = line.strip()
        if st.startswith("SRDI") and "\\ph{REC_SRDI" in line:
            continue
        out.append(line)
    text = "\n".join(out)
    text = text.replace(
        "    T1                 & \\ph{REC_SAITS_MSE}",
        "    SAITS              & \\ph{REC_SAITS_MSE}")
    text = re.sub(r"\\multirow\{3\}\{\*\}\{\\ph\{DISCORDANT_RATE\}\}",
                  "\\\\multirow{2}{*}{\\\\ph{DISCORDANT_RATE}}", text)

    io.open(PATH, "w", encoding="utf-8").write(text)
    print("appendix patched")


if __name__ == "__main__":
    main()
