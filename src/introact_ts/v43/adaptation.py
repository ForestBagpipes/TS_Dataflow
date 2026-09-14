"""Pair export integrity only; actual TSFM adaptation remains pending."""
from .schemas import array_hash, require


def export_training_pairs(episode, candidate, target, raw_test_context):
    require(episode.split == "train" and target.split == "train", "training pairs require train")
    require(episode.uid == candidate.episode_uid == target.episode_uid, "pair identity mismatch")
    require(candidate.target.shape == episode.target.shape and len(target.values) == episode.horizon, "pair shape mismatch")
    return {"pair_id": episode.uid, "X_raw": episode.target, "X_governed": candidate.target,
            "Y_common": target.values, "Y_common_hash": array_hash(target.values),
            "test_input_hash": array_hash(raw_test_context)}
