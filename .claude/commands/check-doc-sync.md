---
description: Check whether multi-language doc pairs (`<name>.md` ↔ `<name>.zh.md`) are content-consistent; list any out-of-sync pairs with specifics and prompt the user to align (read-only, never edits).
argument-hint: <path/to/file | all>
allowed-tools: Read, Glob, Grep
---

# Check Doc Sync — multi-language consistency check

You verify that bilingual documentation pairs are **content-consistent**: each English
canonical `<name>.md` and its Chinese copy `<name>.zh.md` should carry the *same information
and structure* (only the prose language differs). You **report** mismatches and tell the user
to align them — you **never edit** any file.

## Input

Target: `$ARGUMENTS`

- `all` → check **every** bilingual pair in the repository.
- a file path (either side of a pair) → check just that one pair.
- empty → default to `all`.

## Step 1 — Resolve the pairs to check (BOTH directions — do not skip either)

Under `all` you MUST scan in **both directions** so missing translations cannot slip through —
this is the most common real defect, so make it a first-class check, not an afterthought:

1. **Existing copies → check canonical exists**: `Glob **/*.zh.md` and (legacy) `**/*_zh.md`.
   For each, the canonical side is the same path with the Chinese suffix stripped
   (`<name>.zh.md` → `<name>.md`, `<name>_zh.md` → `<name>.md`). If a `.zh.md` has **no**
   sibling `.md`, it is an **orphan** (copy without a canonical) → **reported finding**.
2. **Canonicals → check copy exists**: `Glob **/README.md` (and any other canonical `.md` you
   are checking). If a `README.md` has **no** `README.zh.md` sibling, that is a
   **reported finding** ("missing Chinese version") — the project keeps every `README` bilingual.
   (For non-`README` `.md` files, a missing `.zh.md` is informational, not a failure — not every
   doc is translated.)

Skip anything under `.git/`. For a single path argument: derive the other side (strip or add
the Chinese suffix) and check just that pair (including whether the counterpart exists at all).

## Step 2 — Compare each pair (read BOTH files)

The two sides are in different languages, so do **not** diff prose text. Compare the
**language-invariant skeleton and facts**, which must match:

- **Heading skeleton** — the count, nesting level, and order of `#` / `##` / `###` sections.
  Each section on one side should have a corresponding section on the other (1:1, same order).
- **Fenced code blocks** — same number of ``` blocks, and their contents (commands, code, the
  repo-layout tree) should be effectively identical.
- **Tables** — same number of tables and the same row/column counts per table.
- **Links / file paths / URLs** — the set of paths and links should match.
- **Hard facts** — version numbers (`vX.Y.Z`), vehicle registrations (e.g. `YK73WFN`),
  numbers, units: these must be identical on both sides.
- **Gross size** — a large length disparity is a strong hint that a section was added on one
  side but not the other.

Flag, per pair, any of: a section/heading present on one side but missing on the other; a
differing number of tables or table rows; a differing set of code blocks; divergent
numbers / paths / links; an orphan copy.

## Step 3 — Report (read-only)

Print a concise result with **all four** sections below — never omit the "Missing translation"
section, even when it is the only problem (a `README` with no copy is a real defect, not a
footnote):

- **❗ Missing translation (MANDATORY section)** — every `README.md` that has **no**
  `README.zh.md`, and every `.zh.md` orphan that has no canonical `.md`. List each path
  explicitly. If there are none, state "none" — but you must show this section.
- **✗ Out of sync** — for each pair that exists on both sides but differs, a short bullet list
  of the *specific* discrepancies (e.g. "`README.zh.md` is missing the `## Environment setup`
  section", "table in §Layout has 14 rows vs 13", "version `v2.2.3` on EN vs `v2.2.4` on ZH").
- **✓ In sync** — list pairs that match (one line each).
- **(info) Untranslated non-README `.md`** — optional note of canonical `.md` (not README)
  lacking a `.zh.md`; informational only.

End with the fix hint: create any missing `README.zh.md` (or canonical `.md`) and, for each
out-of-sync pair, edit the authoritative side (usually the one just changed) and run
**`/translate-doc <that side>`** to regenerate the other, or align manually. Do **not** modify
any file yourself.
