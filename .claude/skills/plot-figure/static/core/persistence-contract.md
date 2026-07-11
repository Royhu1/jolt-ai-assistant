# Persistence contract (always load)

**Rule: every bespoke invocation persists a self-contained, runnable plotting script in the
target workspace's code folder, runs it from there, and does NOT delete it.** Plot-and-delete
is forbidden — past throwaways are exactly why some published figures (e.g. the per-OEM
energy/range PNGs) have no findable generator.

1. **Where to write it** — the *target workspace's* code/scripts folder, i.e. the folder
   that owns the destination figures:
   - publication paper → `publication_workspace/<paper>/code/`
   - data-analysis topic → `data_analysis_workspace/<topic>/scripts/`
   - if the destination workspace is ambiguous, ask the user; default to the workspace that
     owns the `figures/` the output is going into.
2. **Naming** — descriptive `snake_case`, prefixed `plot_`, named after the figure(s) it
   produces: e.g. `plot_energy_per_oem.py`, `plot_range_cross_oem.py`. **Never** the
   gitignored throwaway names `_tmp_*.py` / `_patch_*.py` (those are deleted after use).
3. **Self-contained & reproducible** — the script runs standalone (`python <path>`) and
   contains: imports, the style constants (copied or imported from
   `data_analysis_workspace/shared/generate_figures.py`, per the style contract), data
   loading from `excel_report_database/<version>/`, the data-quality filters, any exclusion
   list (as a clearly-named module-level constant, e.g. `EXCLUDE_REGS = {...}`), the fit,
   and `fig.savefig(<dest>)`. A module docstring states what it plots, the data version,
   the exclusion criterion, and the output path(s).
4. **Output path** — write the PNG(s) directly to the destination `figures/` dir the user
   asked for (or the workspace default). Keep DPI/sizing per the style contract.
5. **Run it, then report** — execute the persisted script, confirm the PNG(s) were written,
   and tell the user the script path so they can tweak and re-run it.
6. **Provenance** — when the figure feeds a paper, point the caption `Source:` / the paper
   README "copied from" table at the persisted script path (not at a tmp file).

> Idempotent re-runs: a bespoke script must overwrite its own PNG cleanly on re-run, so the
> user's edit→re-run loop is friction-free.
