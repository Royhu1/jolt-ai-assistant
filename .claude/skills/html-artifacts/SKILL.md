---
name: html-artifacts
description: |
  MANUAL TRIGGER ONLY: invoke only when user types /html-artifacts (or a
  Chinese equivalent like "write with html-artifacts" / "make it an html document").
  Produce a self-contained HTML artifact instead of a markdown document
  when the user explicitly requests an HTML deliverable — typically for
  content that benefits from spatial layout, color, real diagrams,
  interactivity, or a round-trip editor (docs, writeups, plans, specs,
  reports, explainers, comparisons, reviews, PR writeups, mockups,
  flowcharts, decks, status updates, post-mortems, playgrounds, one-off
  editors). Do NOT auto-trigger on generic "summarize / compare / explain"
  requests — those default to markdown unless the user invokes the skill.
  Before drafting, always ask the user which language to write in
  (English / Chinese / mirror the user's prompt).
---

# HTML Artifacts

Markdown is the default agent output, but for anything longer than a handful of sentences it's a poor format. It can't show two options side by side, can't render a real diagram, can't be interactive, and can't be shared by link. HTML can do all of those — and when the artifact is the deliverable rather than something you'll skim and forget, the difference between "a document I'd skim" and "a document I'd actually read" is enormous.

The use cases below are not the only places HTML helps, but they cover most of the territory. The pattern in every category is the same: the agent picks a layout that makes the *shape* of the content visible, instead of flattening it into linear prose.

## When to reach for HTML

This skill is **manually triggered** — the user has to explicitly invoke it
(e.g. `/html-artifacts`, "write a ... with html-artifacts", "make it an html document").
Once invoked, evaluate the request against the categories below to decide
what shape the HTML artifact should take. The categories are guidance for
*how* to lay out the artifact, not for whether to produce one.

Reach for the HTML format treatment described in each category when **any**
of the following is true:

- **Comparison.** Two or more options/approaches/designs the reader needs to weigh against each other. Side-by-side beats stacked.
- **Spatial information.** Diffs, call graphs, module maps, flowcharts, timelines, before/after — anything where position carries meaning.
- **Interaction matters.** Animations, easing curves, parameter tuning, state transitions — things the reader needs to *feel*, not read about.
- **Reference material.** A document the reader will navigate non-linearly: tabs, collapsible sections, glossary in the margin, jump links.
- **Color or hierarchy carries meaning.** Severity tags, status colors, syntax highlighting, design tokens.
- **One-off editor.** The reader needs to manipulate a thing (drag tickets, toggle flags, tune a prompt) and round-trip the result back into a prompt or a commit.
- **The reader will share it.** A spec going to leadership, a PR writeup going to reviewers, a status report going to a team. People are dramatically more likely to actually read an HTML page than a markdown file.
- **Length.** Anything longer than ~100 lines in markdown becomes hard to read. HTML's navigation and layout earn their keep past that threshold.

The heuristic, said another way: if the user is going to *do* something with the document — read it carefully, share it, refer back to it, hand it to an implementer, paste edits back in — make it HTML.

## When to stay in markdown

Markdown still wins for:

- Short conversational replies inside chat.
- Code-only outputs (a function, a config block, a one-liner).
- Terminal/command-flavored answers ("run this, then that").
- Quick three-bullet summaries the reader will scan once and discard.
- Files that need to be diffed in version control regularly. HTML diffs are noisy. If the artifact will live in git and be reviewed in PRs over time, markdown is friendlier — though even then, *generating* an HTML view alongside is often worth it for review.

If the artifact is going to be edited by hand by a human afterward, markdown is also friendlier. But increasingly artifacts are edited by re-prompting Claude, which removes that advantage.

## Before drafting: ALWAYS ask the user which language (mandatory)

This skill operates in mixed-language projects, so the natural-language locale
of the artifact is never assumed. **Before writing any of the HTML body**, you
must explicitly ask the user which language to write the artifact in.

**Procedure**

1. The moment you decide the answer is going to be an HTML artifact, and before
   you begin drafting the document body, call `AskUserQuestion` with:

   - **question:** "Which language should the HTML artifact be written in?"
   - **header:** "Artifact language"
   - **options** (single-select):
     - `English`  — All narrative content in English
     - `Chinese (Simplified)` — All narrative content in Simplified Chinese
     - `Same as the user's prompt` — Mirror the language the user just used

2. If `AskUserQuestion` is not available in the current environment
   (e.g. Claude.ai chat without the question tool), ask the same question
   inline as a short single sentence and wait for the user's answer before
   continuing.

3. **Only skip the question when the user has already given an explicit
   language directive in the very same request** — e.g. "make an English
   HTML report", "write an HTML plan in Chinese". In that case proceed directly,
   but still acknowledge the choice in one short sentence before drafting.

**Scope of the language choice**

The chosen language applies to **all natural-language content** in the
artifact, including but not limited to:

- `<title>` and `<h1>`/`<h2>`/`<h3>` headings
- Body prose, captions, list items, table cell text
- Button labels, tooltips, placeholder text
- Inline annotations on SVG diagrams
- Any "Copy as markdown / JSON / prompt" export labels

The chosen language does **not** apply to technical identifiers, which must
keep their original casing and form:

- Variable names, function names, class names, file paths, CLI commands
- Mathematical notation, units of measurement, ISO date strings
- Brand / product names
- Verbatim code inside `<code>` / `<pre>`
- Identifiers and labels that appear in source data the user provided

**Why this is mandatory.** Producing an artifact in the wrong locale is a
very expensive mistake to recover from — the user has to either re-prompt
the whole document or hand-edit every string. A two-second confirmation
question costs nothing compared to that cost.

## Universal rules for every HTML artifact

Every artifact this skill produces must satisfy all of these:

1. **Single self-contained `.html` file.** No build step, no bundler, no `npm install`. CSS goes in a `<style>` tag, JS goes in a `<script>` tag, images are inline SVG or data URIs.
2. **Works offline.** No required network calls at view time. If a CDN is used (Tailwind, a font, a library), prefer well-known stable CDNs and assume the user might want to swap to inlined later. For Claude Code outputs that may be archived or shared via S3, lean toward fewer external dependencies.
3. **Mobile responsive.** Include `<meta name="viewport" content="width=device-width, initial-scale=1">` and a layout that survives a narrow viewport. Greg or anyone else may open it on a phone.
4. **Real layout, not stacked headers.** If the content is a comparison, lay it out in columns. If it's a timeline, draw a timeline. If it's a diff, render a diff. Don't translate markdown structure 1:1 into HTML — that's wasted effort.
5. **Readable on its own.** Title at the top, a one-paragraph TL;DR or framing sentence right below, then the substance. The reader should know what they're looking at within five seconds.
6. **Tasteful by default.** A neutral but considered design: legible serif or sans body, comfortable line length (60–75ch), generous spacing, restrained color, dark-mode-friendly if cheap. Resist the default-AI aesthetic of "everything is a card with a gradient." See `references/matching-your-style.md` if the user has an existing design system to match.
7. **Editors export back to text.** This one is non-negotiable for any artifact where the reader manipulates state. The artifact must end with a "copy as markdown" / "copy as JSON" / "copy as prompt" button that turns the UI state into something pasteable. The whole point of a throwaway editor is the round-trip.

## Category index

Pick the matching reference file below before drafting. Each one has the per-category pattern (what the layout should look like, what's load-bearing, what mistakes to avoid) plus a sketch of a concrete example.

| If the request is about… | Read… |
|---|---|
| Brainstorming options, side-by-side comparisons, implementation plans, exploring directions before committing | `references/exploration-and-planning.md` |
| Annotated diffs, PR writeups, code review, module maps, "explain this code" | `references/code-review-and-pr.md` |
| Design systems, component sheets, mockups, prototyping animations or interactions | `references/design-and-prototypes.md` |
| Inline SVG figures, flowcharts, architecture diagrams, technical illustrations | `references/diagrams-and-illustrations.md` |
| Status reports, incident timelines, post-mortems, concept explainers, feature deep-dives, learning material | `references/reports-and-research.md` |
| Slide decks, arrow-key presentations | `references/decks.md` |
| One-off custom editors: triage boards, flag toggles, prompt tuners, dataset curators | `references/custom-editors.md` |
| Matching the user's existing visual style or design system | `references/matching-your-style.md` |

If the request spans multiple categories (e.g., "implementation plan with mockups and a flowchart"), read all the relevant references. They're short.

## Output mechanics

Two environments, slightly different mechanics.

### In Claude Code

Save the file to the working directory with a descriptive `kebab-case` name and a `.html` extension. Examples: `onboarding-design-explorations.html`, `pr-streaming-review.html`, `cycle-14-triage.html`. After saving, tell the user the path and offer to open it in their default browser (`open <file>` on macOS, `xdg-open <file>` on Linux). For shareable artifacts the user may upload to S3, Notion, etc. — that's their call, but mention the option once.

If the artifact is a member of a *web* of related files (explorations → mockups → plan), put them in a folder together so they can be opened/shared as a unit.

### In Claude.ai

Use the artifact system. Output a single HTML artifact (`text/html`) — not React, not Mermaid, not SVG-only — unless the request specifically calls for one of those. The HTML artifact is the closest analog to what Claude Code would produce on disk and gives the user the same affordance: open, screenshot, share.

For Claude.ai's artifact environment, observe the platform's rules: no `localStorage`/`sessionStorage` (use in-memory state), no external script tags that aren't on the allowed CDN list, and the artifact must work as a single file.

## A note on token cost and time

HTML artifacts cost roughly 2–4× the tokens of a markdown equivalent and take longer to generate. This is a real tradeoff. The skill is configured to err toward HTML because the reading experience is dramatically better and shareability matters, but if the user is iterating fast on something disposable ("just summarize what's in this file"), a markdown reply is fine. Don't manufacture a use case for HTML where there isn't one.

## A note on taste

Bad-looking HTML is worse than good markdown. If the artifact would render as a wall of generic Tailwind cards with emoji headers, slow down. Read `references/matching-your-style.md` first. If the user has a `frontend-design` skill or design system file in the repo, lean on it. If not, default to a calm typographic layout — system serif body, restrained palette, real structure — rather than a busy "dashboard" look.

## A note on what this skill is not

This skill is not "always answer in HTML." The point is not the format; the point is that for many of the things people ask agents to produce — plans, comparisons, reviews, explainers, editors — the format markdown forces (linear text, no spatial layout, no color, no interactivity) actively obscures the content. HTML lifts that constraint. Where markdown is genuinely the better medium, use markdown.
