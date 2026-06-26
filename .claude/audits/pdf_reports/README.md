# .claude/audits/pdf_reports/ — PDF-briefing data-audit records

Maintained by the `pdf-report-auditor` agent (see `../../agents/pdf-report-auditor.md`), used to
accumulate experience across successive audits of the partner-facing briefings in
`pdf_report_workspace/output/`. Committed to git with `.claude/`, shared by the team.

## Contents

| File | Purpose |
|------|------|
| `LESSONS.md` | Accumulated check recipes, verified facts, KNOWN & ACCEPTED limitations (do not re-flag), and traps — **read first** at the next audit |
| `audit_<YYYYMMDD>.md` | One report per audit: per-vehicle verdicts, every flag with evidence, accepted-as-expected items, open to-dos |

## The closed loop of each audit

1. Before starting, read `LESSONS.md` + the most recent `audit_*.md` + the skill's `SKILL.md` §1 + project memory.
2. Re-derive every briefing number INDEPENDENTLY from `raw_telematics/` + the xlsx (not from the
   generator's own output), per the SOP checklist in the agent definition.
3. At wrap-up, write a new `audit_<YYYYMMDD>.md`, and append reusable experience to `LESSONS.md` after de-duplicating.

> The briefing numbers go to industrial partners — the audit bias is toward over-checking. A number
> is "verified" only when an independent pandas re-derivation from the raw source agrees with the PDF.
