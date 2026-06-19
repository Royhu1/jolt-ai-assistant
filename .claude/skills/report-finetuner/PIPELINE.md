# report-finetuner — Pipeline

> A thin slash-command trigger that launches the `report-finetuner` agent, which does
> vision-driven segmentation corrections producing `*_finetuned` artefacts.

**Invoke:** `/report-finetuner <REG> <period>` · **In:** the period's `jolt_report_*.xlsx` +
its `validation_*.png` · **Out:** `*_finetuned.xlsx` + overlay `*_finetuned.png` +
`inspect_*_finetuned.html` (originals never overwritten)

## Flow

1. **Route** — the skill itself only launches the `report-finetuner` agent (via `Agent`,
   `subagent_type="report-finetuner"`) with the registration + period; all real work happens
   in the agent's isolated context.
2. **Agent (0) locate** — find the xlsx/figures and read prior `references/{REG}.md` +
   `evaluations/` logs.
3. **Agent (1) diagnose** — visually inspect every validation figure across the period to find
   multi-split / miss-split / false-positive segments (single-operation mode skips this sweep).
4. **Agent (2) plan** — propose a list of `MergeOp` / `SplitOp` / `DeleteOp`.
5. **Agent (3) apply** — run `jolt_toolkit.report_generator.finetune` to write the
   `*_finetuned.xlsx`, then regenerate overlay figures + inspect HTML.
6. **Agent (4) log** — write the `evaluations/{REG}_{period}_finetune_log.md` and update the
   `references/{REG}.md` case study.

**Why an agent:** context isolation (reading tens of PNGs), cross-session memory, and forced
two-layer logging. **Owner:** the core library `finetune.py` belongs to `jolt-toolkit-dev`;
the agent definition is `.claude/agents/report-finetuner.md`. Use after `/param-tuner` is
exhausted but figures still show segmentation errors.
