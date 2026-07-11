# Run mode: template-only — quick PDF/template check on existing data

Use ONLY when the user explicitly asks to test the digest PDF / template (layout tweaks,
rendering checks) on existing data — no SRF, no dashboard refresh. Anything else is
`full-check`.

## How to run

Run from the **repo root**:

```bash
# Quick PDF/template check on existing data only (no SRF, no dashboard refresh)
PYTHONUTF8=1 python .claude/skills/data-collection-monitor/run_monitor.py --dry-run
```

## Notes

- `--dry-run` builds the digest from what is already in `excel_report_database/<version>/`:
  no SRF calls, no append-only extension of the database, no charger backfill sweep, no
  dashboard refresh.
- Under OneDrive, first close any `.xlsx` open in Excel (a locked workbook is skipped on
  read with a warning).
- The digest's fixed layout is specified in `references/digest-spec.md`; the template
  itself is `templates/digest_template.html.j2`.
- HTML→PDF uses this machine's headless Chrome/Edge (`build_digest_pdf.py`, vendored from
  generate-pdf-report's `build_pdf.py`, zero extra dependencies).
