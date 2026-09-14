# Role stratified conformal risk control for tool calls

arXiv 2607.24343, first public 2026-07-27, revised 2026-07-31. Rahman, Rahman,
Samin, Tasnia, Amin, Ahona, Noshin. **Concurrent with a 2026-09-24 submission,
two months prior. Treated as concurrent and still distinguished explicitly.**

## What it does

Calibrates per field rather than per call. A tool call has several semantic
argument roles, and their consequences differ by orders of magnitude: untrusted
content may legitimately shape an email body and must never set a recipient, an
account, a command or a credential. The method assigns an independent risk
threshold to each role and calibrates per field detectors separately, rather
than averaging risk across the whole call.

Evaluated on AgentDojo and InjecAgent across six language models.

## What it shares with this work

**The refusal of an aggregate.** Their argument is that a single budget over a
whole tool call hides the fields where harm concentrates. Ours is that a single
number over a whole corpus hides the stratum where damage concentrates, which
is why every table here is reported by protected stratum and by generator form,
and why we report that the same aggregate can be one stratum wearing a
disguise.

That is a real convergence and it is worth saying so, since two teams arrived
at stratification from unrelated starting points.

## Where it differs

**Stratification is over consequence, ours is over the failure of the signal.**
They stratify because harm is unevenly distributed across argument roles, which
is a property of the task. We stratify because the verifier's error is unevenly
distributed across data types, which is a property of the instrument. Their
recipient field is dangerous no matter what any detector says. Our clean but
unpredictable windows are safe, and the instrument says otherwise.

**The premise, again.** The per field detectors are assumed to detect. The
calibration allocates budget across them and does not ask whether one of them
is anti correlated with the harm it is supposed to catch. In our setting that
is precisely what happens.
