# .claude/health_checks/ — Project Health-Check Records

Maintained by the `project-health-steward` agent (see `../agents/project-health-steward.md`),
used to accumulate experience across successive health checks. Committed to git along with `.claude/`, shared by the team.

## Contents

| File | Purpose |
|------|------|
| `LESSONS.md` | Accumulated experience / project conventions / pitfalls (de-duplicated, refined over time) — **read here first** at the next health check |
| `check_<YYYYMMDD>.md` | One report per health check: findings / actions taken / outstanding to-dos / unresolved issues |

## The closed loop of each health check

1. Before starting work, read `LESSONS.md` + the most recent `check_*.md` + project memory.
2. Carry out the health check item by item according to the SOP checklist in the agent definition.
3. At wrap-up, write a new `check_<YYYYMMDD>.md`, and append any reusable experience to `LESSONS.md` after de-duplicating.
