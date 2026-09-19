"""The paper says Holm is applied across the pre-declared baseline comparisons.

The evaluation stage computed intervals and stopped there, so the statement had
nothing behind it.  The bootstrap now also returns a two-sided p-value from its
own draws, and the evaluation stage adjusts the five baseline comparisons with
Holm and records both the raw and the adjusted value.
"""
import io

SELECT = "src/introact_ts/v46/select.py"
EVALUATE = "scripts/v46_evaluate.py"

OLD_BOOT = '''    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {"difference": point, "ci_low": float(lo), "ci_high": float(hi),
            "excludes_zero": bool(lo > 0 or hi < 0),
            "parents": len(by_parent), "resamples": resamples, "seed": seed}'''

NEW_BOOT = '''    lo, hi = np.percentile(draws, [2.5, 97.5])
    # A two-sided p-value read off the same draws.  It cannot go below one over
    # the number of resamples, and it is reported at that floor when it hits it.
    tail = min(float((draws <= 0).mean()), float((draws >= 0).mean()))
    p_value = min(1.0, max(2.0 * tail, 1.0 / resamples))
    return {"difference": point, "ci_low": float(lo), "ci_high": float(hi),
            "excludes_zero": bool(lo > 0 or hi < 0), "p_value": p_value,
            "parents": len(by_parent), "resamples": resamples, "seed": seed}'''

OLD_EVAL = '''    ranked = [name for name in list(DEPLOYABLE) + list(external) + list(ABLATIONS)]'''

NEW_EVAL = '''    # Holm across the pre-declared baseline comparisons only.  The ablations are
    # variants of this method rather than competing claims, so they are not in
    # the family and are reported with intervals alone.
    family = [f"FULL_INTROACT_vs_{name}" for name
              in ("NATIVE_KEEP", "BEST_FIXED", "R2_CART") + tuple(external)
              if f"FULL_INTROACT_vs_{name}" in comparisons]
    adjusted = SEL.holm({key: comparisons[key]["p_value"] for key in family})
    for key in family:
        comparisons[key]["p_holm"] = adjusted[key]
        comparisons[key]["significant_holm"] = bool(adjusted[key] < 0.05)
        comparisons[key]["in_holm_family"] = True

    ranked = [name for name in list(DEPLOYABLE) + list(external) + list(ABLATIONS)]'''


def main() -> None:
    text = io.open(SELECT, encoding="utf-8").read()
    assert OLD_BOOT in text, "bootstrap tail"
    io.open(SELECT, "w", encoding="utf-8").write(text.replace(OLD_BOOT, NEW_BOOT, 1))

    text = io.open(EVALUATE, encoding="utf-8").read()
    assert OLD_EVAL in text, "rank anchor"
    io.open(EVALUATE, "w", encoding="utf-8").write(text.replace(OLD_EVAL, NEW_EVAL, 1))
    print("Holm adjustment wired into the evaluation stage")


if __name__ == "__main__":
    main()
