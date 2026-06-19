# pdf_report_workspace — briefing artefact store

**This directory holds only generated artefacts.** The production method (code, Jinja2
template, style references, commentary style guide, run instructions) lives in the
**`generate-pdf-report` skill**: `.claude/skills/generate-pdf-report/SKILL.md`.

To (re)generate a briefing, type in Claude Code:

```
/generate-pdf-report <REG> <yyyymmdd_yyyymmdd>
```

## Contents (all gitignored)

```
pdf_report_workspace/
├── output/<REG>_<period>/        # one folder per briefing
│   ├── report_<REG>_<period>.html    # browser-viewable briefing
│   ├── report_<REG>_<period>.pdf     # PDF (identical to the HTML preview)
│   ├── report_anon_<period>.html/pdf # anonymised version (--anon: no operator/reg/source,
│   │                                 # label-free CARTO basemap) — safe to forward
│   ├── verification_<REG>_<period>.xlsx  # human-verification workbook (Excel formulas
│   │                                 # independently recompute every briefing number)
│   └── figures/, figures_anon/       # chart PNGs (run-token names bust browser cache)
└── cache/here_*.png              # HERE basemap tiles (keyed by centre/zoom/size,
                                  # reused across runs so re-runs work offline)
```

- If the canonical `report_*.pdf` is locked by a PDF viewer at generation time, a
  timestamped `report_*_<unixtime>.pdf` is written instead — close the viewer and
  regenerate to write back the canonical name.
- Safe to delete anything here; every artefact is reproducible from the skill +
  `excel_report_database/`.
