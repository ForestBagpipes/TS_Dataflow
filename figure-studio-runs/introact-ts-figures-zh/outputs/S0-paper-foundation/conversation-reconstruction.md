# Conversation reconstruction

## User objective

Create two Chinese academic-paper figures for IntroAct-TS, each delivered as a high-resolution PNG and an editable PPTX.

## Source material

- `paper/01_introduction.zh.md`
- `paper/03_method.zh.md`
- `docs/code_overview.md`
- `docs/claims.md`
- User-provided pasted figure prompts
- Two user-provided system-architecture reference images

## Decisions recorded so far

- Use the hybrid interpretation: retain a four-stage horizontal rhythm while making the current paper's execution-time acceptance layer the visual center; policy learning is supporting feedback rather than an overstated primary contribution.
- Selected layout direction A: a simple two-case motivation figure and a detailed compact academic system figure.
- Figure 1 is simpler than Figure 2.
- All labels are Chinese except necessary method acronyms and mathematical symbols.
- All module containers are square-corner rectangles; rounded rectangles are forbidden.
- Strict grid alignment and regular spacing are mandatory.
- Chinese font: Microsoft YaHei.
- English font: Calibri.
- Mathematical formulas: Cambria Math.
- Same hierarchy must use the same font size; never shrink one item independently to fit.

## Current open decision

Whether to deliver one two-slide PPTX, two separate one-slide PPTX files, or both.
