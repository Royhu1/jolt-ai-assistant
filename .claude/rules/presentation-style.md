> Presentation (slide-deck) style conventions — referenced from the root `CLAUDE.md`
> "## Presentation Convention" section via `@import`. Editing here = editing the slide
> formatting rules for the whole project (team-shared, committed with `.claude/`).

Applies to **every slide deck produced in this project** (`monthly_presentation/` decks,
ad-hoc partner/SteerCo slides), whatever tool generates them (python-pptx, manual edits).

### Typography (mandatory)

- **Font: Arial for all slide text** — titles, body, tables, footnotes, chart labels
  embedded as text boxes. When editing an existing deck whose theme uses another font
  (e.g. Calibri), switch the theme's latin major/minor fonts to Arial rather than
  patching runs one by one, so inherited text follows too.
  *Why:* Arial is the house style of the JOLT/CSRF meeting decks and renders identically
  on every partner machine (no font-substitution surprises in the meeting room).
- **Minimum font size: 18 pt** — nothing on a slide below 18 pt, including table cells,
  axis annotations and footnotes. If content does not fit at 18 pt, **split it across
  slides (or trim columns/rows)** — never shrink the text to make it fit.
  *Why:* decks are projected in meeting rooms; below ~18 pt the back of the room cannot
  read it, and shrinking text hides the real problem (too much content on one slide).

### Working practice

- Prefer the deck's own theme palette (accent colours) for tables/charts so inserted
  content matches the template's look.
- After programmatic edits, verify visually: export the touched slides to PNG
  (PowerPoint COM `Slide.Export`) and inspect for clipping/overflow before delivering.
