# Related resources & user-side usage (on demand)

## Related resources

- Agent definition: `.claude/agents/report-finetuner.md`
- Core library: `.claude/skills/report-finetuner/code/finetune.py` (canonical home since
  v3.1.0 — moved from `src/jolt_toolkit/report_generator/finetune.py`; import it with the
  skill's `code/` dir on `sys.path`, `jolt_toolkit` importable for shared names)
- Past case studies: `.claude/skills/report-finetuner/references/{REG}.md`
- Past logs: `.claude/skills/report-finetuner/evaluations/{REG}_{period}_finetune_log.md`

## User-side usage

No need to remember the agent name; any of the following phrasings triggers it:

- `/report-finetuner YK73WFN 20240601_20240901`
- "fix the segmentation on AV24LXK's early-2025 report"
- "merge rows 12 and 13 of YK73 for me" (single-operation mode; the agent skips the stage-1
  visual sweep)
