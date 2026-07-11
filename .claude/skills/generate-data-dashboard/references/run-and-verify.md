# Run and verify (load when actually executing the CLI)

## How to run

```bash
python -m jolt_toolkit.report_generator.data_dashboard --version 2.2.7
# → excel_report_database/2.2.7/dashboard/data_dashboard.html (open offline by double-click)
# overrides: --db-root <reports root>   --out <html path>
```

Optional: `--details none|all|<REG,REG,…>` (default `none`) additionally writes
per-vehicle drill-down `detail_<REG>.html` pages into the same dashboard folder.

Optional: `--fetch-uplot` (one-off) downloads the vendored uPlot JS/CSS from jsDelivr
before continuing — the only network-touching flag of this CLI. Detail pages refuse to
render when these assets are missing and their error message names this flag; once
vendored, everything is offline again.

The CLI prints a per-vehicle summary table (events vs raw day counts per category)
— include it in the reply so the user can sanity-check coverage at a glance.

## Verify after generating

1. The HTML file was (re)written and is self-contained — no `http(s)://` /
   CDN / `<link>` references (it must open offline by double-click).
2. The embedded `const DATA` blob contains every vehicle directory present under
   `excel_report_database/<version>/` (compare against `ls`).
3. Console summary table shows no vehicle skipped due to a locked/unreadable file.
