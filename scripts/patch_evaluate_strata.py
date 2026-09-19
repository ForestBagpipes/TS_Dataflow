"""Add the opportunity strata to the evaluation record.

Section 4.2 defers the stratum-level breakdown to the appendix, so the record
has to carry it.  An episode's oracle opportunity is how much the best
admissible action could have improved on the reference input.  The two stratum
boundaries are quantiles of that quantity on the replay bank, computed once and
applied unchanged, so no evaluation episode takes part in choosing them.
"""
import io

PATH = "scripts/v46_evaluate.py"

OLD = '''def missed_opportunity(queries: SEL.Queries, selected: np.ndarray,
                       threshold: float) -> float:'''

NEW = '''def opportunity_strata(bank_queries: SEL.Queries, queries: SEL.Queries,
                       rows: dict, mase_of: dict,
                       quantiles=(0.50, 0.85)) -> dict:
    """Stratum sizes and per-stratum MASE, under boundaries fixed on the bank."""
    def opportunity(q: SEL.Queries) -> np.ndarray:
        keep = SEL.realised(q, np.full(len(q.episode), SEL.REFERENCE, dtype=object))
        best = SEL.realised(q, SEL.oracle(q))
        return keep - best

    bank_gap = opportunity(bank_queries)
    usable = bank_gap[np.isfinite(bank_gap)]
    positive = usable[usable > 1e-9]
    if positive.size < 10:
        return {}
    low, high = (float(np.quantile(positive, quantiles[0])),
                 float(np.quantile(positive, quantiles[1])))

    gap = opportunity(queries)
    strata = np.full(len(gap), "no-op", dtype=object)
    strata[np.isfinite(gap) & (gap > 1e-9) & (gap <= low)] = "low"
    strata[np.isfinite(gap) & (gap > low)] = "high"
    strata[np.isfinite(gap) & (gap > high)] = "high"

    out = {"boundaries": {"no_op": 1e-9, "low_to_high": low, "upper_reference": high,
                          "quantiles": list(quantiles), "fitted_on": "replay bank"},
           "sizes": {}, "per_method": {}}
    for name in ("no-op", "low", "high"):
        mask = strata == name
        values = gap[mask & np.isfinite(gap)]
        out["sizes"][name] = {
            "episodes": int(mask.sum()),
            "share": float(mask.mean()),
            "parents": int(len({queries.parent[i] for i in np.flatnonzero(mask)})),
            "median": float(np.median(values)) if values.size else None,
            "p90": float(np.percentile(values, 90)) if values.size else None,
        }
    for method, vector in mase_of.items():
        row = {}
        for name in ("no-op", "low", "high"):
            mask = (strata == name) & np.isfinite(vector)
            if not mask.any():
                row[name] = None
                continue
            sub = SEL.Queries.__new__(SEL.Queries)
            sub.episode = queries.episode[mask]
            sub.parent = queries.parent[mask]
            sub.source = queries.source[mask]
            sub.horizon = queries.horizon[mask]
            sub.severity = queries.severity[mask]
            sub.pattern = queries.pattern[mask]
            row[name] = SEL.source_macro(sub, vector[mask])
        row["overall"] = SEL.source_macro(queries, vector)
        out["per_method"][method] = row
    return out


def missed_opportunity(queries: SEL.Queries, selected: np.ndarray,
                       threshold: float) -> float:'''

OLD_PAY = '''        "heterogeneity": heterogeneity(queries),'''
NEW_PAY = '''        "heterogeneity": heterogeneity(queries),
        "opportunity_strata": opportunity_strata(
            SEL.Queries(bank_catalogs, blocks=full_blocks), queries, rows, mase_of),'''


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert OLD in text, "missed_opportunity anchor"
    text = text.replace(OLD, NEW, 1)
    assert OLD_PAY in text, "payload anchor"
    text = text.replace(OLD_PAY, NEW_PAY)
    io.open(PATH, "w", encoding="utf-8").write(text)
    import ast
    ast.parse(text)
    print("opportunity strata added")


if __name__ == "__main__":
    main()
