# IntroAct-TS Chinese Figures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build two editable Chinese IntroAct-TS paper figures and export matching PNG files.

**Architecture:** A single JavaScript ES module defines shared typography, colors, square-corner module primitives, connectors, miniature time-series plots, and two slide-builder functions. The builder exports a combined deck and two one-slide decks, then exports PNG previews and layout metadata for verification.

**Tech Stack:** `@oai/artifact-tool`, bundled Node.js presentation runtime, presentation render/overflow helpers.

---

### Task 1: Prepare the artifact workspace

**Files:**
- Create: `.tmp/introact-ts-figures/build_figures.mjs`
- Create: `.tmp/introact-ts-figures/source-notes.txt`

- [ ] Load bundled workspace dependencies and create a local `node_modules` junction.
- [ ] Record source files and reference-image roles in `source-notes.txt`.
- [ ] Run the presentation artifact-operation marker exactly once for three PPTX outputs.

### Task 2: Build shared editable primitives

**Files:**
- Modify: `.tmp/introact-ts-figures/build_figures.mjs`

- [ ] Define the 1600×720 canvas, grid, palette, and font roles.
- [ ] Define editable rectangle, text, connector, block-arrow, time-series, and metric primitives.
- [ ] Enforce `geometry: "rect"` for every module container and equal typography by hierarchy.

### Task 3: Build Figure 1

**Files:**
- Modify: `.tmp/introact-ts-figures/build_figures.mjs`

- [ ] Construct two aligned example lanes: isolated artifact and real extreme event.
- [ ] Apply the same despiking operation to sandbox copies.
- [ ] Show utility improvement in both lanes and opposing structure/decision outcomes.
- [ ] Export the editable one-slide deck and PNG.

### Task 4: Build Figure 2

**Files:**
- Modify: `.tmp/introact-ts-figures/build_figures.mjs`

- [ ] Create aligned top stage bars and detailed stage bodies.
- [ ] Show evidence acquisition, copy-on-write sandbox, calibrated conjunctive acceptance, feedback, output, and governance trajectory.
- [ ] Give the acceptance stage the strongest visual hierarchy and include the Cambria Math acceptance formula.
- [ ] Export the editable one-slide deck and PNG.

### Task 5: Export and verify all outputs

**Files:**
- Create: `figures/IntroAct-TS_图1_示例图.pptx`
- Create: `figures/IntroAct-TS_图2_系统框架图.pptx`
- Create: `figures/IntroAct-TS_图1与图2_合并版.pptx`
- Create: `figures/IntroAct-TS_图1_示例图.png`
- Create: `figures/IntroAct-TS_图2_系统框架图.png`

- [ ] Run the builder with the bundled Node.js runtime.
- [ ] Render every final slide and inspect each image at full size.
- [ ] Run the slide overflow test on all three PPTX files.
- [ ] Fix clipping, wrapping, alignment, connector, or typography issues and rerun verification.
