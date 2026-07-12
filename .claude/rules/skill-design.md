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
> Anatomy v2 (2026-07-11): adopted nature-figure's **router / static-dynamic split** for
> every skill — short `SKILL.md` router + declarative `manifest.yaml` + always-loaded
> `static/core/` contracts + exactly-one-loads `static/fragments/` + on-demand
> `references/`; the former per-skill `PIPELINE.md` was absorbed into each skill's
> `README.md` ("Pipeline" section).

## Shared design principles

All skills, commands and agents in `.claude/` follow these principles. Each states its
*why* — a rule whose reason is lost cannot be safely evolved later (by humans or AI).

1. **Single source of truth, progressive disclosure.** Every level's `README.md` owns that
   level's structure; a `SKILL.md` is a lean router that loads deeper material
   (`manifest.yaml`-declared core contracts, mode fragments, `references/`, per-vehicle
   notes) only when needed. *Why:* the always-loaded context stays cheap, and facts live
   in exactly one place so they cannot drift apart.
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

## Anatomy of a skill (v2 — router / static-dynamic split)

Every skill is split into two layers (pattern adapted from nature-figure):

- A **static layer** under `static/` holding versioned, reusable content fragments — the
  contracts that must never drift (`static/core/`, always loaded) and per-choice
  quick-starts (`static/fragments/<axis>/`, exactly one loads per run).
- A **dynamic layer** (`SKILL.md` + `manifest.yaml`) that resolves the run's axis value
  and loads only what the current job needs. Deep material lives in on-demand
  `references/`.

*Why:* the always-loaded context stays cheap and version-reviewable; contract-grade rules
stop being buried mid-file in a monolithic SKILL.md; adding scope means adding fragments
or references, not growing the router.

Minimum files for `.claude/skills/<name>/`:

| File | Required | Purpose |
|------|----------|---------|
| `SKILL.md` | required | Frontmatter (`name`, `description` with enumerated triggers) + the **routing protocol only** (load manifest → always-load core → resolve axes/gates → load one fragment → on-demand references). No deep content; update fragments and references, not the router, when adding scope. |
| `manifest.yaml` | required¹ | Declarative loading contract: `version` (per-skill SemVer, bumped on every skill edit — see `git-workflow.md`), `always_load` (core contracts), `axes` (per-axis `detect` rule + `values` → fragment paths), `gates` (blocking preconditions), `references.on_demand` (condition → path table). |
| `README.md` | required¹ | The skill's human-facing single source of truth: what it is, directory map, how to run, artefact paths, and a **Pipeline** section (data in → processing → artefacts out, ownership, neighbouring skills — absorbed from the former per-skill `PIPELINE.md`). |
| `static/core/` | as needed | Always-loaded contracts: style / persistence / discipline rules that apply to every run of the skill. |
| `static/fragments/<axis>/` | as needed | One file per axis value (mode, vehicle type, …); exactly one loads per run. Skills with no genuine branch simply omit `axes`. |
| `references/` | recommended | Modular deep knowledge loaded on demand (per-vehicle notes, style guides, API docs). |
| `evaluations/` | recommended² | Per-run experience / regression evidence (what was tried on which vehicle, what worked). |
| scripts / `templates/` | as needed | Code and templates the skill drives; self-contained in the skill dir. |

¹ Vendored third-party skills (e.g. `html-artifacts`) are exempt: they keep their
  `UPSTREAM_README.md` instead and are listed in the checker's vendored set.
² Follow the pattern already set by `param-tuner/evaluations/` and
  `report-finetuner/evaluations/`.

**Proportionality rule:** the split scales with the skill. A 70-line CLI wrapper gets a
short router, a minimal manifest (`always_load` + `references.on_demand`, no axes) and a
small core file — do not manufacture empty fragments or padding references to look
complete. A monolith the size of the old 475-line `generate-pdf-report` SKILL.md is
exactly what the split exists to break up.

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

`manifest.yaml` template (axes and gates only where a genuine branch/precondition exists):

```yaml
name: <kebab-case-name>
version: X.Y.Z   # per-skill SemVer — bump on EVERY edit to the skill's files
                 # (patch = doc fix, minor = new fragment/reference/capability,
                 #  major = breaking invocation/axes/output change); rules in
                 # .claude/rules/git-workflow.md "Per-skill versions"
description: >
  Declarative manifest for the static/dynamic split. SKILL.md uses this to
  decide which fragments to load for a given request.

always_load:
  - static/core/<contract>.md

axes:
  <axis-name>:               # e.g. mode, vehicle-type
    detect: |
      <How to resolve the value: default, explicit user choice, or a blocking
      question. State what happens when ambiguous.>
    values:
      <value-a>: static/fragments/<axis-name>/<value-a>.md
      <value-b>: static/fragments/<axis-name>/<value-b>.md
    multi: false

gates:
  <gate-name>: |
    <BLOCKING precondition and how to resolve it (ask user / hand off to
    another skill), e.g. output destination, vehicle configured, xlsx exists.>

references:
  on_demand:
    - condition: <when to open it>
      path: references/<file>.md
```

The exemplar conversion is `plot-figure/` — read it before restructuring or creating a
skill.

## Adding a new skill / command / agent

1. Create the directory / file under `.claude/skills/` (or `commands/`, `agents/`)
   following the anatomy above (router `SKILL.md` + `manifest.yaml` + `README.md`;
   `plot-figure/` is the exemplar); kebab-case name per `naming.md`.
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
- every skill dir contains `SKILL.md`, and `manifest.yaml` + `README.md` unless in the
  vendored set;
- every `manifest.yaml` declares a valid SemVer `version:` (per-skill versioning, see
  `git-workflow.md`).

Run it after touching anything under `.claude/skills|commands|agents` or the README index
tables (exit 1 on violation, same contract as `check_subproject_independence.py`).
