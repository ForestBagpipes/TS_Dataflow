"""More room on the ninth page.

Two definitional passages repeat what the table captions already say, and the
scope caveat in the robustness subsection is stated again in the scope section
and in the appendix.
"""
import io

TEX = "latex/IntroActTS_20260919_v46.tex"
READING = "latex/fill_v46_reading.py"

OLD_HARM = r"""Table~\ref{tab:harm} reports the selective-governance diagnostics at the default operating
point. An intervention is harmful when it increases the realised loss relative to leaving the
input unchanged, so the conditional harmful rate is conditioned on the requests where an
intervention was executed and must be read together with the intervention rate, because a
method that intervenes on almost nothing can report a low conditional rate without
contributing anything. Beneficial precision is the share of executed interventions that reduced
the loss, and missed opportunity is the share of episodes with a positive oracle opportunity on
which nothing was executed."""

NEW_HARM = r"""Table~\ref{tab:harm} reports the selective-governance diagnostics at the default operating
point, where an intervention counts as harmful when it raises the realised loss relative to
leaving the input unchanged. The conditional harmful rate covers only the requests on which an
intervention ran, so it has to be read together with the intervention rate: a method that
almost never intervenes can report a low rate without contributing anything."""

OLD_ROBUST = r"""backbones, and no method is retuned between levels. The levels lie inside the registered grid
that the replay bank samples from, so this is a within-grid robustness check and not an
unseen-severity stress test, and the roster is the one of Table~\ref{tab:main}."""

NEW_ROBUST = r"""backbones, with the roster of Table~\ref{tab:main} and no retuning between levels. The levels
lie inside the registered grid the replay bank samples from, so this is a within-grid check."""

OLD_RANK = '''        for b in behind:
            name, value = min(per_rank[b].items(), key=lambda kv: kv[1])
            sentence += (f". On {BACKBONE_NAME[b]} {DISPLAY.get(name, name)} ranks "
                         f"{value:.2f} against our {per_rank[b]['FULL_INTROACT']:.2f}")'''

NEW_RANK = '''        for b in behind:
            name, value = min(per_rank[b].items(), key=lambda kv: kv[1])
            sentence += (f", against {value:.2f} for {DISPLAY.get(name, name)} on "
                         f"{BACKBONE_NAME[b]}")'''


def main() -> None:
    text = io.open(TEX, encoding="utf-8").read()
    assert OLD_HARM in text, "harm paragraph"
    assert OLD_ROBUST in text, "robust paragraph"
    text = text.replace(OLD_HARM, NEW_HARM, 1)
    text = text.replace(OLD_ROBUST, NEW_ROBUST, 1)
    io.open(TEX, "w", encoding="utf-8").write(text)

    code = io.open(READING, encoding="utf-8").read()
    assert OLD_RANK in code, "rank behind branch"
    io.open(READING, "w", encoding="utf-8").write(code.replace(OLD_RANK, NEW_RANK, 1))
    print("harm, robustness and rank passages tightened")


if __name__ == "__main__":
    main()
