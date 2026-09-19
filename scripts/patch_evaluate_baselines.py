"""Let the evaluation carry published-baseline rows alongside the catalog rows.

A catalog method is described by the action it selected; a baseline is
described by the forecast it returned.  Both end up as a vector of realised
MASE aligned to the evaluation episodes, so ranks, paired intervals and the
harm diagnostics can be computed the same way for both.
"""
import io

PATH = "scripts/v46_evaluate.py"

OLD_IMPORT = '''DEPLOYABLE = ("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "FULL_INTROACT")'''
NEW_IMPORT = '''DEPLOYABLE = ("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "FULL_INTROACT")

#: Published baselines, by the directory their records live in.  A method that
#: returns a repaired input or a transformed context intervenes on every
#: incomplete request by construction.
BASELINES = {"saits": "SAITS", "tato": "TATO"}'''

OLD_SUM = '''def summarise(queries: SEL.Queries, selected: np.ndarray, name: str) -> dict:
    out = SEL.outcomes(queries, selected)
    row = {
        "method": name,
        "mase": SEL.source_macro(queries, out["mase"]),
        "rmsse": SEL.source_macro(queries, SEL.realised(queries, selected, "rmsse")),
        "intervention_rate": out["intervention_rate"],
        "conditional_hir": out["conditional_hir"],
        "harmful_loss": out["harmful_loss"],
        "beneficial_precision": out["beneficial_precision"],
        "n_acted": out["n_acted"],
        "n_zero_utility": out["n_zero_utility"],
        "per_source_mase": SEL.macro_by_source(queries, out["mase"]),
        "per_source_horizon_mase": per_source_horizon(queries, out["mase"]),
        "per_cell_mase": SEL.macro_by_cell(queries, out["mase"]),
        "action_counts": {a: int((selected == a).sum()) for a in SEL.ACTIONS},
    }
    return row'''

NEW_SUM = '''def load_baseline(root: Path, method: str, block: str, backbone: str,
                  queries: SEL.Queries) -> dict | None:
    """A baseline's realised MASE and RMSSE, aligned to the evaluation episodes."""
    path = root / f"results/v46/baselines/{method}_{block}_{backbone}/records.json"
    if not path.exists():
        return None
    records = json.loads(path.read_text())["records"]
    n = len(queries.episode)
    mase = np.full(n, np.nan)
    rmsse = np.full(n, np.nan)
    for i, episode in enumerate(queries.episode):
        item = records.get(episode)
        if item is None:
            continue
        if item.get("mase") is not None:
            mase[i] = item["mase"]
        if item.get("rmsse") is not None:
            rmsse[i] = item["rmsse"]
    if not np.isfinite(mase).any():
        return None
    return {"mase": mase, "rmsse": rmsse, "scored": int(np.isfinite(mase).sum())}


def summarise_vectors(queries: SEL.Queries, mase: np.ndarray, rmsse: np.ndarray,
                      name: str, *, keep_mase: np.ndarray) -> dict:
    """The same row a catalog method gets, for a method that returns a forecast.

    A baseline modifies the input of every incomplete request, so its
    intervention rate is one and its harmful rate is unconditional: it counts
    the requests where its forecast is worse than the reference forecast of the
    same backbone.
    """
    usable = np.isfinite(mase) & np.isfinite(keep_mase)
    harmful = usable & (mase > keep_mase)
    benefit = usable & (mase < keep_mase)
    n = int(usable.sum())
    return {
        "method": name,
        "mase": SEL.source_macro(queries, mase),
        "rmsse": SEL.source_macro(queries, rmsse),
        "intervention_rate": 1.0,
        "conditional_hir": (float(harmful.sum()) / n) if n else 0.0,
        "harmful_loss": (float((mase[harmful] - keep_mase[harmful]).sum()) / n) if n else 0.0,
        "beneficial_precision": (float(benefit.sum()) / n) if n else float("nan"),
        "n_acted": n,
        "n_zero_utility": int(usable.sum() - harmful.sum() - benefit.sum()),
        "per_source_mase": SEL.macro_by_source(queries, mase),
        "per_source_horizon_mase": per_source_horizon(queries, mase),
        "per_cell_mase": SEL.macro_by_cell(queries, mase),
        "action_counts": {},
    }


def summarise(queries: SEL.Queries, selected: np.ndarray, name: str) -> dict:
    out = SEL.outcomes(queries, selected)
    row = {
        "method": name,
        "mase": SEL.source_macro(queries, out["mase"]),
        "rmsse": SEL.source_macro(queries, SEL.realised(queries, selected, "rmsse")),
        "intervention_rate": out["intervention_rate"],
        "conditional_hir": out["conditional_hir"],
        "harmful_loss": out["harmful_loss"],
        "beneficial_precision": out["beneficial_precision"],
        "n_acted": out["n_acted"],
        "n_zero_utility": out["n_zero_utility"],
        "per_source_mase": SEL.macro_by_source(queries, out["mase"]),
        "per_source_horizon_mase": per_source_horizon(queries, out["mase"]),
        "per_cell_mase": SEL.macro_by_cell(queries, out["mase"]),
        "action_counts": {a: int((selected == a).sum()) for a in SEL.ACTIONS},
    }
    return row'''

OLD_ROWS = '''    rows = {name: summarise(queries, sel, name) for name, sel in decisions.items()}
    threshold = 1e-9
    for name, sel in decisions.items():
        rows[name]["missed_opportunity"] = missed_opportunity(queries, sel, threshold)

    mase_of = {name: SEL.realised(queries, sel) for name, sel in decisions.items()}'''

NEW_ROWS = '''    rows = {name: summarise(queries, sel, name) for name, sel in decisions.items()}
    threshold = 1e-9
    for name, sel in decisions.items():
        rows[name]["missed_opportunity"] = missed_opportunity(queries, sel, threshold)

    mase_of = {name: SEL.realised(queries, sel) for name, sel in decisions.items()}

    # Published baselines enter as realised forecasts rather than as a choice
    # over the catalog, and are ranked and tested exactly like the other rows.
    keep_mase = mase_of["NATIVE_KEEP"]
    external = {}
    for method, label in BASELINES.items():
        loaded = load_baseline(root, method, args.block, args.backbone, queries)
        if loaded is None:
            continue
        rows[label] = summarise_vectors(queries, loaded["mase"], loaded["rmsse"],
                                        label, keep_mase=keep_mase)
        rows[label]["missed_opportunity"] = 0.0
        rows[label]["scored_episodes"] = loaded["scored"]
        mase_of[label] = loaded["mase"]
        external[label] = loaded["scored"]'''

OLD_COMP = '''    for reference in ("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "A1_GLOBAL_UTILITY",
                      "A4_ALWAYS_ACT", "A5_PARAMETRIC_RIDGE", "A2_WO_INTERVENTION",
                      "A3_WO_FORECAST"):'''
NEW_COMP = '''    for reference in (("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "A1_GLOBAL_UTILITY",
                       "A4_ALWAYS_ACT", "A5_PARAMETRIC_RIDGE", "A2_WO_INTERVENTION",
                       "A3_WO_FORECAST") + tuple(external)):'''

OLD_RANK = '''    ranked = [name for name in list(DEPLOYABLE) + list(ABLATIONS)]'''
NEW_RANK = '''    ranked = [name for name in list(DEPLOYABLE) + list(external) + list(ABLATIONS)]'''

OLD_PAY = '''        "episodes": n,
        "parents": int(len({c.parent for c in eval_catalogs})),'''
NEW_PAY = '''        "episodes": n,
        "external_baselines": external,
        "parents": int(len({c.parent for c in eval_catalogs})),'''


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    for old, new in ((OLD_IMPORT, NEW_IMPORT), (OLD_SUM, NEW_SUM), (OLD_ROWS, NEW_ROWS),
                     (OLD_COMP, NEW_COMP), (OLD_RANK, NEW_RANK), (OLD_PAY, NEW_PAY)):
        assert old in text, old[:60]
        text = text.replace(old, new)
    io.open(PATH, "w", encoding="utf-8").write(text)
    import ast
    ast.parse(text)
    print("evaluation now carries baseline rows")


if __name__ == "__main__":
    main()
