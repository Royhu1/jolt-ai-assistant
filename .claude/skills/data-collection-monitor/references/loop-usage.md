# Trigger and /loop usage (incl. "ask cadence on first run" and "cadence display")

> This file is the "§2" cited by the SKILL.md frontmatter ("ASK the user for the cadence
> on the FIRST run only (see §2)").

Intended to be triggered periodically via `/loop`, e.g. once a week. The interaction rule on
the **first** trigger within a loop:

1. Read `data_collection_reports/MONITOR_STATUS.md`.
2. **If that file does not exist (= the first run of this loop)**: use `AskUserQuestion` to ask
   the user for the **trigger cadence** (daily / **weekly (default)** / fortnightly / monthly).
   The lookback window defaults to follow the cadence (weekly → 7 days); the user may specify
   otherwise. Then run with `--cadence <value> [--window-days N]`.
3. **On every subsequent trigger**: read the cadence back from `MONITOR_STATUS.md` and reuse
   it, **do not ask again**; after the run the file is rewritten, refreshing last run / next
   due.

**Where the cadence is shown:** `MONITOR_STATUS.md` shows at the top, fixed, **Cadence (loop
period) / Lookback / Last run / Next run / Watched vehicles / latest digest**, plus a one-line
"new data this time?" summary per vehicle. Each reply should also echo the cadence and
next-due at the end, so the user can confirm at any time that the loop is still running and
what the period is.

> **About a genuine "weekly" schedule:** `/loop`'s dynamic self-pacing (ScheduleWakeup) is at
> most ~1 hour per step, so it cannot do a one-week interval; a true weekly trigger is handled
> by the harness's scheduled task (cron). This skill does not create a cron itself — the user
> decides the schedule with `/loop`; the skill only "does the work when triggered + maintains
> its own cadence state".
