#!/usr/bin/env python3
"""Second half of the v4.7 code changes: the selector module and the stages.

Run after ``v47_patch.py``.  Idempotent.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path("/home/vipuser/work/work2")
CHANGES: list[str] = []
SKIPPED: list[str] = []


def edit(rel: str, old: str, new: str, *, tag: str) -> None:
    path = ROOT / rel
    text = path.read_text()
    if new in text:
        SKIPPED.append(tag)
        return
    if old not in text:
        raise SystemExit(f"FAILED {tag}: anchor not found in {rel}")
    if text.count(old) != 1:
        raise SystemExit(f"FAILED {tag}: anchor is not unique in {rel}")
    path.write_text(text.replace(old, new))
    CHANGES.append(tag)


# ===================================================== the v47 selector module

pkg = ROOT / "src/introact_ts/v47"
pkg.mkdir(parents=True, exist_ok=True)
init = pkg / "__init__.py"
if not init.exists():
    init.write_text('"""v4.7 selection layer.\n\n'
                    'Same decision rule as v4.4 and v4.6.  What changes is the catalog, which\n'
                    'now carries a trained imputer, and the rule that picks the neighbourhood\n'
                    'size and the penalty strength.\n"""\n')
    CHANGES.append("create src/introact_ts/v47/__init__.py")

select_src = (ROOT / "src/introact_ts/v46/select.py").read_text()
select_dst = pkg / "select.py"
if not select_dst.exists() or "v4.7 selector" not in select_dst.read_text():
    select_dst.write_text(select_src.replace(
        '"""v4.6 selector:', '"""v4.7 selector:', 1))
    CHANGES.append("copy v46/select.py -> v47/select.py")

edit("src/introact_ts/v47/select.py",
     '''K_GRID = (8, 16, 32, 64, 128, 256)
BETA_GRID = (0.0, 0.5, 1.0, 1.64)''',
     '''K_GRID = P.K_GRID
BETA_GRID = P.BETA_GRID''',
     tag="select: the searched grids come from the frozen protocol")

edit("src/introact_ts/v47/select.py",
     '''    feasible = [r for r in rows if cap is None or r["conditional_hir"] <= cap]
    fallback = not feasible
    if fallback:
        feasible = [r for r in rows if r["beta"] == max(beta_grid)]
    leader = min(feasible, key=lambda r: (r["lopo_mase"], r["k"]))
    # A paired comparison against the leader, clustered on the parent, says
    # which of the remaining settings the bank cannot separate from it.
    for r in feasible:
        gap = macro_difference(queries, r["mase"], leader["mase"])
        r["gap_to_leader"] = gap["difference"]
        r["gap_se"] = gap["standard_error"]
        r["tied_with_leader"] = bool(gap["difference"] <= gap["standard_error"])
    tied = [r for r in feasible if r["tied_with_leader"]]
    # Among settings the bank cannot separate, the one that intervenes least
    # carries the least exposure to harm.
    best = min(tied, key=lambda r: (r["intervention_rate"], -r["beta"], r["k"]))
    for r in rows:
        r.pop("mase", None)
    return {"selected": {"k": best["k"], "beta": best["beta"]},
            "cap": cap, "fallback_to_most_conservative": fallback,
            "rule": "one clustered standard error of the leave-one-parent-out "
                    "leader, then the least intervening setting",
            "leader": {"k": leader["k"], "beta": leader["beta"],
                       "lopo_mase": leader["lopo_mase"]},
            "tied_settings": len(tied), "feasible_settings": len(feasible),
            "grid": sorted(rows, key=lambda r: r["lopo_mase"])}''',
     '''    feasible = [r for r in rows if cap is None or r["conditional_hir"] <= cap]
    fallback = not feasible
    if fallback:
        feasible = [r for r in rows if r["beta"] == max(beta_grid)]
    # Among the settings the cap admits, take the lowest cross-validated macro.
    # Ties on that value are broken towards the setting that intervenes least,
    # which is the same reasoning the cap itself rests on.
    best = min(feasible, key=lambda r: (round(r["lopo_mase"], 6),
                                        r["intervention_rate"], r["k"]))
    # The spread against the selected setting is reported so a reader can see
    # how flat the surface is, and it selects nothing.
    for r in feasible:
        gap = macro_difference(queries, r["mase"], best["mase"])
        r["gap_to_selected"] = gap["difference"]
        r["gap_se"] = gap["standard_error"]
    for r in rows:
        r.pop("mase", None)
    return {"selected": {"k": best["k"], "beta": best["beta"]},
            "cap": cap, "fallback_to_most_conservative": fallback,
            "rule": "lowest leave-one-parent-out source-macro MASE among the "
                    "settings whose conditional harmful rate respects the cap",
            "leader": {"k": best["k"], "beta": best["beta"],
                       "lopo_mase": best["lopo_mase"]},
            "feasible_settings": len(feasible),
            "grid": sorted(rows, key=lambda r: r["lopo_mase"])}''',
     tag="select: constrained minimisation replaces the one standard error rule")


# ================================================================ the stages

# -- TS-ICL stage: its own lock, so the backbones may run beside it ----------

edit("scripts/v47_tsicl.py",
     '''    with (root / "locks/gpu.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        active = subprocess.check_output(
            ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
            text=True).strip()
        if active:
            raise RuntimeError("GPU has active processes; refusing to interfere")
        import torch''',
     '''    with (root / "locks/gpu-tsicl.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # One lock per model stage rather than one for the device.  The
        # checkpoints here are small and every call is a single series, so the
        # device is latency bound and several stages together finish sooner
        # than the same stages one after another.  The free-memory floor is
        # what keeps that from turning into an allocation failure.
        free_mib = int(subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            text=True).strip().splitlines()[0])
        if free_mib < 6144:
            raise RuntimeError(f"only {free_mib} MiB of GPU memory is free")
        import torch''',
     tag="tsicl: per-stage lock and a memory floor")

# -- forecast stage: the imputer archive, the guard, its own lock ------------

edit("scripts/v47_forecast.py",
     '''def load_candidate(store, tsicl_store, key: str, action: str) -> np.ndarray | None:
    if action in ("KEEP", "FFILL", "CONTEXT_RIDGE"):
        name = f"{key}|{action}"
        return store[name] if name in store.files else None
    name = f"{key}|{action}"
    return tsicl_store[name] if name in tsicl_store.files else None''',
     '''def load_candidate(store, tsicl_store, saits_store, key: str,
                   action: str) -> np.ndarray | None:
    name = f"{key}|{action}"
    if action in ("KEEP", "FFILL", "CONTEXT_RIDGE"):
        return store[name] if name in store.files else None
    if action == "SAITS":
        if saits_store is None or name not in saits_store.files:
            return None
        return saits_store[name]
    return tsicl_store[name] if name in tsicl_store.files else None''',
     tag="forecast: load the imputer candidate")

edit("scripts/v47_forecast.py",
     '''from introact_ts.v44 import protocol as P
from introact_ts.v44.hashing import array_hash''',
     '''from introact_ts.v44 import actions as A
from introact_ts.v44 import protocol as P
from introact_ts.v44.hashing import array_hash''',
     tag="forecast: import the guard")

edit("scripts/v47_forecast.py",
     '''    with np.load(OUT / "inputs" / f"{args.block}.npz", allow_pickle=False) as store, \\
            np.load(tsicl_path, allow_pickle=False) as tsicl_store:''',
     '''    saits_path = OUT / "saits" / f"{args.block}.npz"
    saits_store = (np.load(saits_path, allow_pickle=False)
                   if saits_path.exists() else None)

    with np.load(OUT / "inputs" / f"{args.block}.npz", allow_pickle=False) as store, \\
            np.load(tsicl_path, allow_pickle=False) as tsicl_store:''',
     tag="forecast: open the imputer archive")

edit("scripts/v47_forecast.py",
     '''                meta = row["candidates"].get(action)
                if action in ("SINGLE_TSICL", "MULTI_TSICL"):
                    available = f"{key}|{action}" in tsicl_store.files
                    meta = {"applicable": available,
                            "reason": None if available else "tsicl stage produced no output"}''',
     '''                meta = row["candidates"].get(action)
                if action in ("SINGLE_TSICL", "MULTI_TSICL"):
                    available = f"{key}|{action}" in tsicl_store.files
                    meta = {"applicable": available,
                            "reason": None if available else "tsicl stage produced no output"}
                if action == "SAITS":
                    available = (saits_store is not None
                                 and f"{key}|{action}" in saits_store.files)
                    meta = {"applicable": available,
                            "reason": None if available else "imputer stage produced no output"}''',
     tag="forecast: plan the imputer action")

edit("scripts/v47_forecast.py",
     '''                value = load_candidate(store, tsicl_store, key, action)
                if value is None:
                    plan.append({"episode": key, "action": action,
                                 "applicable": False,
                                 "reason": "candidate array missing",
                                 "input_hash": None})
                    continue
                digest = array_hash(value)''',
     '''                value = load_candidate(store, tsicl_store, saits_store, key, action)
                if value is None:
                    plan.append({"episode": key, "action": action,
                                 "applicable": False,
                                 "reason": "candidate array missing",
                                 "input_hash": None})
                    continue
                # Every candidate meets the registered plausibility bound
                # before it is executed, whichever stage produced it, so a
                # diverging repair is recorded here instead of entering the
                # bank as a legitimate execution.
                implausible = A.implausible_reason(value, store[f"{key}|reference"])
                if implausible is not None:
                    plan.append({"episode": key, "action": action,
                                 "applicable": False, "reason": implausible,
                                 "input_hash": None})
                    continue
                digest = array_hash(value)''',
     tag="forecast: the plausibility guard runs on every candidate")

edit("scripts/v47_forecast.py",
     '''        with (root / "locks/gpu.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            active = subprocess.check_output(
                ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
                text=True).strip()
            if active:
                raise RuntimeError("GPU has active processes; refusing to interfere")
            import torch''',
     '''        with (root / f"locks/gpu-{args.backbone}.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # One lock per backbone.  Every call is a single series on a small
            # checkpoint, so the device is latency bound and the three frozen
            # families together finish sooner than the same three in sequence.
            free_mib = int(subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                text=True).strip().splitlines()[0])
            if free_mib < 6144:
                raise RuntimeError(f"only {free_mib} MiB of GPU memory is free")
            import torch''',
     tag="forecast: per-backbone lock and a memory floor")

# -- selection stage: a bank that may span several blocks --------------------

edit("scripts/v47_select.py",
     '''    parser.add_argument("--backbone", default="bolt")
    args = parser.parse_args()''',
     '''    parser.add_argument("--backbone", default="bolt")
    parser.add_argument("--bank-blocks", default="bankx",
                        help="comma separated blocks that make up the replay bank")
    args = parser.parse_args()''',
     tag="select stage: bank blocks argument")

edit("scripts/v47_select.py",
     '''    catalogs = C.load_catalog(root, "bank", args.backbone)
    blocks = SEL.blocks_of()''',
     '''    catalogs = []
    for name in args.bank_blocks.split(","):
        catalogs.extend(C.load_catalog(root, name.strip(), args.backbone))
    blocks = SEL.blocks_of()''',
     tag="select stage: load every bank block")

edit("scripts/v47_select.py",
     '''        "stage": "v46-hyperparameter-selection",
        "backbone": args.backbone,
        "block": "bank",''',
     '''        "stage": "v47-hyperparameter-selection",
        "backbone": args.backbone,
        "block": args.bank_blocks,''',
     tag="select stage: record which blocks the bank came from")

# -- evaluation stage: roster, ranking pool, comparisons ---------------------

edit("scripts/v47_evaluate.py",
     '''DEPLOYABLE = ("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "FULL_INTROACT")''',
     '''DEPLOYABLE = ("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "FIXED_SAITS",
              "FULL_INTROACT")''',
     tag="evaluate: the fixed imputer is a deployable row")

edit("scripts/v47_evaluate.py",
     '''BASELINES = {"saits": "SAITS", "tato": "TATO"}''',
     '''BASELINES = {"tato": "TATO"}''',
     tag="evaluate: the imputer row comes from the catalog, not from a side file")

edit("scripts/v47_evaluate.py",
     '''    parser.add_argument("--resamples", type=int, default=2000)
    args = parser.parse_args()''',
     '''    parser.add_argument("--resamples", type=int, default=2000)
    parser.add_argument("--bank-blocks", default="bankx")
    args = parser.parse_args()''',
     tag="evaluate: bank blocks argument")

edit("scripts/v47_evaluate.py",
     '''    bank_catalogs = C.load_catalog(root, "bank", args.backbone)
    eval_catalogs = C.load_catalog(root, args.block, args.backbone)''',
     '''    bank_catalogs = []
    for name in args.bank_blocks.split(","):
        bank_catalogs.extend(C.load_catalog(root, name.strip(), args.backbone))
    eval_catalogs = C.load_catalog(root, args.block, args.backbone)''',
     tag="evaluate: load every bank block")

edit("scripts/v47_evaluate.py",
     '''    decisions["R2_CART"] = SEL.r2_cart(bank, queries)''',
     '''    decisions["R2_CART"] = SEL.r2_cart(bank, queries)
    # Always applying the trained imputer is a fixed policy over one catalog
    # action, so it is computed here rather than read from a separate file and
    # it is accounted exactly like every other row.
    decisions["FIXED_SAITS"] = SEL.apply_fixed(queries, "SAITS")''',
     tag="evaluate: the fixed imputer row")

edit("scripts/v47_evaluate.py",
     '''    for reference in (("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "A1_GLOBAL_UTILITY",
                       "A4_ALWAYS_ACT", "A5_PARAMETRIC_RIDGE", "A2_WO_INTERVENTION",
                       "A3_WO_FORECAST") + tuple(external)):''',
     '''    for reference in (("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "FIXED_SAITS",
                       "A1_GLOBAL_UTILITY", "A4_ALWAYS_ACT", "A5_PARAMETRIC_RIDGE",
                       "A2_WO_INTERVENTION", "A3_WO_FORECAST") + tuple(external)):''',
     tag="evaluate: compare against the fixed imputer")

edit("scripts/v47_evaluate.py",
     '''    family = [f"FULL_INTROACT_vs_{name}" for name
              in ("NATIVE_KEEP", "BEST_FIXED", "R2_CART") + tuple(external)
              if f"FULL_INTROACT_vs_{name}" in comparisons]''',
     '''    family = [f"FULL_INTROACT_vs_{name}" for name
              in ("NATIVE_KEEP", "BEST_FIXED", "R2_CART", "FIXED_SAITS")
              + tuple(external)
              if f"FULL_INTROACT_vs_{name}" in comparisons]''',
     tag="evaluate: the Holm family is the deployable roster")

edit("scripts/v47_evaluate.py",
     '''    ranked = [name for name in list(DEPLOYABLE) + list(external) + list(ABLATIONS)]
    cell_rank = collections.defaultdict(list)
    for i in range(n):
        values = [(name, mase_of[name][i]) for name in ranked
                  if np.isfinite(mase_of[name][i])]''',
     '''    # The average rank the main table reports is over the rows of that table,
    # so the pool is the deployable roster and nothing else.  The ablation
    # variants are ranked separately because they are variants of one method
    # rather than competing rows.
    ranked = [name for name in list(DEPLOYABLE) + list(external)]
    cell_rank = collections.defaultdict(list)
    for i in range(n):
        values = [(name, mase_of[name][i]) for name in ranked
                  if np.isfinite(mase_of[name][i])]''',
     tag="evaluate: the ranking pool is the main table roster")

edit("scripts/v47_evaluate.py",
     '''    average_rank = {name: float(np.mean(v)) for name, v in cell_rank.items()}''',
     '''    average_rank = {name: float(np.mean(v)) for name, v in cell_rank.items()}

    ablation_pool = ["FULL_INTROACT"] + list(ABLATIONS)
    ablation_rank_cells = collections.defaultdict(list)
    for i in range(n):
        values = [(name, mase_of[name][i]) for name in ablation_pool
                  if name in mase_of and np.isfinite(mase_of[name][i])]
        if len(values) < 2:
            continue
        for j, (name, _value) in enumerate(sorted(values, key=lambda kv: kv[1])):
            ablation_rank_cells[name].append(j + 1)
    ablation_rank = {name: float(np.mean(v))
                     for name, v in ablation_rank_cells.items()}''',
     tag="evaluate: a separate rank over the ablation variants")

edit("scripts/v47_evaluate.py",
     '''        "rows": rows,
        "average_rank": average_rank,''',
     '''        "rows": rows,
        "average_rank": average_rank,
        "average_rank_pool": ranked,
        "ablation_rank": ablation_rank,''',
     tag="evaluate: record the ranking pool")

edit("scripts/v47_evaluate.py",
     '''        "stage": "v46-evaluation",''',
     '''        "stage": "v47-evaluation",''',
     tag="evaluate: stage name")

# -- the diagnostics that read the bank --------------------------------------

for rel, tag in (("scripts/v47_banksize.py", "bank size"),
                 ("scripts/v47_selection_stability.py", "selection stability"),
                 ("scripts/v47_severity_bias.py", "severity bias")):
    text = (ROOT / rel).read_text()
    if 'C.load_catalog(root, "bank"' in text:
        edit(rel, 'C.load_catalog(root, "bank"', 'C.load_catalog(root, "bankx"',
             tag=f"{tag}: read the densified bank")
    elif 'C.load_catalog(ROOT, "bank"' in text:
        edit(rel, 'C.load_catalog(ROOT, "bank"', 'C.load_catalog(ROOT, "bankx"',
             tag=f"{tag}: read the densified bank")

text = (ROOT / "scripts/v47_latency.py").read_text()
if 'C.load_catalog(ROOT, "bank"' in text:
    edit("scripts/v47_latency.py", 'C.load_catalog(ROOT, "bank"',
         'C.load_catalog(ROOT, "bankx"', tag="latency: read the densified bank")

print("APPLIED:")
for item in CHANGES:
    print("  +", item)
print("SKIPPED (already present):")
for item in SKIPPED:
    print("  =", item)
