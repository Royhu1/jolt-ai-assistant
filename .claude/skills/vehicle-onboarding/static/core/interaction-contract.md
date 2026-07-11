# Interaction contract (always load)

How every onboarding run talks to the user: the run mode chosen at the start, the
decision points that must go to the user, and the working discipline.

## Mode selection

At the start, present the user with two options:

1. **Guided mode** — step-by-step with user confirmation at each decision point
2. **Auto mode** — make best-guess decisions automatically, present results for review

Default: Guided mode.

## Decision points requiring user input

All decision points present numbered options in English with brief explanations.
The last option is always "Something else" for free-form input.

| Decision | When | Options |
|----------|------|---------|
| Branch selection | After data inspection | speed / soc / something else |
| Color | After pipeline config | suggest unused color / user picks |
| min_cluster_gap_kg | After mass data inspection | 1000 / 2000 / 3000 / something else |
| Date range | Before report generation | suggest range based on data / user picks |
| Pipeline params | If default doesn't work | adjust specific params / something else |

## Guidelines

- **ALL questions to the user MUST be formatted as numbered selectable options** with brief
  explanations for each option. The last option is always "Something else" for free-form input.
  Give a recommended option where applicable. Never use open-ended questions — always provide
  concrete choices. This applies to every decision point, including capacity, color, date range,
  parameters, and any other user-facing question.
- Always verify SRF API results with user before proceeding
- Never assume column names — always inspect raw data first
- Use existing pipeline parameters as starting point, not from scratch
- Check param-tuner `references/` for similar vehicles before tuning
- Ensure all configurations are --fast mode compatible (no Logger dependency for segmentation)
- One vehicle at a time; complete onboarding before starting the next
