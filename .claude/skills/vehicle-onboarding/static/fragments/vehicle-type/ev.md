# Vehicle type: ev — segmentation branch question (speed vs SOC)

Loads at Phase 2 §2.1 when SRF `fuel` ≠ DIESEL. After the branch is chosen, continue
with §2.2 (pipeline configuration) in the core workflow, `static/core/workflow.md`.

For **EV** vehicles, present options to user (in English):

```
Which segmentation approach should be used for discharge trip detection?

1. **Speed-based** (recommended if speed column available) — Detects trips by
   vehicle speed. More accurate trip boundaries, compatible with --fast mode.
   Best for vehicles with reliable speed data at ≥1 reading/5min.

2. **SOC-based** — Detects trips by SOC decrease patterns. Works without speed
   data but sensitive to SOC precision. Best for vehicles with high-precision
   SOC (≥0.1%) or no speed data.

3. Something else — Describe your preferred approach.

Recommended: [1 or 2 based on data inspection]
```
