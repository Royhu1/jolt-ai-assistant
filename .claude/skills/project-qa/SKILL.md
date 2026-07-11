---
name: project-qa
description: |
  Read-only Q&A agent for the JOLT project. Answers questions about the project
  without making any code or config changes. Use when the user asks about:
  (1) Which vehicles/operators have data collected, and for what date ranges
  (2) What reports have been generated and their status
  (3) Pipeline configurations and algorithm parameters for specific vehicles
  (4) Simulation experiment results and findings
  (5) Fleet overview, vehicle specifications, operator assignments
  (6) Recent changes (changelog entries)
  Triggers on: "what vehicles", "which operators", "what data", "tell me about",
  "project overview", "fleet status", "report status", "/project-qa"
---

# Project Q&A — Router

This skill is split into two layers (pattern adapted from nature-skills/nature-figure):

- A **static layer** under `static/` holding the one contract that applies to every
  interaction: the strict read-only constraint, the mandatory Step-0 language
  preference and the presentation guidelines.
- A **dynamic layer** (this file plus `manifest.yaml`) that clears the language gate,
  classifies the question, and loads only the reference material the current question
  needs. This skill has no genuine mode branch, so it has no axes and no
  `static/fragments/` (proportionality rule, `.claude/rules/skill-design.md`).

Do not answer from memory or from this router alone. Always load the material from
disk as described below. **The behaviour is contract-fixed**: strictly read-only, with
the Step-0 language choice on every interaction — this refactor changes how the skill
is organised, never how it answers.

## Routing protocol

Follow these four steps every time the skill is invoked.

### 1. Load the manifest and the core layer

Read [manifest.yaml](manifest.yaml). It declares the always-load core contract, the
blocking language-preference gate, and the on-demand reference table (no axes).

Also read the file listed under `always_load`:
[static/core/read-only-contract.md](static/core/read-only-contract.md) — the strict
read-only constraint, the mandatory Step-0 language preference, and the presentation
guidelines. It applies to every question.

### 2. Clear the language gate — blocking

Before answering any question, present the response-language options exactly as
written in the core contract's Step 0 (Chinese default / English / other) and wait
for the user's reply (or proceed with Chinese if they don't respond / reply with a
number). Then answer in the chosen language.

### 3. Classify the question and load the matching references

Classify the question into one of the eight known categories: fleet overview,
data-collection date ranges, generated-report status, pipeline/algorithm parameters,
vehicle specifications, simulation results, recent changes (changelog), or package
version/branch. Then open the references on demand per the manifest table:

- [references/data-sources.md](references/data-sources.md) — the read-only map of
  where every project fact lives (configs, reports, test ranges, simulation,
  changelog, version, architecture docs).
- [references/question-categories.md](references/question-categories.md) — the
  per-category answer recipe (which source to read, what to show, in what shape).

### 4. Answer per the presentation guidelines

Apply the core contract: lead with the direct answer, use tables for multiple
vehicles/parameters, include units, say so clearly when data is unavailable — and
decline any change request per the strict read-only constraint.

## Why this split

- The rules that must never drift — the strict read-only constraint and the mandatory
  Step-0 language preference — are the ones that always load (`static/core/`).
- Each invocation stays cheap: the data-source map and the category recipes enter
  context only when a question needs them.
- The router itself is short on purpose. Update the core contract and references, not
  this file, when adding scope (a ninth question category = one new recipe).
- This structure mirrors nature-figure's static/dynamic split, adapted to the JOLT
  skill anatomy v2 (`README.md` + `manifest.yaml` + `references/` per
  `.claude/rules/skill-design.md`); the human-facing map + pipeline live in
  [README.md](README.md).
