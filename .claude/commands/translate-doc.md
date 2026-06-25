---
description: Bidirectional doc localisation between an English canonical `.md` and its Chinese `.zh.md` copy. Pass the file you just edited; it regenerates the other side.
argument-hint: <path/to/README.md | path/to/README.zh.md>
allowed-tools: Read, Write, Glob
---

# Translate Doc — bidirectional README localisation

You translate ONE documentation file between its **English canonical** form (`<name>.md`)
and its **Chinese copy** (`<name>.zh.md`). The user passes the file they just edited; you
regenerate the *other* side so the pair stays in sync.

## Input

Target file: `$ARGUMENTS`

If `$ARGUMENTS` is empty, ask the user which file to translate and stop.

## Step 1 — Determine direction and the output path

Inspect the input filename:

- Ends with `.zh.md` (or the legacy `_zh.md`) → **source is Chinese**, translate **into English**.
  Output = the same path with the Chinese suffix stripped (`<name>.zh.md` → `<name>.md`,
  `<name>_zh.md` → `<name>.md`).
- Otherwise ends with `.md` → **source is English**, translate **into Chinese**.
  Output = `<name>.md` → `<name>.zh.md` (always the **dot** form — it matches `.gitignore`
  and the existing copies; never emit `_zh.md`).
- Anything else → stop and tell the user it is not a Markdown doc.

Read the source file to confirm it exists. If it does not, stop and report.

## Step 2 — Translate faithfully

Read the FULL source file, then produce the output as a faithful translation.

Translation rules (be faithful, not creative):
- Translate ONLY natural-language prose. English target → **British English** (analyse,
  optimise, behaviour, normalise, colour, centre …). Chinese target → **Simplified Chinese**.
- Do NOT change, drop, summarise, reorder, or add anything. Every section, heading, table
  row, list item, code block and directory-tree line must be present, in the same order.
- Keep IDENTICAL: all Markdown structure (headings, tables, code fences, blockquotes,
  lists), all code/commands inside fences, file paths, relative links, URLs, `@import`
  lines, vehicle registrations (e.g. YK73WFN), version numbers (e.g. v2.2.3), units, numbers.
- Keep embedded technical terms as-is (EP, telematics, leg, segment, SOC, Crr/CdA, OEM,
  FPS, SRF, HEADERS, η_BM …).
- Do NOT add any "translated by" banner or extra commentary.

## Step 3 — Write and report

Overwrite the output file with the translation, then report:
- direction (zh→en or en→zh),
- `source path → output path`,
- one line confirming the structure (headings/tables/code/links) was preserved.

Reminder: the Chinese `.zh.md` copies are gitignored; the English `.md` is the committed
canonical version.
