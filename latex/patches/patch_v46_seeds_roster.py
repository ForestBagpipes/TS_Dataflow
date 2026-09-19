"""The stability appendix named three methods and then showed one.

The table carries the method against the untouched input, so the sentence now
says that, and the simple selector enters as its spread over the same three
realisations rather than as a row that is not there.
"""
import io

TEX = "latex/IntroActTS_20260919_v46.tex"
STRATA = "latex/fill_v46_strata.py"

OLD_TEX = r"""The subset is fixed before the run: all eight sources, patterns P1 to P4, $10\%$ severity,
$H=96$, on Bolt and Chronos-2, and the comparison is restricted to \textsc{Keep}, R2-CART,
and \introact{}. Reporting the spread over three realisations is a stability diagnostic and
is not an additional estimate of variance."""

NEW_TEX = r"""The subset is fixed before the run: all eight sources, patterns P1 to P4, $10\%$ severity,
$H=96$, on Bolt and Chronos-2. Table~\ref{tab:app-seeds} carries \introact{} against
\textsc{Keep} on each realisation. The simple selector moves by \ph{SEED_SPREAD_CART_BOLT} on
Bolt and \ph{SEED_SPREAD_CART_CH2} on the held-out backbone over the same three realisations,
so neither method is carried by one deletion pattern. Reporting the spread over three
realisations is a stability diagnostic and is not an additional estimate of variance."""

OLD_PY = '''        if len(mases) >= 2:
            out[f"SEED_SPREAD_{tag}"] = num(max(mases) - min(mases))
            out[f"SEED_IR_SPREAD_{tag}"] = pct(max(rates) - min(rates))'''

NEW_PY = '''        if len(mases) >= 2:
            out[f"SEED_SPREAD_{tag}"] = num(max(mases) - min(mases))
            out[f"SEED_IR_SPREAD_{tag}"] = pct(max(rates) - min(rates))
        # The rival on the same realisations, so the stability claim covers the
        # comparison rather than one row of it.
        rival = []
        for block in blocks:
            path = ROOT / f"results/v46/evaluation/{block}_{backbone}.json"
            if not path.exists():
                continue
            row = json.loads(path.read_text())["rows"].get("R2_CART")
            if row and row.get("mase") is not None:
                rival.append(row["mase"])
        if len(rival) >= 2:
            out[f"SEED_SPREAD_CART_{tag}"] = num(max(rival) - min(rival))'''


def main() -> None:
    text = io.open(TEX, encoding="utf-8").read()
    assert OLD_TEX in text, "seeds paragraph"
    io.open(TEX, "w", encoding="utf-8").write(text.replace(OLD_TEX, NEW_TEX, 1))

    code = io.open(STRATA, encoding="utf-8").read()
    assert OLD_PY in code, "strata spread block"
    io.open(STRATA, "w", encoding="utf-8").write(code.replace(OLD_PY, NEW_PY, 1))
    print("stability appendix now matches its table")


if __name__ == "__main__":
    main()
