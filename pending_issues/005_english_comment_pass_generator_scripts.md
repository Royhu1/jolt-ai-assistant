# 005 — English-comment pass for the large generator scripts

- **Status**: OPEN
- **Date found**: 2026-07-12 (skill/agent QA audit)
- **Summary**: Four git-tracked scripts still carry extensive Chinese comments /
  docstrings / runtime messages, violating the code-style rule that all committed
  content is English: `.claude/skills/generate-pdf-report/generate_pdf_report.py`
  (~1500 lines, heaviest), `.claude/skills/generate-pdf-report/build_pdf.py`,
  `data_analysis_workspace/shared/generate_figures.py`, and the **runtime
  `logging.*` / exception message strings** in
  `.claude/skills/generate-excel-report/batch_generate.py` (its docstrings /
  argparse help / comments were already translated on 2026-07-12; the runtime
  strings were deliberately left because translating console/exception output is
  not behaviour-neutral).
- **Root cause**: the scripts pre-date the English-only convention; the audit chose
  targeted fixes over a risky wholesale translation inside a larger change.
- **Impact**: cosmetic/consistency only — no functional impact; remote repo shows
  mixed-language source.
- **Suggested fix**: one dedicated, behaviour-neutral translation pass per script
  (comments + docstrings + help; decide separately whether runtime message strings
  should change, since tests/logs may match on them), verified by `--help` runs and
  a diff review that touches no logic lines.
- **Owner**: generate-pdf-report skill (its two scripts) / plot-figure skill
  (generate_figures.py) / generate-excel-report skill (batch_generate runtime strings)
- **References**: 2026-07-12 audit findings (changelog entry of that date);
  `.claude/rules/code-style.md` "Code comments and docstrings must always be written
  in English".
