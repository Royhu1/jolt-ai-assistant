---
name: report-finetuner
description: |
  Thin slash-command trigger (`/report-finetuner <REG> <yyyymmdd>_<yyyymmdd>`)
  for the `report-finetuner` agent. All actual work (visual diagnosis,
  operation planning, xlsx finetune, figure regeneration) is performed by
  the agent — this skill just routes the invocation.

  Triggers on:
  (1) "/report-finetuner <REG> <period>"
  (2) "finetune report for <REG>"
  (3) "fix segmentation <REG>"
  (4) user says param-tuner exhausted but figures still show segmentation errors
---

# Report Finetuner — Router (slash-command shortcut)

**This is only a thin trigger.** The real work is done by the `report-finetuner` agent
(see `.claude/agents/report-finetuner.md`). Per the proportionality rule in
`.claude/rules/skill-design.md`, this launcher has no axes, no fragments and no gates —
a single always-loaded handoff contract plus one on-demand reference. Do not perform
the finetune work in the main conversation; load the handoff contract from disk and
follow it.

## Routing protocol

Follow these three steps every time the skill is invoked.

### 1. Load the manifest and the core layer

Read [manifest.yaml](manifest.yaml). It declares the single always-load contract and
the on-demand reference table.

Also read the file listed under `always_load`:
[static/core/handoff-contract.md](static/core/handoff-contract.md) — the exact
`Agent(...)` launch call (substitute in REG + period), the "why an agent rather than
the skill doing it directly" rationale, and the never-overwrite `*_finetuned` output
discipline the agent's artefacts follow.

### 2. Hand off to the agent

There is no axis to resolve — every invocation follows the single path in the handoff
contract: launch the `report-finetuner` agent immediately with the vehicle
registration and report period. All actual work (visual diagnosis, operation
planning, xlsx finetune, figure + inspect-HTML regeneration, evaluations/references
logging) happens in the agent's isolated context.

### 3. Reach for the reference only when needed

Open [references/related-resources.md](references/related-resources.md) on demand per
the manifest table: pointers to the agent definition, the finetune core library, past
case studies / logs, and the user-side trigger phrasings.

## Why this split

- The handoff contract (launch call + rationale + never-overwrite discipline) is the
  one piece that must never drift, so it is the one piece that always loads.
- The router stays short on purpose: this skill is a launcher, not a workflow — adding
  scope means updating the contract or the agent definition, not growing this file.
- The human-facing map + pipeline live in [README.md](README.md), per anatomy v2 in
  `.claude/rules/skill-design.md`.
