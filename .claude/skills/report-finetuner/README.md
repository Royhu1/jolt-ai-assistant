# report-finetuner — slash-command shortcut for the report-finetuner agent

> A thin slash-command trigger that launches the `report-finetuner` agent, which does
> vision-driven segmentation corrections producing `*_finetuned` artefacts.
> This README is the skill's human-facing single source of truth; `SKILL.md` is the
> agent-facing router over `manifest.yaml`.

**Invoke:** `/report-finetuner <REG> <period>` · **In:** the period's `jolt_report_*.xlsx` +
its `validation_*.png` · **Out:** `*_finetuned.xlsx` + overlay `*_finetuned.png` +
`inspect_*_finetuned.html` (originals never overwritten)

## Directory map

```
report-finetuner/
├── SKILL.md            # router: routing protocol only (agent entry point)
├── manifest.yaml       # always_load (handoff contract) + on-demand reference table; no axes / gates
├── README.md           # this file — human-facing map + pipeline
├── code/
│   └── finetune.py     # the finetune core library (canonical home since v3.1.0; moved from the package)
├── static/
│   └── core/           # handoff-contract.md (always loaded): agent launch call + why-an-agent + never-overwrite discipline
├── references/         # related-resources.md (on demand) + per-vehicle case studies {REG}.md
└── evaluations/        # per-run logs {REG}_{period}_finetune_log.md
```

> Content ownership: the `report-finetuner` **agent** (not this skill) writes
> `references/{REG}.md` and the `evaluations/` logs at the end of each run — they are the
> agent's cross-session memory; the skill only points to them.

## Pipeline

1. **Route** — the skill itself only launches the `report-finetuner` agent (via `Agent`,
   `subagent_type="report-finetuner"`) with the registration + period; all real work happens
   in the agent's isolated context.
2. **Agent (0) locate** — find the xlsx/figures and read prior `references/{REG}.md` +
   `evaluations/` logs.
3. **Agent (1) diagnose** — visually inspect every validation figure across the period to find
   multi-split / miss-split / false-positive segments (single-operation mode skips this sweep).
4. **Agent (2) plan** — propose a list of `MergeOp` / `SplitOp` / `DeleteOp`.
5. **Agent (3) apply** — run the skill-owned finetune library
   (`code/finetune.py`, imported with this skill's `code/` on `sys.path`) to write
   the `*_finetuned.xlsx`, then regenerate overlay figures + inspect HTML.
6. **Agent (4) log** — write the `evaluations/{REG}_{period}_finetune_log.md` and update the
   `references/{REG}.md` case study.

The authoritative four-phase workflow definition lives in
`.claude/agents/report-finetuner.md` — this pipeline is the summary, the agent file is the
contract.

**Why an agent:** context isolation (reading tens of PNGs), cross-session memory, and forced
two-layer logging. **Owner:** since v3.1.0 the core library's canonical home is this skill's
`code/finetune.py` (moved out of the `jolt_toolkit` package; it still imports package names —
HEADERS, segmentation constants — read-only, and its figure/HTML regeneration will delegate
to the `report-visuals` CLI in P2b); the agent definition is
`.claude/agents/report-finetuner.md`. Use after `/param-tuner` is exhausted but figures
still show segmentation errors.
