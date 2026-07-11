# Mode: quick — one iteration on a stratified sample

- Stratified sampling, review **max(30% of total trips, 30)** figures (whichever is larger)
- One iteration of parameter adjustment (propose → apply → spot-check)
- Spot-check: re-examine ~10 key figures (mix of previously problematic + correct)
- Suitable for vehicles with known similar characteristics to a previously tuned vehicle

## Review-set selection (workflow step 2) — stratified sampling (≥ max(30% of trips, 30) figures)

1. **Count total validation figures** and compute target: `N = max(total * 0.3, 30)`

2. **Classify all figures** by SOC activity pattern:
   - **Active days**: days with discharge segments (SOC drops during driving)
   - **Charge-only days**: only charging events, no discharge
   - **Idle days**: no activity (flat SOC, no speed)

3. **Mandatory inclusions** (always review these):
   - ALL active days (these are the primary optimization targets)
   - ALL charge-only days (verify charge segmentation)

4. **Random supplement**: if mandatory set < N, randomly sample idle days
   until reaching N figures total. Idle days verify there are no false positives.

5. **Priority ordering**: review active days first, sorted by SOC range
   (days with largest SOC swing first — most likely to reveal segmentation issues).

## Re-check scope (workflow step 5.4 / Phase 3)

Spot-check ~10 key figures (5 previously problematic + 5 previously correct).
