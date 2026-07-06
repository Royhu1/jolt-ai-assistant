> Skill / command / agent design conventions — referenced from the root `README.md`
> "Commands / Skills / Agents" section (deliberately **not** `@import`-ed into `CLAUDE.md`:
> per the progressive-disclosure principle below, only the one-line summary lives in the
> always-loaded README; open this file when you actually create or restructure a skill).
> Editing here = editing the harness-design conventions for the whole project
> (team-shared, committed with `.claude/`).
>
> Provenance: adapted from the design philosophy of
> [nature-skills](https://github.com/Yuan1z0825/nature-skills) (shared design principles,
> status labels, minimum-file contract, add-a-skill procedure, `_shared/` layer), merged
> with the conventions this repository already practised (single-source READMEs, ownership
> routing, append-only artefacts, per-run experience logs).

## Shared design principles

All skills, commands and agents in `.claude/` follow these principles. Each states its
*why* — a rule whose reason is lost cannot be safely evolved later (by humans or AI).

1. **Single source of truth, progressive disclosure.** Every level's `README.md` owns that
   level's structure; a `SKILL.md` is a lean router that loads deeper material
   (`references/`, `PIPELINE.md`, per-vehicle notes) only when needed. *Why:* the
   always-loaded context stays cheap, and facts live in exactly one place so they cannot
   drift apart.
2. **Explicit beats implicit.** Rules state their reason, artefact paths are written out,
   trigger phrases are enumerated in the `description`. *Why:* an agent that knows why a
   rule exists can tell when the rule does not apply; a bare assertion invites cargo-cult
   copying.
3. **Output-first.** Every skill run ends in a directly usable artefact at a documented
   path (`.xlsx`, `.pdf`, `.png`, `.html`, a report `.md`) — never just advice. *Why:*
   artefact paths are the contract that downstream skills, audits and partners rely on.
4. **Single ownership, explicit routing.** Every directory / artefact / code area has
   exactly one owner (a skill or an agent, declared in its description); anyone else
   routes changes to the owner instead of editing in place. *Why:* two uncoordinated
   writers are how a partner-facing number silently forks.
5. **Self-contained and extensible.** A skill directory carries everything it needs;
   adding a new skill must not require editing existing skills. Content needed by ≥ 2
   skills is promoted to a shared layer (see `_shared/` below) — the docs analogue of the
   code rule-of-three. *Why:* skills stay individually replaceable, deletable and
   reviewable.
6. **Canonical data is append-only.** Never overwrite a canonical artefact: post-processing
   writes `*_finetuned.*` siblings, the report database only extends forward, cleanup
   archives rather than deletes. *Why:* partner-facing numbers must stay traceable to the
   run that produced them.
7. **Accumulate experience.** Skills and agents persist per-run knowledge next to
   themselves (`evaluations/`, `references/<REG>.md`, `.claude/audits/`,
   `.claude/health_checks/`). *Why:* cross-session memory is what turns a one-shot agent
   into an improving one.

## Status labels

Every entry in the README index tables (Commands / Skills / Agents) carries a status.
The README table is the **single source** of status — do not duplicate it in frontmatter.

| Label | Meaning (JOLT-specific) |
|-------|--------------------------|
| `Draft` | Rules/workflow written, but not yet exercised on real fleet data. |
| `Beta` | Has produced real artefacts on part of the fleet or few cases; edge cases (vehicle variants, data quirks) may remain. |
| `Stable` | Validated in routine use across the fleet / workspace; interface and outputs are relied on by other skills. |

Promote `Draft → Beta` on the first successful real-data run; `Beta → Stable` once it has
survived routine use broadly enough that others build on it. Demote when a regression or
redesign re-opens the contract.

## Anatomy of a skill

Minimum files for `.claude/skills/<name>/`:

| File | Required | Purpose |
|------|----------|---------|
| `SKILL.md` | required | Frontmatter (`name`, `description` with enumerated triggers) + the workflow the agent executes. Keep it a router: put deep content in `references/`. |
| `PIPELINE.md` | required¹ | Human-readable walk-through: data in → processing → artefacts out, ownership, neighbouring skills. |
| `references/` | recommended | Modular deep knowledge loaded on demand (per-vehicle notes, style guides, API docs). |
| `evaluations/` | recommended² | Per-run experience / regression evidence (what was tried on which vehicle, what worked). |
| scripts / `templates/` | as needed | Code and templates the skill drives; self-contained in the skill dir. |

¹ Vendored third-party skills (e.g. `html-artifacts`) are exempt: they keep their
  `UPSTREAM_README.md` instead and are listed in the checker's vendored set.
² Follow the pattern already set by `param-tuner/evaluations/` and
  `report-finetuner/evaluations/`.

`SKILL.md` frontmatter + description template:

```yaml
---
name: <kebab-case-name>
description: |
  <One paragraph: what it does, what artefact it produces and WHERE the output goes.>
  Triggers on:
  (1) "<natural-language trigger>"
  (2) "/<name> <args>"
  <Routing boundary: what this skill does NOT own and where to route that instead.>
---
```

## Adding a new skill / command / agent

1. Create the directory / file under `.claude/skills/` (or `commands/`, `agents/`)
   following the anatomy above; kebab-case name per `naming.md`.
2. Declare ownership and routing boundaries in the `description` (which agent owns
   neighbouring code, e.g. anything under `src/jolt_toolkit/` → `jolt-toolkit-dev`).
3. Add one row to the matching README index table: linked name, status (`Draft` for a
   brand-new skill), one-line purpose. Keep the row's purpose consistent with the
   `description`.
4. Run `python .claude/scripts/check_skill_registry.py` — it must pass.
5. If the skill produces a new artefact type or directory, record it in the naming /
   housekeeping rules and the relevant workspace `README.md`.

## `_shared/` layer (create on first real need)

When (and only when) **two or more skills** need the same reference content, move it to
`.claude/skills/_shared/` and reference it by relative path from each consumer. `_shared/`
is not a skill: it has no `SKILL.md` and must contain a `README.md` listing each file and
its consumers. Task-specific logic (how a skill diagnoses, generates or verifies) stays in
the skill; only shared *definitions and reference material* are promoted. Machine code
reused by 3+ consumers still goes to `jolt_toolkit.analysis` per the code rule-of-three —
`_shared/` is for prompt/reference content, not for importable Python.

## Registry consistency check

`python .claude/scripts/check_skill_registry.py [--verbose]` verifies the README index
tables against what actually exists under `.claude/`:

- every skill dir / command file / agent file has exactly one table row, and vice versa;
- every row's link resolves to an existing file;
- every status is one of `Draft` / `Beta` / `Stable`;
- every skill dir contains `SKILL.md`, and `PIPELINE.md` unless in the vendored set.

Run it after touching anything under `.claude/skills|commands|agents` or the README index
tables (exit 1 on violation, same contract as `check_subproject_independence.py`).
