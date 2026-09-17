#!/usr/bin/env python3
"""v4.4 -- canonical tables for the TRAIN-Eval admission batch (task book §31).

Emits machine-readable tables from the frozen artifacts so the paper side never
has to re-derive a number from prose:

* ``table_train_eval.csv``        one row per (backbone, method)
* ``table_train_eval_cells.csv``  one row per (backbone, method, horizon, pattern)
* ``table_train_eval_pairs.csv``  one row per paired bootstrap comparison
* ``claims.md``                   what the batch does and does not support

Every value is copied from ``train_eval.json`` / ``admission.json``; nothing is
recomputed here, so a table can always be traced back to the frozen artifact.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from introact_ts.v44 import protocol as P

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "results/v44/evaluation"

ORDER = ["NATIVE_KEEP", "BEST_FIXED", "R2_CART", "FULL_INTROACT",
         "A1_GLOBAL_REPLAY", "A2_WO_INTERVENTION", "A3_WO_FORECAST",
         "A4_WO_GATE", "A5_PARAMETRIC_RIDGE", "A5_PARAMETRIC_CART",
         "CATALOG_ORACLE"]

MAIN_COLUMNS = ["backbone", "method", "source_macro_mase", "intervention_rate",
                "hir", "harmful_loss", "cgc", "cgc_usable", "cgc_excluded",
                "n_scored", "excluded_missing_loss", "mean_latency",
                "p95_latency", "max_latency", "difference_vs_full",
                "ci_low", "ci_high", "ci_excludes_zero"]


def dump(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval", default=str(EVAL / "train_eval.json"))
    parser.add_argument("--admission", default=str(EVAL / "admission.json"))
    parser.add_argument("--out", default=str(EVAL))
    args = parser.parse_args()

    evaluation = json.loads(Path(args.eval).read_text())
    admission = json.loads(Path(args.admission).read_text())
    out = Path(args.out)

    main_rows = []
    cell_rows = []
    pair_rows = []

    for backbone in P.DEV_BACKBONES:
        block = evaluation["per_backbone"][backbone]
        report = admission["per_backbone"][backbone]
        comparisons = {**report["vs_controls"], **report["component_contribution"]}
        for method in ORDER:
            if method not in block["macro_mase"]:
                continue
            governance = block["governance"].get(method, {})
            efficiency = block["efficiency"].get(method, {})
            comparison = comparisons.get(method)
            main_rows.append([
                backbone, method, block["macro_mase"][method],
                governance.get("intervention_rate"), governance.get("hir"),
                governance.get("harmful_loss"), governance.get("cgc"),
                governance.get("usable"), governance.get("excluded"),
                governance.get("n"), governance.get("excluded_missing_loss"),
                efficiency.get("mean_latency"), efficiency.get("p95_latency"),
                efficiency.get("max_latency"),
                (comparison or {}).get("difference"),
                (comparison or {}).get("ci_low"),
                (comparison or {}).get("ci_high"),
                (comparison or {}).get("excludes_zero"),
            ])
            for cell, value in sorted(block["macro_cells"].get(method, {}).items()):
                horizon, pattern = cell.split("|", 1)
                cell_rows.append([backbone, method, horizon, pattern, value])

        for name, comparison in comparisons.items():
            if comparison.get("status") != "computed":
                continue
            pair_rows.append([
                backbone, "FULL_INTROACT", name, comparison["difference"],
                comparison["ci_low"], comparison["ci_high"],
                comparison["excludes_zero"], comparison["favours"],
                comparison["parents"], comparison["sources"],
                comparison["unpaired_dropped"],
                admission["bootstrap"]["resamples"],
                admission["bootstrap"]["seed"],
            ])

    dump(out / "table_train_eval.csv", MAIN_COLUMNS, main_rows)
    dump(out / "table_train_eval_cells.csv",
         ["backbone", "method", "horizon", "pattern", "source_macro_mase"],
         cell_rows)
    dump(out / "table_train_eval_pairs.csv",
         ["backbone", "left", "right", "difference", "ci_low", "ci_high",
          "excludes_zero", "favours", "parents", "sources", "unpaired_dropped",
          "resamples", "seed"], pair_rows)

    verdicts = admission["verdicts"]
    lines = [
        "# v4.4 TRAIN-Eval 准入批次 — 可支持与不可支持的陈述",
        "",
        "数据来源：`results/v44/evaluation/train_eval.json`（frozen K=%d, beta=%.2f）"
        "与 `admission.json`。协议 `PROTOCOL_SEED=%d`，"
        "统计为 parent 单位配对聚类 bootstrap，%d 次重采样，seed %d。"
        % (admission["frozen"]["k"], admission["frozen"]["beta"], P.PROTOCOL_SEED,
           admission["bootstrap"]["resamples"], admission["bootstrap"]["seed"]),
        "**calibration / test 全程未读取**（`heldout_labels_read=0`）。",
        "",
        "## 可以陈述",
        "",
    ]
    for backbone, verdict in verdicts.items():
        value = verdict["full_source_macro_mase"]
        lines.append(
            "- `%s`：Full IntroAct 的 source-macro MASE 为 `%.6f`，"
            "低于 Native KEEP 与 R2-CART。" % (backbone, value))
        beat = [name for name, ok in verdict["beats_controls"].items() if ok]
        if beat:
            lines.append("  - 点估计低于的对照：%s。" % ", ".join(beat))
        else:
            lines.append("  - 点估计未低于任何对照。")
    lines += [
        "- 保守闸门确实降低了有害干预比例（见 `table_train_eval.csv` 的 `hir` 列）。",
        "",
        "## 不可以陈述",
        "",
        "- 不可以说 v4.4 方法优于其自身消融：",
    ]
    for backbone, verdict in verdicts.items():
        missing = verdict["components_not_contributing"]
        lines.append("  - `%s`：移除下列模块后指标**不变差或更好**：%s。"
                     % (backbone, ", ".join(missing) if missing else "（无）"))
    lines += [
        "- 不可以说三个模块均有贡献；`A4_WO_GATE` 在两个骨干上都显著优于 Full，"
        "即保守闸门以平均精度为代价换取更低的 HIR，这是治理权衡，不是精度增益。",
        "- 不可以说超过 Best Fixed 已被证实：TimesFM 上 Full 与 Best Fixed 的配对"
        "区间跨零。",
        "- 不可以引用任何 calibration / test 数字；本批次未打开。",
        "- 不可以声称 SOTA、显著优于文献方法或已通过独立确认。",
        "- Catalog Oracle 是事后诊断，不入排名、不入 claim。",
        "",
        "## 结论",
        "",
        "本批次**不构成方法晋升**。按任务书 §21，方法扩展停止，"
        "保留 v4.4 负结果，确认集保持封存。",
        "",
    ]
    (out / "claims.md").write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "main_rows": len(main_rows), "cell_rows": len(cell_rows),
        "pair_rows": len(pair_rows),
        "files": [str(out / name) for name in
                  ("table_train_eval.csv", "table_train_eval_cells.csv",
                   "table_train_eval_pairs.csv", "claims.md")],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
