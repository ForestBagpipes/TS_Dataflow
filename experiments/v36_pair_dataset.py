"""v3.6 Phase 0: build the episode/pair dataset from the frozen v3.3 candidate table.

Pre-registered in ``docs/v3_6_pair_preregistration.md`` (§2–§4). An episode is
one window: KEEP plus every candidate action proposed for that window in
``results/v33_training_data.jsonl``. Training pairs encode within-window
preferences ``P(a_i ≻ a_j)`` under the strict label rules of §3:

  1. beneficial_and_safe action ≻ KEEP;
  2. KEEP ≻ every non-beneficial_and_safe action;
  3. between two B&S actions, higher ``true_repair_gain`` wins; tie broken by
     lower ``true_loss``; still tied -> no pair, counted as a tie;
  4. two non-B&S actions never form a training pair (counted for audit only);
  5. every training pair is emitted in both directions (label flipped).

KEEP label semantics (implicit action, synthesized here -- it is not a row of
the candidate table): KEEP leaves the window untouched, so ``true_loss = 0.0``
and ``true_repair_gain = 0.0``; ``safe = True`` (it cannot corrupt data) but
``beneficial_and_safe = False`` because it provides no repair benefit. KEEP
carries no deployable feature vector -- ``features = {}`` is the explicit
empty marker; pair records copy it verbatim so downstream code must treat an
empty feature dict as "the KEEP baseline".

Every pair record also carries ``eval_*`` fields (true gains/losses and the
B&S flags of both sides). These are label-audit / evaluation quantities only:
they are derived from the hidden clean target and MUST NOT enter any
deployment feature vector (pre-registration §3 rule 5).

Usage:
    python experiments/v36_pair_dataset.py \
        [--input results/v33_training_data.jsonl] \
        [--manifest results/p0_corpus_manifest_a.json] \
        [--out results/v36_pair_dataset.jsonl] \
        [--integrity results/v36_pair_integrity.json]

Exit code is 1 if any integrity check FAILs (Phase 0 stop condition, §4).
"""

import argparse
import hashlib
import json
import random
import sys
import time
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

INPUT = ROOT / "results" / "v33_training_data.jsonl"
MANIFEST = ROOT / "results" / "p0_corpus_manifest_a.json"
OUT = ROOT / "results" / "v36_pair_dataset.jsonl"
INTEGRITY = ROOT / "results" / "v36_pair_integrity.json"

RECHECK_SEED = 20260903  # fixed seed for the 20-candidate label recheck (check 9)
RECHECK_N = 20

# Fields copied verbatim from a candidate row into a pair record's cand_i/cand_j.
CAND_COPY_FIELDS = ("family", "rung", "params", "features")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(obj):
    """Deterministic JSON: sorted keys, tight separators, no NaN."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cand_key(cand):
    """Canonical identity of a candidate action inside an episode."""
    return canonical_json([cand["family"], cand["rung"], cand["params"]])


def episode_id_for(sample_uid):
    return "ep-" + sha256_text(sample_uid)[:16]


def load_candidates(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def synthesize_keep(episode_meta):
    """The implicit KEEP action for one episode. See module docstring for the
    label semantics; KEEP is the baseline every real candidate is judged
    against, never a beneficiary itself."""
    return {
        "family": "KEEP",
        "rung": "keep",
        "params": {},
        "features": {},  # explicit empty marker: KEEP has no deployable features
        "beneficial": False,
        "harmful": False,
        "safe": True,
        "beneficial_and_safe": False,
        "true_loss": 0.0,
        "true_repair_gain": 0.0,
        "output_hash": None,  # KEEP produces no operator output
        "is_keep": True,
    }


def build_episodes(candidates):
    """Group candidate rows into episodes keyed by sample_uid, attach KEEP.

    Returns an OrderedDict episode_id -> episode, sorted by sample_uid so the
    whole pipeline is deterministic.
    """
    by_uid = {}
    for row in candidates:
        by_uid.setdefault(row["sample_uid"], []).append(row)
    episodes = OrderedDict()
    for uid in sorted(by_uid):
        rows = sorted(by_uid[uid], key=cand_key)
        first = rows[0]
        meta = {
            "sample_uid": uid,
            "window_id": first["window_id"],
            "dataset": first["dataset"],
            "stratum": first["stratum"],
        }
        episodes[episode_id_for(uid)] = {
            "episode_id": episode_id_for(uid),
            **meta,
            "keep": synthesize_keep(meta),
            "candidates": rows,
        }
    return episodes


def _copy_cand(cand):
    return {k: cand[k] for k in CAND_COPY_FIELDS}


def _pair_record(episode, ci, cj, label, direction):
    """One ordered pair record. cand_i ≻ cand_j iff label == 1."""
    ki, kj = cand_key(ci), cand_key(cj)
    pair_id = f"{episode['episode_id']}|{ki}|{kj}"
    rec = {
        "episode_id": episode["episode_id"],
        "sample_uid": episode["sample_uid"],
        "dataset": episode["dataset"],
        "stratum": episode["stratum"],
        "cand_i": _copy_cand(ci),
        "cand_j": _copy_cand(cj),
        "label": label,
        "pair_direction": direction,
        "pair_id": pair_id,
        # eval_* namespace: true quantities for held-out evaluation and label
        # audit only -- never deployment features (pre-registration §3.5).
        "eval_true_gain_i": ci["true_repair_gain"],
        "eval_true_loss_i": ci["true_loss"],
        "eval_true_gain_j": cj["true_repair_gain"],
        "eval_true_loss_j": cj["true_loss"],
        "eval_bns_i": ci["beneficial_and_safe"],
        "eval_bns_j": cj["beneficial_and_safe"],
    }
    rec["pair_hash"] = sha256_text(canonical_json(rec))
    return rec


def _emit_both_directions(episode, winner, loser, pairs):
    """Rule 5: (i, j) and (j, i) are both emitted, label flipped."""
    pairs.append(_pair_record(episode, winner, loser, 1, "forward"))
    pairs.append(_pair_record(episode, loser, winner, 0, "reverse"))


def generate_pairs(episode):
    """All training pairs of one episode under §3 rules 1–4.

    Returns (pairs, stats) where stats counts ties (rule 3) and the
    non-B&S/non-B&S combinations excluded from training (rule 4, audit only).
    """
    keep = episode["keep"]
    cands = episode["candidates"]  # sorted by cand_key -> deterministic
    pairs = []
    n_ties = 0
    n_nonbns_pairs = 0

    # Rules 1 & 2: every candidate vs KEEP.
    for c in cands:
        if c["beneficial_and_safe"]:
            _emit_both_directions(episode, c, keep, pairs)  # rule 1
        else:
            _emit_both_directions(episode, keep, c, pairs)  # rule 2

    # Rules 3 & 4: candidate-vs-candidate.
    bns = [c for c in cands if c["beneficial_and_safe"]]
    non_bns = [c for c in cands if not c["beneficial_and_safe"]]
    for a in range(len(bns)):
        for b in range(a + 1, len(bns)):
            ci, cj = bns[a], bns[b]
            if ci["true_repair_gain"] != cj["true_repair_gain"]:
                winner, loser = (ci, cj) if ci["true_repair_gain"] > cj["true_repair_gain"] else (cj, ci)
            elif ci["true_loss"] != cj["true_loss"]:
                winner, loser = (ci, cj) if ci["true_loss"] < cj["true_loss"] else (cj, ci)
            else:
                n_ties += 1  # still tied after both criteria: no pair
                continue
            _emit_both_directions(episode, winner, loser, pairs)
    n_nonbns_pairs = len(non_bns) * (len(non_bns) - 1) // 2  # rule 4 audit count

    return pairs, {"ties": n_ties, "nonbns_excluded_combos": n_nonbns_pairs}


def build_dataset(candidates):
    """Episodes + all pair records, fully deterministic ordering."""
    episodes = build_episodes(candidates)
    records = []
    stats = {
        "ties": 0,
        "nonbns_excluded_combos": 0,
        "family_combo_pairs": Counter(),  # unordered family pair -> forward-pair count
        "bns_vs_keep_pairs": 0,  # forward pairs only
        "bns_vs_bns_pairs": 0,
        "per_dataset": {},
    }
    for ep in episodes.values():
        pairs, ep_stats = generate_pairs(ep)
        records.extend(pairs)
        stats["ties"] += ep_stats["ties"]
        stats["nonbns_excluded_combos"] += ep_stats["nonbns_excluded_combos"]
        ds = ep["dataset"]
        per = stats["per_dataset"].setdefault(ds, {"episodes": 0, "pairs": 0})
        per["episodes"] += 1
        per["pairs"] += len(pairs)
        for rec in pairs:
            if rec["pair_direction"] != "forward":
                continue
            fi, fj = rec["cand_i"]["family"], rec["cand_j"]["family"]
            combo = "|".join(sorted((fi, fj)))
            stats["family_combo_pairs"][combo] += 1
            if "KEEP" in (fi, fj):
                stats["bns_vs_keep_pairs"] += 1
            else:
                stats["bns_vs_bns_pairs"] += 1
    return episodes, records, stats


# ---------------------------------------------------------------------------
# Integrity checks (pre-registration §4; any FAIL stops Phase 0)
# ---------------------------------------------------------------------------


def check_dataset(episodes, records, candidates, input_path, manifest_path, code_path):
    """Returns (checks, ok) -- checks is an ordered dict name -> {status, detail}."""
    checks = OrderedDict()

    def record(name, ok, detail):
        checks[name] = {"status": "PASS" if ok else "FAIL", "detail": detail}
        return ok

    # 1. Episode count == windows covered by the frozen table.
    uids = {r["sample_uid"] for r in candidates}
    wins = {r["window_id"] for r in candidates}
    record(
        "1_episode_count_matches_frozen_windows",
        len(episodes) == len(uids) == len(wins),
        f"episodes={len(episodes)} unique_sample_uids={len(uids)} unique_window_ids={len(wins)} candidates={len(candidates)}",
    )

    # 2. Episode <-> sample_uid bijection; all rows of a uid in one episode.
    uid_to_eps = {}
    for ep in episodes.values():
        uid_to_eps.setdefault(ep["sample_uid"], set()).add(ep["episode_id"])
    ep_uids = [ep["sample_uid"] for ep in episodes.values()]
    ok = (
        len(set(ep_uids)) == len(episodes)
        and all(len(v) == 1 for v in uid_to_eps.values())
        and set(ep_uids) == uids
        and all(
            {r["sample_uid"] for r in ep["candidates"]} == {ep["sample_uid"]}
            for ep in episodes.values()
        )
    )
    record(
        "2_episode_sample_uid_bijection",
        ok,
        f"episodes={len(episodes)} distinct_uids={len(set(ep_uids))} uids_mapped={len(uid_to_eps)}",
    )

    # 3. KEEP present and unique per episode.
    ok = all(ep["keep"]["family"] == "KEEP" for ep in episodes.values())
    ok = ok and all(
        sum(1 for c in ep["candidates"] if c["family"] == "KEEP") == 0
        for ep in episodes.values()
    )
    record(
        "3_keep_present_and_unique",
        ok,
        "KEEP is synthesized exactly once per episode; no KEEP row exists in the candidate table",
    )

    # 4. No duplicate (family, rung, params) inside an episode.
    bad = [
        ep["episode_id"]
        for ep in episodes.values()
        if len({cand_key(c) for c in ep["candidates"]}) != len(ep["candidates"])
    ]
    record("4_no_duplicate_candidate_actions", not bad, f"violating_episodes={bad[:5]}")

    # 5. Forward/reverse symmetry: equal counts; every forward pair has its
    #    mirror with swapped i/j and flipped label.
    fwd = [r for r in records if r["pair_direction"] == "forward"]
    rev = [r for r in records if r["pair_direction"] == "reverse"]
    rev_index = {}
    for r in rev:
        key = (r["episode_id"], cand_key(r["cand_j"]) + "->" + cand_key(r["cand_i"]))
        rev_index[key] = r
    ok = len(fwd) == len(rev)
    for r in fwd:
        key = (r["episode_id"], cand_key(r["cand_i"]) + "->" + cand_key(r["cand_j"]))
        mirror = rev_index.get(key)
        if mirror is None or mirror["label"] != 1 - r["label"]:
            ok = False
            break
    record(
        "5_forward_reverse_symmetry",
        ok,
        f"forward={len(fwd)} reverse={len(rev)} labels_flip_checked=True",
    )

    # 6. No cross-window pairs: pair_id embeds episode_id; both sides carry the
    #    record's episode (pairs are only ever generated within one episode).
    ok = True
    ep_by_id = {eid: ep for eid, ep in episodes.items()}
    for r in records:
        if not r["pair_id"].startswith(r["episode_id"] + "|"):
            ok = False
            break
        ep = ep_by_id[r["episode_id"]]
        member_keys = {cand_key(c) for c in ep["candidates"]} | {cand_key(ep["keep"])}
        if cand_key(r["cand_i"]) not in member_keys or cand_key(r["cand_j"]) not in member_keys:
            ok = False
            break
    record(
        "6_pairs_never_cross_windows",
        ok,
        "pair_id = '<episode_id>|<cand_i_key>|<cand_j_key>'; both sides asserted episode members",
    )

    # 7. LODO grouping feasible: every pair carries dataset; per-source counts.
    per_ds = Counter()
    ep_per_ds = Counter()
    for r in records:
        per_ds[r["dataset"]] += 1
    for ep in episodes.values():
        ep_per_ds[ep["dataset"]] += 1
    ok = all(r.get("dataset") for r in records) and len(per_ds) >= 2
    record(
        "7_lodo_dataset_grouping",
        ok,
        {
            "n_datasets": len(per_ds),
            "pairs_per_dataset": dict(sorted(per_ds.items())),
            "episodes_per_dataset": dict(sorted(ep_per_ds.items())),
        },
    )

    # 8. Provenance hashes.
    checks["8_provenance_hashes"] = {
        "status": "PASS",
        "detail": {
            "corpus_manifest_path": str(manifest_path),
            "corpus_manifest_sha256": sha256_file(manifest_path),
            "input_path": str(input_path),
            "input_sha256": sha256_file(input_path),
            "code_path": str(code_path),
            "code_sha256": sha256_file(code_path),
            "pair_count": len(records),
            "episode_count": len(episodes),
        },
    }

    # 9. Label recheck: re-read the frozen table fresh and compare 20 random
    #    candidates' labels against the episode copies; output_hash non-empty.
    fresh = load_candidates(input_path)
    fresh_index = {}
    for r in fresh:
        fresh_index[(r["sample_uid"], cand_key(r))] = r
    rng = random.Random(RECHECK_SEED)
    sample = rng.sample(fresh, min(RECHECK_N, len(fresh)))
    mismatches = []
    for s in sample:
        rebuilt = None
        for ep in episodes.values():
            if ep["sample_uid"] != s["sample_uid"]:
                continue
            for c in ep["candidates"]:
                if cand_key(c) == cand_key(s):
                    rebuilt = c
                    break
        key = (s["sample_uid"], cand_key(s))
        if rebuilt is None or key not in fresh_index:
            mismatches.append({"sample_uid": s["sample_uid"], "reason": "missing"})
            continue
        for field in ("beneficial_and_safe", "true_loss", "true_repair_gain"):
            if rebuilt[field] != fresh_index[key][field]:
                mismatches.append(
                    {"sample_uid": s["sample_uid"], "field": field,
                     "episode_value": rebuilt[field], "table_value": fresh_index[key][field]}
                )
    empty_output_hash = [
        r["sample_uid"] for r in fresh if not r.get("output_hash")
    ][:5]
    record(
        "9_label_recheck_and_output_hash",
        not mismatches and not empty_output_hash,
        {
            "recheck_seed": RECHECK_SEED,
            "n_sampled": len(sample),
            "mismatches": mismatches,
            "empty_output_hash_examples": empty_output_hash,
        },
    )

    ok_all = all(c["status"] == "PASS" for c in checks.values())
    return checks, ok_all


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(INPUT))
    ap.add_argument("--manifest", default=str(MANIFEST))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--integrity", default=str(INTEGRITY))
    args = ap.parse_args(argv)

    t0 = time.time()
    input_path, manifest_path = Path(args.input), Path(args.manifest)
    code_path = Path(__file__).resolve()

    candidates = load_candidates(input_path)
    episodes, records, stats = build_dataset(candidates)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        for rec in records:
            f.write(canonical_json(rec) + "\n")

    checks, ok_all = check_dataset(
        episodes, records, candidates, input_path, manifest_path, code_path
    )

    elapsed = time.time() - t0
    report = {
        "schema_version": "v36-pair-1",
        "generator": "experiments/v36_pair_dataset.py",
        "label_rules": "docs/v3_6_pair_preregistration.md §3 rules 1-5",
        "overall": "PASS" if ok_all else "FAIL",
        "elapsed_seconds": round(elapsed, 3),
        "episode_count": len(episodes),
        "candidate_count": len(candidates),
        "pair_count": len(records),
        "forward_pairs": sum(1 for r in records if r["pair_direction"] == "forward"),
        "reverse_pairs": sum(1 for r in records if r["pair_direction"] == "reverse"),
        "bns_vs_keep_forward_pairs": stats["bns_vs_keep_pairs"],
        "bns_vs_bns_forward_pairs": stats["bns_vs_bns_pairs"],
        "rule3_ties_no_pair": stats["ties"],
        "rule4_nonbns_excluded_combos": stats["nonbns_excluded_combos"],
        "pair_count_per_dataset": {
            k: v["pairs"] for k, v in sorted(stats["per_dataset"].items())
        },
        "episode_count_per_dataset": {
            k: v["episodes"] for k, v in sorted(stats["per_dataset"].items())
        },
        "forward_pairs_per_family_combo": dict(sorted(stats["family_combo_pairs"].items())),
        "dataset_file_sha256": sha256_file(out_path),
        "checks": checks,
    }
    integ_path = Path(args.integrity)
    integ_path.parent.mkdir(parents=True, exist_ok=True)
    with open(integ_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(canonical_json(report) + "\n")

    print(json.dumps({"overall": report["overall"],
                      "episodes": report["episode_count"],
                      "pairs": report["pair_count"],
                      "ties": report["rule3_ties_no_pair"],
                      "elapsed_seconds": report["elapsed_seconds"],
                      "dataset_sha256": report["dataset_file_sha256"]}, indent=2))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
