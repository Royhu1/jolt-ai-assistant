"""Refresh excel_report_database/<version>/<REG>/inspect_*.html to the current version's HTML template.

Purpose
-------
When ``_write_html_viewer``'s UX is upgraded (e.g. active-day red text, empty-day
filter checkbox, ``localStorage`` state memory), the inspect HTML of every
existing xlsx report needs to be rewritten, but **without re-running the
segmentation algorithm or redrawing the validation figures**.

Logic
-----
- Scan the ``excel_report_database/<version>/<REG>/`` directory for all ``jolt_report_<REG>_<DS>_<DE>.xlsx``.
- Parse period_start / period_end from the file name (YYYYMMDD → date).
- Call ``html_viewer._write_html_viewer(out_dir, reg, ds, de, report_name)`` directly.
  That function itself reads the existing pngs under ``out_dir/validation_figures/``
  and the active dates from the xlsx, so no extra involvement is needed from us.
- Does not touch the xlsx / figures / raw_telematics at all.

Notes
-----
- Generic across EV / diesel, because ``_write_html_viewer`` depends only on the
  figures file-name convention + the date columns in the xlsx, and is
  vehicle-type-agnostic.
- Single-vehicle filtering is via the ``--reg`` argument; refreshes the whole fleet by default.

Skill-local copy (report-visuals skill, v3.1.0 P1) of
``src/jolt_toolkit/scripts/refresh_inspect_html.py`` (copied 2026-07-17;
symbols: ``refresh_one``, ``main``). Function bodies are identical to the
source except: the html-viewer helpers now come from the skill-local
``html_viewer`` sibling, and ``_project_root()`` climbs from the skill's
location instead of the package's.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import date
from pathlib import Path

# Bootstrap: make the skill's code/ importable when run as a plain script.
_CODE_DIR = str(Path(__file__).resolve().parent)
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

from html_viewer import (  # noqa: E402 (needs the bootstrap above)
    _compute_active_dates_from_xlsx,
    _write_html_viewer,
)

LOG = logging.getLogger("refresh_inspect_html")

# jolt_report_<REG>_<YYYYMMDD>_<YYYYMMDD>.xlsx
_XLSX_RE = re.compile(
    r"^jolt_report_(?P<reg>[A-Z0-9]+)_(?P<ds>\d{8})_(?P<de>\d{8})\.xlsx$"
)


def _ymd(s: str) -> date:
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def _project_root() -> Path:
    # .claude/skills/report-visuals/code/refresh_inspect_html.py -> repo root
    # (code -> report-visuals -> skills -> .claude -> root)
    return Path(__file__).resolve().parents[4]


def _iter_reports(reports_root: Path, reg_filter: str | None):
    """Yield (reg, xlsx_path) for every report in reports_root."""
    if not reports_root.exists():
        raise FileNotFoundError(f"Reports directory not found: {reports_root}")
    for reg_dir in sorted(reports_root.iterdir()):
        if not reg_dir.is_dir():
            continue
        reg = reg_dir.name
        if reg_filter and reg != reg_filter:
            continue
        for xlsx in sorted(reg_dir.glob("jolt_report_*.xlsx")):
            yield reg, xlsx


def refresh_one(xlsx: Path) -> dict:
    """Rewrite the inspect HTML next to ``xlsx`` in place. Returns a stats dict."""
    out_dir = xlsx.parent
    m = _XLSX_RE.match(xlsx.name)
    if not m:
        LOG.warning("Skip (unexpected filename): %s", xlsx.name)
        return {"skipped": True}
    reg = m.group("reg")
    ds = _ymd(m.group("ds"))
    de = _ymd(m.group("de"))
    report_name = xlsx.name

    fig_dir = out_dir / "validation_figures"
    n_figs_total = (
        len(list(fig_dir.glob(f"validation_{reg}_*.png"))) if fig_dir.exists() else 0
    )

    # Count figs that fall inside the period (matches _write_html_viewer's own filter).
    # ``[._]`` accepts both the one-figure-per-day ``validation_<reg>_<date>.png`` and
    # the legacy per-leg ``validation_<reg>_<date>_<NNNN>.png`` (kept in lock-step with
    # _write_html_viewer so the counts here match what the viewer actually lists).
    _date_re = re.compile(r"validation_" + re.escape(reg) + r"_(\d{4}-\d{2}-\d{2})[._]")
    figs_in_period: list[str] = []
    if fig_dir.exists():
        ds_s, de_s = ds.isoformat(), de.isoformat()
        for p in fig_dir.glob(f"validation_{reg}_*.png"):
            mm = _date_re.match(p.name)
            if mm and ds_s <= mm.group(1) <= de_s:
                figs_in_period.append(mm.group(1))
    n_figs_in_period = len(figs_in_period)

    active_dates = _compute_active_dates_from_xlsx(xlsx)
    n_active_in_period = sum(1 for d in figs_in_period if d in active_dates)
    n_idle_in_period = n_figs_in_period - n_active_in_period

    if n_figs_in_period == 0:
        LOG.info(
            "SKIP %s_%s_%s: no figures in period (xlsx may be empty)",
            reg,
            m.group("ds"),
            m.group("de"),
        )
        return {
            "reg": reg,
            "report": report_name,
            "figs_total": n_figs_total,
            "figs_in_period": 0,
            "active": 0,
            "idle": 0,
            "written": False,
        }

    _write_html_viewer(out_dir, reg, ds, de, report_name)
    html_name = "inspect_" + report_name.replace(".xlsx", ".html")
    written = (out_dir / html_name).exists()

    LOG.info(
        "%s %s: %d figures in period (%d active / %d idle), HTML %s",
        "WROTE" if written else "MISS",
        report_name.replace(".xlsx", ""),
        n_figs_in_period,
        n_active_in_period,
        n_idle_in_period,
        html_name if written else "<not written>",
    )

    return {
        "reg": reg,
        "report": report_name,
        "figs_total": n_figs_total,
        "figs_in_period": n_figs_in_period,
        "active": n_active_in_period,
        "idle": n_idle_in_period,
        "written": written,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--version",
        default="2.2.3",
        help="Reports version subdirectory under excel_report_database/ (default: 2.2.3)",
    )
    ap.add_argument(
        "--reg",
        default=None,
        help="Only refresh a single vehicle registration (e.g. YK73WFN)",
    )
    ap.add_argument(
        "--reports-root",
        default=None,
        help="Override reports root directory (defaults to <repo>/excel_report_database/<version>)",
    )
    args = ap.parse_args()

    logging.basicConfig(
        format="%(levelname)-5s %(message)s",
        level=logging.INFO,
    )

    if args.reports_root:
        root = Path(args.reports_root)
    else:
        root = _project_root() / "excel_report_database" / args.version

    LOG.info("Reports root: %s", root)
    if args.reg:
        LOG.info("Filter:       reg=%s", args.reg)

    results: list[dict] = []
    n_written = 0
    n_skipped = 0
    for reg, xlsx in _iter_reports(root, args.reg):
        try:
            stats = refresh_one(xlsx)
        except Exception as exc:  # noqa: BLE001
            LOG.exception("FAIL %s: %s", xlsx.name, exc)
            continue
        if stats.get("skipped"):
            continue
        results.append(stats)
        if stats.get("written"):
            n_written += 1
        else:
            n_skipped += 1

    # Per-vehicle summary
    LOG.info("=" * 70)
    LOG.info("Summary: %d HTML written, %d skipped (no figures)", n_written, n_skipped)
    LOG.info("-" * 70)
    per_reg: dict[str, list[dict]] = {}
    for r in results:
        per_reg.setdefault(r["reg"], []).append(r)
    for reg in sorted(per_reg.keys()):
        rows = per_reg[reg]
        n = len(rows)
        figs = sum(r["figs_in_period"] for r in rows)
        active = sum(r["active"] for r in rows)
        idle = sum(r["idle"] for r in rows)
        pct = (100.0 * active / figs) if figs else 0.0
        LOG.info(
            "%s: %d report(s), %d figs total, %d active / %d idle (%.1f%% active)",
            reg,
            n,
            figs,
            active,
            idle,
            pct,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
