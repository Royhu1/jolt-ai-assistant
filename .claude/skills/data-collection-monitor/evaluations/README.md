# data-collection-monitor — evaluations

Per-run experience log (skill-design principle 7: accumulate experience). One file per
notable run: `<topic-or-REG>_<YYYYMMDD>.md`, following the pattern set by
`param-tuner/evaluations/`.

Record here when a monitor run teaches something reusable, e.g.:

- a new vehicle's data appearing on SRF for the first time (and how the append-only
  extension picked it up);
- an SRF platform quirk (late uploads, coverage gaps, rate limits, schema surprises) and
  the workaround;
- a digest anomaly (mis-counted legs, colour-state confusion, layout overflow) and its
  root cause;
- a cadence / `MONITOR_STATUS.md` state issue (stale next-due, first-run question asked
  when it should not have been).

Routine no-new-data iterations do not need an entry.
