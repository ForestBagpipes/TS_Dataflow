"""Reassemble curated univariate windows into multivariate blocks.

The design this supports, stated plainly because it is a choice and not a
compromise. **Curation operates per channel and evaluation operates on
multivariate forecasting.** Data quality problems in this setting are
overwhelmingly within channel sensor faults, a stuck reading, a dropout, a
spike, a splice, so treating each channel separately is the right granularity
for the intervention. The downstream task these corpora exist to serve is
multivariate, so that is the granularity for the evaluation.

Reassembly is only possible when the corpus was built with
`sample_ett_window_groups`, which draws one position and takes every channel
there. The default sampler round robins over channel and position independently
and its groups cannot be completed.

Two properties this preserves and one it cannot.

Preserved: a channel that was cropped by a segmenting operator keeps its crop
offset, and the group is trimmed to the intersection of what survived, so no
channel is padded with values it never had.

Preserved: a channel that was left untouched appears exactly as it entered.

Not preserved: cross channel alignment after differing crops. If two channels in
a group are cropped by different amounts the intersection is shorter than either
and the block loses the head of one and the tail of the other. Groups where this
would leave too little are dropped and counted rather than silently padded.
"""

import numpy as np

#: A reassembled group must retain at least this many steps to be usable, since
#: the downstream pair builder needs context plus horizon.
MIN_BLOCK_LEN = 128

#: Minimum channels for a block to be worth forming. Groups are rarely complete:
#: the corpus builder shuffles its pool and draws only what each stratum needs,
#: so most positions contribute some of their channels and not all. Requiring
#: seven of seven discards almost everything, and under channel independent
#: modelling a block of four aligned channels is as usable as a block of seven.
MIN_CHANNELS = 3


def regroup(traces, windows, group_map, min_len: int = MIN_BLOCK_LEN):
    """Stack curated series back into (T, C) blocks, one per group.

    ``group_map`` maps a window id to (group_id, channel_index). It is passed in
    rather than read off the window because the window type carries no metadata
    field and this evaluation is not a reason to change a type the curation loop
    depends on. The corpus builder returns the map alongside the windows.

    Returns the curated blocks, the pristine blocks for scoring, and a report of
    what was dropped and why.
    """
    byid = {w.window_id: w for w in windows}
    groups = {}
    for t in traces:
        w = byid.get(t.window_id)
        if w is None or t.window_id not in group_map:
            continue
        gid, ci = group_map[t.window_id]
        groups.setdefault(gid, []).append((ci, t, w))

    blocks, pristine, report = [], [], {
        "groups_seen": len(groups), "dropped_incomplete": 0,
        "dropped_too_short": 0, "kept": 0, "crop_mismatch": 0,
    }
    if not groups:
        report["error"] = "no group metadata found, corpus was not built grouped"
        return blocks, pristine, report

    from collections import Counter
    report["channels_per_group"] = dict(
        Counter(len(v) for v in groups.values()))
    for gid, members in sorted(groups.items()):
        if len(members) < MIN_CHANNELS:
            report["dropped_incomplete"] += 1
            continue
        members.sort(key=lambda m: m[0])

        # Align on the intersection of what each channel kept. A crop removes a
        # prefix, so the common region starts at the largest offset and ends at
        # the shortest surviving tail.
        lo = max(int(getattr(t, "crop_offset", 0)) for _, t, _ in members)
        hi = min(int(getattr(t, "crop_offset", 0)) + len(t.final_series)
                 for _, t, _ in members)
        if len({int(getattr(t, "crop_offset", 0)) for _, t, _ in members}) > 1:
            report["crop_mismatch"] += 1
        if hi - lo < min_len:
            report["dropped_too_short"] += 1
            continue

        cur, pri = [], []
        for _, t, w in members:
            off = int(getattr(t, "crop_offset", 0))
            cur.append(np.asarray(t.final_series, float)[lo - off : hi - off])
            ref = w.clean_series if w.clean_series is not None else w.series
            pri.append(np.asarray(ref, float)[lo:hi])
        blocks.append(np.stack(cur, axis=1))
        pristine.append(np.stack(pri, axis=1))
        report["kept"] += 1

    report["block_shapes"] = dict(Counter(b.shape for b in blocks)) if blocks else {}
    report["total_channel_series"] = sum(b.shape[1] for b in blocks)
    return blocks, pristine, report
