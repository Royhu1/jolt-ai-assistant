---
name: vehicle-onboarding
description: |
  Onboard a new vehicle into the JOLT report generator. Use when the user
  provides a new vehicle registration that is not yet in vehicles.json.
  Triggers on:
  (1) "add vehicle <reg>", "onboard <reg>", "configure <reg>"
  (2) "new vehicle <reg>"
  (3) "/vehicle-onboarding <reg>"
  Queries SRF API for vehicle metadata, inspects raw telematics data columns,
  configures vehicles.json/pipelines.json/plot_config.json, generates an initial
  report (with inspect HTML), runs param-tuner to optimise segmentation, and then
  ORCHESTRATES the downstream artefacts — weather backfill, the data-availability
  dashboard, and data-collection-monitor registration — by INVOKING the existing
  skills rather than re-implementing them. Handles both EV and DIESEL vehicles.
---

# Vehicle Onboarding — Router

Onboard a new vehicle into the JOLT report pipeline: from SRF API discovery
to validated segmentation parameters.

This skill is split into two layers (pattern adapted from nature-skills/nature-figure):

- A **static layer** under `static/` holding versioned, reusable content fragments: the
  six-phase workflow, the interaction contract, and a per-vehicle-type quick-start.
- A **dynamic layer** (this file plus `manifest.yaml`) that resolves the vehicle's energy
  type and loads only the fragment the current onboarding needs. The SRF discovery code
  and the case-study template live in on-demand `references/`.

Do not onboard from memory or from this router alone. Always load the fragments from disk
as described below. **The onboarding contract is fixed**: the phases, the config files
written, and the user decision points are exactly those in `static/` — this refactor
changes how the skill is organised, never what an onboarding does.

## Routing protocol

Follow these five steps every time the skill is invoked.

### 1. Load the manifest and the core layer

Read [manifest.yaml](manifest.yaml). It declares the `vehicle-type` axis, the two
blocking gates, and the on-demand reference table.

Also read every file listed under `always_load`:
[static/core/workflow.md](static/core/workflow.md) (the six-phase workflow:
Discovery → Configuration → Initial report → Parameter tuning → Downstream
artefacts orchestration → Finalize) and
[static/core/interaction-contract.md](static/core/interaction-contract.md)
(mode selection, the decision-points table, and the guidelines — numbered
selectable options for every user-facing question). These apply to every run.

### 2. Resolve the gates — run mode and new registration

- **Interaction mode** (blocking, at start): present Guided vs Auto per the
  interaction contract. Default: Guided mode.
- **New registration** (blocking): this skill is for a registration NOT yet in
  `vehicles.json`. If `<REG>` is already configured, the vehicle is already
  onboarded — stop and confirm with the user what they actually need.

### 3. Resolve the vehicle type and load the matching fragment

The axis value comes from SRF metadata during Phase 1 (`fuel` field) — read it,
never guess from make/model. Load the fragment before Phase 2 §2.1:

- **`ev`** (SRF `fuel` ≠ DIESEL) — speed/SOC segmentation branch question, then
  §2.2 pipeline configuration.
  → Read [static/fragments/vehicle-type/ev.md](static/fragments/vehicle-type/ev.md).
- **`diesel`** (SRF `fuel` = DIESEL) — no branch question: SRF-Logger J1939
  channel mappings, reuse `daf_diesel_logger`, jump to §2.4.
  → Read [static/fragments/vehicle-type/diesel.md](static/fragments/vehicle-type/diesel.md).

Do not load the other type's fragment.

### 4. Execute the six-phase workflow using the loaded material

Apply in this order: interaction contract (numbered options at every decision
point) → the core workflow phase by phase → the vehicle-type fragment at Phase 2
§2.1. Phases 3 and 5 ORCHESTRATE the owning skills (`/generate-excel-report`,
`/param-tuner`, weather patch, `/generate-data-dashboard`,
`/data-collection-monitor`) — never re-implement their logic here.

### 5. Reach for references only when needed

Open files under `references/` on demand per the manifest table:
[srf-discovery.md](references/srf-discovery.md) for the Phase 1 SRF API snippets
and the raw-telematics column checklist,
[case-study-template.md](references/case-study-template.md) when writing the
Phase 6 `references/{reg}.md` case study, and the per-vehicle worked examples
([T88RNW.md](references/T88RNW.md), [TA70WTL.md](references/TA70WTL.md),
[YT21EFD.md](references/YT21EFD.md)) when onboarding a similar vehicle.

After Phase 6, report the written config entries, artefact paths and case-study
path to the user.

## Why this split

- The workflow and the interaction contract are versioned, always-loaded, and no longer
  buried in one long SKILL.md — the rules that must never drift are the ones that always load.
- Each invocation stays cheap: only the actual vehicle type's quick-start enters context,
  and the SRF code / case-study depth loads only when a phase needs it.
- The router itself is short on purpose. Update fragments and references, not this file,
  when adding scope.
- This structure mirrors nature-figure's static/dynamic split, adapted to the JOLT skill
  anatomy v2 (`README.md` + `manifest.yaml` + `references/` per
  `.claude/rules/skill-design.md`); the human-facing map + pipeline live in `README.md`.
  Per-vehicle onboarding experience accumulates in `references/<REG>.md` case studies —
  this skill deliberately has no separate `evaluations/` directory.
