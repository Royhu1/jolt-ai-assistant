# research_projects/ — mature research projects

> This directory houses the **mature, systematic research sub-projects** of the JOLT
> project: each has its own physics model / pipeline and results report, and is maintained
> by a dedicated Claude Code agent. By contrast, [`data_analysis_workspace/`](../data_analysis_workspace/README.md)
> holds **smaller, one-off or exploratory analyses** of measured data.

## research_projects/ vs data_analysis_workspace/

- `research_projects/` — systematic, long-term maintained, agent-owned; produces reports and
  re-runnable pipelines.
- `data_analysis_workspace/` — quick analysis scripts + figures for single-point questions;
  lighter-weight sub-projects.

> Note the two similarly-named but distinct projects:
> - `research_projects/regen_analysis/` — regenerative-braking **conversion efficiency**
>   η_regen ≈ 0.42, from a **single-vehicle 1 Hz Logger**.
> - `data_analysis_workspace/regen_recovery_factors/` — influencing factors of the recovery
>   **ratio** R, from **fleet-wide telematics**.

## Sub-projects

Each sub-project documents its own internal structure and results in its linked document.

| Directory | Content | Agent | Run entry point |
|---|---|---|---|
| [`simulation/`](simulation/README.md) | physics simulation (`compute_ep()` + Arrhenius `eta_bat()`, factor-isolation Exp 1–9); pure physics, no SRF API | `simulation` | `python research_projects/simulation/run_all.py` |
| [`regen_analysis/`](regen_analysis/report.md) | regenerative-braking energy recovery: Logger 1 Hz CAN × telematics counters, system-level η_regen ≈ 0.42 | `regen-analysis` | `python research_projects/regen_analysis/scripts/run_all.py` |
| `parameter_identify/` | **data / logs / results** of C_rr / C_dA identification only; the identification **code** lives in `src/jolt_toolkit/vehicle_params_identificator/` | `param-identifier` | `python -m jolt_toolkit.vehicle_params_identificator.run_identification` (needs `PYTHONPATH=src` or `pip install -e .`) |

## Path conventions

- All three sub-projects locate I/O **relative to the repository root** or **relative to
  `__file__`**, so paths stay self-consistent after the `research_projects/` subtree is moved.
- Cross-module references: `research_projects/simulation/models/vehicle_physics.py` is imported
  by several `data_analysis_workspace/` scripts via `sys.path.insert(<root>/research_projects/simulation)`;
  the `logger_dir` in `research_projects/regen_analysis/config.json` points to
  `research_projects/parameter_identify/data/<REG>`.

> Algorithm details and changes for each sub-project always go through its corresponding agent
> (ownership is declared in each `.claude/agents/*.md` definition); the main conversation does
> not modify their code directly.
