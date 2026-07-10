# PDF briefing coverage by trial

One row per **trial** (a vehicle's stint with one operator). BYO = the operator's own
dedicated vehicle; Round-robin = a shared JOLT vehicle rotating between operators (the
operator token comes from the SRF "JOLT Round Robin: `<OP>-<OEM>`" trial description,
dedicated vehicles from the SRF `organisation.name`). Generated PDFs live in
`output/<REG>_<OPERATOR>_<period>/`, produced by the `generate-pdf-report` skill from
report database **2.2.8** (batch of 2026-07-08). Periods are the briefing **operating
period** (first → last valid trip); for the diesel vehicles (no partner briefing yet)
the observed data span is given instead.

| Operator | Vehicle | Reg | Trial type | Period | PDF report |
|----------|---------|-----|------------|--------|------------|
| Knowles | Volvo FM Electric | AV24LXJ | BYO | 2024-06-11 → 2026-07-03 | Yes |
| Knowles | Volvo FM Electric | AV24LXK | BYO | 2024-06-11 → 2026-07-03 | Yes |
| Knowles | Volvo FM Electric | AV24LXL | BYO | 2024-06-11 → 2026-07-03 | Yes |
| Nestlé | Volvo FM Electric | EV73SAL | BYO | 2024-06-12 → 2026-07-05 | Yes |
| Nestlé | Volvo FM Electric | YK73WFN | BYO | 2024-06-12 → 2026-07-03 | Yes |
| JLP | Volvo FM Electric | KY24LHT | BYO | 2024-06-21 → 2025-03-20 (ended) | Yes |
| JLP | Scania P-series BEV | EX74JXY | BYO | 2025-04-11 → 2026-05-03 | Yes |
| Welch Transport | Renault Trucks D Wide Z.E. | N88GNW | BYO | 2024-10-11 → 2026-07-03 | Yes |
| Welch Transport | Renault E-Tech D Wide | T88RNW | BYO | 2024-06-11 → 2026-07-03 | Yes |
| Welch Transport | Renault E-Tech T | TA70WTL | BYO | 2025-05-03 → 2026-07-03 | Yes |
| WJF | Scania P410 (diesel) | YT21EFD | BYO | 2025-08-30 → 2026-07-04 | No (diesel) |
| JLP | Volvo FH Electric | CMZ6260 | Round-robin | 2025-10-30 → 2025-12-23 | Yes |
| SJG | Volvo FH Electric | CMZ6260 | Round-robin | 2026-02-06 → 2026-04-07 | Yes |
| HTL | Volvo FH Electric | CMZ6260 | Round-robin | 2026-04-27 → 2026-07-01 | Yes |
| DP World | Scania P-series BEV | EX74JXW | Round-robin | 2025-07-07 → 2025-08-22 | Yes |
| WJF | Scania P-series BEV | EX74JXW | Round-robin | 2025-10-11 → 2025-11-18 | Yes |
| Welch Transport | Scania P-series BEV | EX74JXW | Round-robin | 2026-02-26 → 2026-04-29 | Yes |
| JLP | DAF XD Electric | LN25NKE | Round-robin | 2025-09-01 → 2025-12-29 | Yes |
| Welch Transport | DAF XD Electric | LN25NKE | Round-robin | 2026-01-14 → 2026-04-07 | Yes |
| WS | DAF XD Electric | LN25NKE | Round-robin | 2026-04-16 → 2026-07-03 | Yes |
| WJF | Mercedes-Benz eActros 600 | YN25RSY | Round-robin | 2025-10-21 → 2025-11-18 | Yes |
| Port Express (Daimler) | Mercedes-Benz eActros 600 | YN75NMA | Round-robin | 2026-01-29 → 2026-04-08 | Yes |
| HTL | Mercedes-Benz eActros 600 | YN75NMA | Round-robin | 2026-04-17 → 2026-06-26 | Yes |
| DP World | DAF XF 450 (diesel) | WU70GLV | Round-robin | 2025-06-26 → 2025-08-08 | No (diesel) |
| WJF | DAF XF 450 (diesel) | WU70GLV | Round-robin | 2025-09-01 → 2025-11-06 | No (diesel) |
| DP World | DAF XF 450 (diesel) | WU70GLV | Round-robin | 2025-11-07 → 2025-12-11 | No (diesel) |

## Notes

- **22 EV trials have a generated briefing** (all "Yes" rows; each briefing dir also
  carries the `_xlsxkpi` page-1 variant and a verification workbook). The 4 diesel
  trial rows (YT21EFD, WU70GLV) have no partner briefing yet — the briefing generator
  currently targets EVs only.
- **EX74JXW / Welch Transport** is a sparse stint (11 valid trips); its briefing was
  generated with `--min-operator-trips 10` and its load-point / temperature analysis
  is flagged unreliable in the skill notes.
- **WU70GLV returned to DP World** after its WJF stint, hence two DP World rows.
- **KY24LHT** (JLP Volvo) stopped reporting on 2025-03-20; its trial is closed.
- Update this table after each briefing batch (see the `generate-pdf-report` skill);
  the previous batch (2.2.7, 2026-07-03) is archived at
  `../archive/pdf_briefings_2.2.7_20260708/`.
