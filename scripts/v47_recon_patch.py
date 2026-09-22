#!/usr/bin/env python3
"""Point the reconstruction diagnostic at the catalog, now that the trained
imputer is one of its actions, and add the across-episode statistic.

The within-episode ranking is noisy when several repairs land close together,
so the comparison also needs a statistic that does not rank inside an episode:
for each action, the correlation across episodes between how badly it
reconstructed and how much it helped.  If that is low as well, the disagreement
is a property of the two criteria rather than of the ranking.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path("/home/vipuser/work/work2")
CHANGES: list[str] = []


def edit(rel: str, old: str, new: str, *, tag: str) -> None:
    path = ROOT / rel
    text = path.read_text()
    if new in text:
        print("  = already present:", tag)
        return
    if text.count(old) != 1:
        raise SystemExit(f"FAILED {tag}: anchor appears {text.count(old)} times")
    path.write_text(text.replace(old, new))
    CHANGES.append(tag)


edit("scripts/v47_reconstruction.py",
     'REPAIRS = ("FFILL", "SINGLE_TSICL", "MULTI_TSICL", "CONTEXT_RIDGE")',
     'REPAIRS = ("FFILL", "SINGLE_TSICL", "MULTI_TSICL", "CONTEXT_RIDGE", "SAITS")',
     tag="the trained imputer is one of the repairs compared")

edit("scripts/v47_reconstruction.py",
     '''#: The published reconstruction baseline enters the same comparison when its
#: repaired inputs and its forecasts are both on disk, which is what makes the
#: two criteria comparable for it as well.
EXTERNAL = {"SAITS": ("saits", "SAITS")}''',
     '''#: Every repair in this comparison is a catalog action, so all of them are read
#: from the same stage archives and scored against the same frozen backbone.
EXTERNAL: dict[str, tuple[str, str]] = {}''',
     tag="no external row remains in the comparison")

edit("scripts/v47_reconstruction.py",
     '''    tsicl = np.load(root / "results/v47/replay/tsicl" / f"{args.block}.npz",
                    allow_pickle=False)''',
     '''    tsicl = np.load(root / "results/v47/replay/tsicl" / f"{args.block}.npz",
                    allow_pickle=False)
    saits_path = root / "results/v47/replay/saits" / f"{args.block}.npz"
    saits = (np.load(saits_path, allow_pickle=False) if saits_path.exists() else None)''',
     tag="open the imputer archive")

edit("scripts/v47_reconstruction.py",
     '''                values = (store[name] if name in store.files
                          else (tsicl[name] if name in tsicl.files else None))''',
     '''                values = None
                for handle in (store, tsicl, saits):
                    if handle is not None and name in handle.files:
                        values = handle[name]
                        break''',
     tag="read the imputer candidate like any other")

edit("scripts/v47_reconstruction.py",
     '''    finally:
        store.close()
        tsicl.close()''',
     '''    finally:
        store.close()
        tsicl.close()
        if saits is not None:
            saits.close()''',
     tag="close the imputer archive")

edit("scripts/v47_reconstruction.py",
     '''        "mean_within_episode_spearman": float(np.nanmean(rhos)) if rhos else None,''',
     '''        "mean_within_episode_spearman": float(np.nanmean(rhos)) if rhos else None,
        # Across episodes, per action: does a worse reconstruction predict a
        # worse outcome for that same repair?  This does not rank inside an
        # episode, so it is not exposed to ties between close repairs.
        "across_episode_spearman": {
            a: (spearman(-np.asarray(v["rec_mse"]), np.asarray(v["utility"]))
                if len(v["utility"]) >= 3 else None)
            for a, v in per_action.items()},''',
     tag="the across-episode statistic")

edit("scripts/v47_reconstruction.py",
     '''        "stage": "v46-reconstruction-vs-utility",''',
     '''        "stage": "v47-reconstruction-vs-utility",''',
     tag="stage name")

print("APPLIED:")
for item in CHANGES:
    print("  +", item)
