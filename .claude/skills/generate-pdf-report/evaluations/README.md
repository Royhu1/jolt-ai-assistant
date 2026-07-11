# generate-pdf-report — evaluations

Per-run experience log (skill-design principle 7: accumulate experience). One file per
notable run or revision: `<REG>_<period>_<YYYYMMDD>.md`, following the pattern set by
`param-tuner/evaluations/`.

Record here when a run or revision teaches something reusable, e.g.:

- partner review comments applied (comment → decision → what changed → which briefings
  were re-rendered);
- layout / commentary decisions and their rationale (especially anything added to, or
  deliberately diverging from, the layout contract or the style baseline);
- per-vehicle quirks (GVM band judgements recorded in `briefing_vehicle_specs.json`,
  sparse operators forced via `--min-operator-trips`, missing data channels, no-mass
  distribution-variant cases);
- verification findings (FAIL / CHECK MANUALLY rows in `verification_*.xlsx` and how they
  were resolved).

Routine regenerations that match the style baseline and verify clean do not need an entry.
