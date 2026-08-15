# Locked terminology, English and Chinese

No `materials` directory exists in this repository. The locked vocabulary is
therefore taken from what is already used across `src/introact_ts/` and
`docs/`, with frequency counts from those files. Nothing here is coined for the
paper.

Two rules that apply everywhere. No borrowed method name appears in the body
text, so a competing system is described by its mechanism rather than named in
a sentence that could read as a comparison of names. And no dashes, no
semicolons and no curly quotes, in either language.

| English | 中文 | source |
|---|---|---|
| curation | 治理 | 27 uses |
| structural distance | 结构距离 | 17 uses |
| proposer | 提议者 | 17 uses |
| statistical profile | 统计画像 | 12 uses |
| sandbox | 沙箱 | 11 uses |
| model utility | 模型效用 | 11 uses |
| acceptance rule | 接受规则 | 11 uses |
| rollback | 回滚 | 9 uses |
| behavioural risk | 行为风险 | 7 uses |
| protected stratum | 受保护层 | 6 uses |
| execution time | 执行时 | 4 uses |
| governance trace | 治理轨迹 | 3 uses |
| verifier | 验证器 | 2 uses |
| acceptance layer | 验收层 | composed from acceptance rule |
| damage | 损害 | metric name in results |
| repair | 修复 | metric name in results |
| frozen forecaster | 冻结预测器 | probe.py |
| contamination | 污染 | corpus.py stratum name |

## Terms deliberately not used

**Shield.** Descriptive of the mechanism and used in `docs/shield_properties.md`
for internal discussion, but it is a term of art from another literature and
carries commitments the paper does not make. The body text says acceptance
layer.

**Agent.** The system does act in a loop, and calling it an agent invites
comparison with systems whose contribution is the search policy. Ours is the
acceptance rule, and the search is one instance. Used only where the loop
itself is being described.

**Guarantee, unqualified.** Always paired with what it is conditional on.
Exchangeability is required and its violation was measured at 20 to 50 percent
relative overshoot.
