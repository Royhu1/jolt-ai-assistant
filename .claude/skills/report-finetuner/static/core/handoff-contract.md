# Handoff contract (always load)

**This skill is only a thin trigger.** The real work is done by the `report-finetuner`
agent (see `.claude/agents/report-finetuner.md`) — this contract is the single path
every invocation follows.

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

## Never overwrite the originals

The agent's outputs are always separate `*_finetuned.*` siblings — `*_finetuned.xlsx`,
overlay `*_finetuned.png`, `inspect_*_finetuned.html` — and the originals
(`jolt_report_*.xlsx`, `validation_*.png`, `inspect_*.html`) are never overwritten
(canonical data is append-only, per `.claude/rules/skill-design.md` principle 6).
