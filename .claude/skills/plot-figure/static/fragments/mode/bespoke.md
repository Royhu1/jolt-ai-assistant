# Mode: bespoke — a specific / customised figure (DEFAULT)

Use for **anything bespoke**: one figure type, a custom vehicle grouping or exclusion
(e.g. "exclude KY24"), a paper/analysis-specific panel, or any figure that will be tuned
later. The persistence contract (`static/core/persistence-contract.md`) is MANDATORY in
this mode — never improvise a throwaway `_tmp_*.py` and delete it.

## Workflow

1. **Confirm the destination** (blocking gate, see manifest): which workspace owns the
   output figures, and therefore which `code/` / `scripts/` folder receives the persisted
   script. Ask the user if ambiguous.
2. **Consult the references you need** (per the manifest's on-demand table):
   - `references/figure-catalogue.md` — which figure family / filename / sub-variant.
   - `references/data-contract.md` — xlsx columns, `plot_config.json` fields, derived
     columns, data-quality filters.
   - `references/fit-models.md` — linear / reciprocal fits, error bars, shaded bands.
3. **Write the persisted script** `plot_<name>.py` in the target workspace's code folder,
   self-contained per the persistence contract: style constants + data loading + filters +
   exclusion constants + fit + `savefig` to the destination figures dir.
4. **Run it**: `python <path/to/plot_name.py>`; confirm the PNG(s) were written.
5. **QA**: check the output against the `templates/` gallery — axes limits, fonts, alphas,
   grid, legend per the style contract, exactly.
6. **Report** the persisted script path so the user can tweak and re-run it.

## Anonymised variants

For anonymised publication variants, expose an `--anon` / `ANON` switch in the persisted
script (mirroring `generate_figures.py`), mapping `Make` → `oem_anonymization` labels from
`plot_config.json`.
