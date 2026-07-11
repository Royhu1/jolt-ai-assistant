# generate-excel-report — evaluations

Per-run experience log (skill-design principle 7: accumulate experience). One file per
notable run: `<topic-or-REG>_<YYYYMMDD>.md`, following the pattern set by
`param-tuner/evaluations/`.

Record here when a run teaches something reusable, e.g.:

- an OneDrive file-lock / sync issue that blocked writing or overwriting an xlsx
  (open Excel handles, "-副本" conflict copies — the literal suffix OneDrive's
  Chinese locale appends to duplicated files) and the workaround;
- a flag combination that behaved non-obviously (`--raw-only` vs `--debug`,
  `--fast` side effects on Logger/Charger columns);
- a per-vehicle generation quirk (missing data channels, stale
  `test_data_config.json` end dates, unusual SRF gaps);
- a toolkit-version / output-directory mix-up and how it was caught
  (cf. the 2.2.3 / 2.2.4 split incident in the core conventions).

Routine successful generations do not need an entry.
