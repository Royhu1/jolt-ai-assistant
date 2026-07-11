# Output formats — PNG default, vector on request

**The default stays PNG at 300 dpi** (style contract). This page exists for the cases where
the user explicitly asks for vector output, and explains which format fits which consumer.
Vector formats are added *alongside* the canonical PNG, never instead of it.

## Why PNG is the right default here

- **Dense scatter layers**: JOLT per-operation figures draw tens of thousands of leg
  points. In SVG/PDF every marker is a vector object — files balloon to tens of MB, PDF
  viewers and PowerPoint stutter, and LaTeX compilation slows down. A 300 dpi PNG is
  bounded in size regardless of point count.
- **Downstream flows are PNG-shaped**: the monthly decks are built with python-pptx
  (`add_picture` takes PNG; SVG needs a fallback-image hack), and the PDF briefing embeds
  figures via HTML → headless Chrome, where PNG is dependable.
- **Reproducibility contract**: the persisted `plot_<name>.py` regenerates the figure at
  source; nobody needs to post-edit text inside the artefact (the reason journals want
  editable-text vector files does not apply to fleet-analysis PNGs).

## When the user asks for vector output

Add extra `savefig` calls in the persisted script, keeping text as text:

```python
import matplotlib as mpl
mpl.rcParams["svg.fonttype"] = "none"   # keep SVG text editable/selectable
mpl.rcParams["pdf.fonttype"] = 42       # embed TrueType text in PDF

fig.savefig(dest / f"{name}.png", dpi=DPI)          # canonical, always
fig.savefig(dest / f"{name}.pdf", bbox_inches="tight")   # for LaTeX
fig.savefig(dest / f"{name}.svg", bbox_inches="tight")   # for PPT (365) / web
```

## Which format for which consumer

| Consumer | Best format | Notes |
|---|---|---|
| LaTeX (pdfLaTeX, IEEE paper) | **PDF** | `\includegraphics` supports PDF natively. SVG is NOT supported directly — it needs the `svg` package + Inkscape + `--shell-escape`, or a manual pre-conversion. Never hand LaTeX an SVG. |
| PowerPoint (365 / 2019+) | PNG (safe) or SVG (manual insert) | Recent PowerPoint renders inserted SVG and can convert it to editable shapes; older versions and python-pptx automation cannot. Programmatic decks stay PNG. |
| HTML briefing / dashboards | PNG or SVG | Both embed fine; SVG only pays off for line-art (fit-line-only figures), not scatter clouds. |
| Journal submission | PDF/SVG with `fonttype` set as above | Editable text is what production staff need; check the venue's figure guide. |

## Scatter-heavy vector escape hatch

If a vector export of a scatter-heavy figure is genuinely required, rasterise the point
layer only, keeping axes/labels/fit lines vector:

```python
ax.scatter(..., rasterized=True)
fig.savefig(dest / f"{name}.pdf", dpi=DPI)  # dpi controls the rasterised layer
```

This keeps the file small and the text editable while preserving print quality.
