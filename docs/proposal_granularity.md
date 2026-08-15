# The acceptance layer is sensitive to proposal granularity

This is a design finding rather than a result in either direction. It is not
that the layer defeated a proposer, and it is not simply that the layer has a
weakness. It is a statement about where the layer applies, derived from a case
that made it visible.

## What happened

The iterative minimum repair proposer rewrites values in place across the whole
series, touching 93 percent of the points in a typical window. A candidate from
it is therefore a global edit and is judged with the global weight profile, the
same one the denoising operator receives. Almost every such candidate crosses
the structural threshold.

Of 108 candidates it produced, 106 were rejected. Damage fell from 0.2547 to
0.0000 and repair fell from +0.056 to -0.000 at the same time.

**The protection is real and the repair retention is not.** Reporting only the
first number would be a misrepresentation.

## The applicable range this establishes

The structural condition measures a compound of how much was changed and how
far the structure moved. It is therefore sensitive to the granularity at which
edits are proposed.

**The layer applies to proposers whose edits are localised.** Against a proposer
that rewrites an entire series point by point it degenerates towards rejecting
everything, which preserves the data and forgoes whatever repair that proposer
might have delivered.

This is a condition on deployment, stated as one, and it can be checked before
deployment by measuring the fraction of points a proposer rewrites.

## The comparison that makes it precise

Unconditional cleaning and iterative minimum repair are both aggressive, and
the layer responds to them in opposite ways.

| proposer | how it acts | gated outcome |
|---|---|---|
| unconditional cleaner | applies named operators inside each window, each with a declared footprint | net effect moves from -0.014 to +0.044, damage falls 97 percent |
| iterative minimum repair | rewrites every point of the window in place | 106 of 108 candidates rejected, damage to 0.0000, repair to -0.000 |

Both change a great deal. One does it through localised operators and survives
the gate with its repair mostly intact, and the other does it by rewriting
everything and is almost entirely refused. **The manner of the aggression, not
its magnitude, determines the response.** That is the direct evidence for the
granularity sensitivity above, and it is a sharper demonstration than either row
alone.

## What the main conclusion rests on

The speed constraint proposer accepted 15 of 47 candidates. A layer that
accepts some and rejects others on the same proposer is the evidence that it
discriminates rather than merely blocks, and the modularity conclusion is drawn
from that row together with the two in the earlier table.

The threshold is not adjusted to accommodate the whole series rewriter. It was
selected by a calibration procedure on held out data with the rule fixed
beforehand, and changing it here to improve one row would discard that.

## Note on the numbers above

These come from a link verification run on the offline surrogate backend and
are used here to establish the mechanism and its direction. The main table
figures come from the real backends and are produced separately.
