"""Bring the v4.6 table rosters in line with the baselines that actually ran.

T1 has no public implementation that admits this protocol, so the
reconstruction row becomes SAITS.  SRDI, GIMCC, VIDA and ChannelTokenFormer
have no runnable implementation here and their rows are removed rather than
filled with an estimate.  Table 3 also loses the held-out backbone column,
which Table 1 already carries at a single severity.
"""
import io
import re
import sys

PATH = "latex/IntroActTS_20260918_v45_review.tex"
BACK = "\\" + "\\"


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    lines = text.split("\n")
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("SRDI ") and ("HARM_" in line or "RB_SRDI" in line):
            continue
        if stripped.startswith("T1 ") and ("HARM_" in line or "RB_T1" in line):
            line = line.replace("T1                 &", "SAITS              &", 1)
            line = line.replace("_T1}", "_SAITS}")
        if "RB_" in line and "_CH2}" in line:
            line = re.sub(r"\s*&\s*\\ph\{RB_[A-Z0-9]+_CH2\}", "", line)
        out.append(line)
    text = "\n".join(out)

    header_old = ("    Method & 10\\% MASE $\\downarrow$ & 30\\% MASE $\\downarrow$ & "
                  "50\\% MASE $\\downarrow$ & Worst pattern $\\downarrow$ & "
                  "Chronos-2 MASE $\\downarrow$ " + BACK)
    header_new = ("    Method & 10\\% MASE $\\downarrow$ & 30\\% MASE $\\downarrow$ & "
                  "50\\% MASE $\\downarrow$ & Worst pattern $\\downarrow$ " + BACK)
    assert header_old in text, "severity header"
    text = text.replace(header_old, header_new)

    spec_old = ("\\resizebox{\\textwidth}{!}{\\begin{tabular}{lccccc}\n    \\toprule\n"
                "    Method & 10\\% MASE")
    spec_new = ("\\resizebox{\\textwidth}{!}{\\begin{tabular}{lcccc}\n    \\toprule\n"
                "    Method & 10\\% MASE")
    assert spec_old in text, "severity column spec"
    text = text.replace(spec_old, spec_new)

    foot_old = """  {\\footnotesize Only methods that share the frozen-backbone reference contract appear here,
  because the harmful rate of an intervention is defined against the reference forecast of the
  same backbone. ChannelTokenFormer has no such reference and is therefore reported in
  Table~\\ref{tab:main} only. Methods that always return a repaired input intervene on every
  incomplete request by construction, so their intervention rate is one and their harmful rate
  is unconditional.}"""
    foot_new = """  {\\footnotesize A method that always returns a repaired input intervenes on every incomplete
  request by construction, so its intervention rate is one and its conditional harmful rate is
  unconditional. \\textsc{Context Ridge} is not admissible on the shared-block pattern, so a
  fixed policy that selects it intervenes on fewer than all requests.}"""
    assert foot_old in text, "harm footnote"
    text = text.replace(foot_old, foot_new)

    cap_old = """  \\caption{Within-grid robustness to missingness severity, with no method retuned between
  levels. The seven rows cover every control type, and the same set is used at all three
  severities and in Appendix~\\ref{app:severity-full}. The worst-pattern column is the largest
  degradation relative to \\textsc{Native Keep} over all pattern and backbone cells at that
  severity. The Chronos-2 column is the held-out backbone under an unchanged configuration.}"""
    cap_new = """  \\caption{Within-grid robustness to missingness severity, with no method retuned between
  levels. The rows are the roster of Table~\\ref{tab:main} and cover every control type. Values
  are source-macro MASE averaged over the backbones, both horizons and the four patterns. The
  worst-pattern column is the largest degradation relative to \\textsc{Native Keep} over all
  pattern and backbone cells at that severity.}"""
    assert cap_old in text, "severity caption"
    text = text.replace(cap_old, cap_new)

    io.open(PATH, "w", encoding="utf-8").write(text)
    print("tables patched")


if __name__ == "__main__":
    sys.exit(main())
