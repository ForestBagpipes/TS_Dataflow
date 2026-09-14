"""Complete-origin development summaries; failures make a comparison invalid."""
import numpy as np
from .schemas import require


def aggregate(expected_uids, rows):
    require(len(set(expected_uids)) == len(expected_uids) > 0, "invalid origin registry")
    uids = [r["episode_uid"] for r in rows]
    require(len(set(uids)) == len(uids) and set(uids) == set(expected_uids), "denominator mismatch")
    failures = [r["episode_uid"] for r in rows if r["status"] not in ("completed", "unscorable_future")]
    summary = {"n_origins": len(expected_uids), "failed_origins": failures,
               "unscorable_origins": [r["episode_uid"] for r in rows if r["status"] == "unscorable_future"]}
    if failures:
        return dict(summary, status="failed", mean_task_gain=None)
    valid = [r for r in rows if r["status"] == "completed"]
    require(all(np.isfinite(r["task_gain"]) for r in valid), "invalid completed metric")
    return dict(summary, status="completed", mean_task_gain=(float(np.mean([r["task_gain"] for r in valid])) if valid else None))
