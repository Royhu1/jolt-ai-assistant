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
  (3) "修正分段 <REG>"
  (4) user says param-tuner exhausted but figures still show segmentation errors
---

# Report Finetuner (slash-command shortcut)

**This is only a thin trigger.** The real work is done by the `report-finetuner` agent
(see `.claude/agents/report-finetuner.md`).

## What the main conversation should do when triggered

Launch the `report-finetuner` agent immediately:

```python
Agent(
    subagent_type="report-finetuner",
    description="Finetune {REG} {period} report",
    prompt=(
        "Finetune the xlsx report for {REG} covering {start}~{end}. "
        "Full workflow: (0) locate inputs and check prior references, "
        "(1) visual diagnosis across all validation figures in the period, "
        "(2) propose MergeOp/SplitOp/DeleteOp list, (3) apply via finetune.py "
        "and regenerate overlay figures + inspect HTML, (4) finalize "
        "evaluations log and references case study. Follow the workflow in "
        "your agent definition."
    ),
)
```

## Why an agent rather than the skill doing it directly

- **Context isolation**: visual diagnosis often needs to read tens of PNGs; doing that in the
  main conversation would burn through context fast. The agent's separate context does not
  crowd the main conversation.
- **Cross-session memory**: the agent has its own `.claude/agent-memory/report-finetuner/`, so
  it can remember "what was previously fixed on this vehicle" and "typical pitfalls for this
  kind of OEM". A skill starts from scratch every time.
- **Traceability**: the agent is forced to write two layers of logs, `evaluations/` and
  `references/`, building a long-term asset.

## Related resources

- Agent definition: `.claude/agents/report-finetuner.md`
- Core library: `src/jolt_toolkit/report_generator/finetune.py` (maintained by `jolt-toolkit-dev`)
- Past case studies: `.claude/skills/report-finetuner/references/{REG}.md`
- Past logs: `.claude/skills/report-finetuner/evaluations/{REG}_{period}_finetune_log.md`

## User-side usage

No need to remember the agent name; any of the following phrasings triggers it:

- `/report-finetuner YK73WFN 20240601_20240901`
- "fix the segmentation on AV24LXK's early-2025 report"
- "merge rows 12 and 13 of YK73 for me" (single-operation mode; the agent skips the stage-1
  visual sweep)
