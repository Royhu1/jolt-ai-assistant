# html-artifacts

A Claude skill for producing self-contained HTML artifacts instead of markdown when the task warrants it.

> Markdown has become the dominant file format used by agents to communicate with us. It's simple, portable, has some rich text capability and is easy for you to edit. But as agents have become more and more powerful, I have felt that markdown has become a restricting format.
>
> — Thariq Shihipar, [*The Unreasonable Effectiveness of HTML*](https://thariqs.github.io/html-effectiveness/)

This skill operationalizes the recognition heuristic and per-category patterns from Thariq's post. It triggers on requests where HTML would land harder than markdown — comparisons, plans, code reviews, explainers, status reports, custom editors — and stays out of the way for everything else.

**[→ See live examples](https://dogum.github.io/html-artifacts/)**

## What this skill does

Markdown is fine for chat-flavored replies, code snippets, and quick summaries. It's a poor format for content that benefits from spatial layout, color, real diagrams, interactivity, or a round-trip editor. This skill teaches Claude to recognize when a task is in the second bucket and produce a single self-contained `.html` file instead — covering nine categories of work where HTML structurally beats markdown.

It's not "always answer in HTML." There's an explicit carve-out for short conversational replies, code-only outputs, terminal-style answers, and content that's genuinely just a few sentences. The point is the right format for the job.

## Install

### Claude.ai

1. Download [`html-artifacts.skill`](html-artifacts.skill) from this repo (or the latest GitHub Release once available).
2. Open Claude.ai → Settings → Capabilities → Skills.
3. Upload the `.skill` file.

### Claude Code

Clone or copy the `skill/` folder into your skills directory:

```bash
git clone https://github.com/dogum/html-artifacts.git
cp -r html-artifacts/skill ~/.claude/skills/html-artifacts
```

The folder containing `SKILL.md` is what Claude Code loads.

### Anthropic API

Skills can be deployed organization-wide via the API. See the [Claude docs](https://docs.claude.com) for the upload endpoint.

## How it's structured

```
skill/
├── SKILL.md                            # recognition heuristic, universal rules, carve-outs
└── references/
    ├── exploration-and-planning.md     # side-by-side comparisons, implementation plans
    ├── code-review-and-pr.md           # annotated diffs, PR writeups, module maps
    ├── design-and-prototypes.md        # design systems, component sheets, animation prototypes
    ├── diagrams-and-illustrations.md   # inline SVG figures, flowcharts
    ├── reports-and-research.md         # status reports, post-mortems, concept explainers
    ├── decks.md                        # arrow-key slide presentations
    ├── custom-editors.md               # throwaway editing UIs that round-trip back to text
    └── matching-your-style.md          # taste, design-system-from-codebase trick
```

`SKILL.md` is the entry point and is always in context when the skill triggers. The references are pulled in only when relevant — a comparison task reads `exploration-and-planning.md`; a code review task reads `code-review-and-pr.md`. Most artifacts only need one or two.

## How this addresses Thariq's worry

In the original post, Thariq writes:

> I'm a little bit afraid that people will read this article and turn it into a /html skill or something. While there might be some value in that, I want to emphasize that you don't need to do much to get Claude to do this.

That worry is legitimate. A skill that mechanically converts every prompt into HTML would be worse than no skill — it would obscure cases where markdown is the right answer, and it would calcify into a default-AI aesthetic of "every artifact is a card with a gradient." This skill tries not to do that:

- The recognition heuristic in `SKILL.md` is about *when* HTML helps, not *whether* to always use it. There's a substantive carve-out for cases where markdown is better.
- The references teach per-category patterns — what makes a comparison page work, what makes a code review page work, what makes an explainer with a live demo work — not generic "make HTML."
- `references/matching-your-style.md` is a deliberate effort to head off the default-AI look. It includes a list of patterns to actively avoid (gradients, four shades of indigo, emoji-decorated headers, "glass morphism") and a baseline typographic CSS that doesn't lean on Tailwind cards.
- The skill respects the user's existing design system. It includes the design-system-from-codebase trick from Thariq's own FAQ.

If the skill's defaults still produce ugly output for your taste, the right move is either to fork it or to put a one-time `design-system.html` file alongside it as your project's reference. Style conventions live in the project, not in the skill.

## Examples

Each example is a single `.html` file produced by the skill in response to a prompt. View them at the [GitHub Pages site](https://dogum.github.io/html-artifacts/) or open the files in `docs/examples/` directly.

| Pattern | Prompt | File |
|---|---|---|
| Side-by-side comparison | "Compare three ways to do SSE streaming in a Hono backend" | [`01-sse-comparison.html`](docs/examples/01-sse-comparison.html) |
| Concept explainer with live demo | "Explain how a quarter-car model computes IRI from a road profile" | [`02-iri-explainer.html`](docs/examples/02-iri-explainer.html) |
| Custom editor with export | "Triage these 8 tickets into Now/Next/Later/Cut, copy-as-markdown export" | [`03-triage-editor.html`](docs/examples/03-triage-editor.html) |
| Weekly status report | "Write the platform team's weekly status report" | [`04-status-report.html`](docs/examples/04-status-report.html) |
| Annotated flowchart | "Diagram our deploy pipeline with happy path and failure paths" | [`05-flowchart.html`](docs/examples/05-flowchart.html) |
| Slide deck | "Make a short deck on the case for HTML over markdown" | [`06-deck.html`](docs/examples/06-deck.html) |

## Acknowledgments

This skill is a direct response to [Thariq Shihipar](https://x.com/trq212)'s [*The Unreasonable Effectiveness of HTML*](https://thariqs.github.io/html-effectiveness/) and the live companion site at [thariqs.github.io/html-effectiveness](https://thariqs.github.io/html-effectiveness/). The categories, the recognition framing, and several of the example shapes (the triage board, the live-demo explainer, the side-by-side option comparison) come directly from his examples. The recognition heuristic and the carve-outs are extensions, not the original.

The skill itself was authored using Anthropic's [skill-creator](https://github.com/anthropics/skills) workflow.

## License

Apache 2.0. See [`LICENSE`](LICENSE).
