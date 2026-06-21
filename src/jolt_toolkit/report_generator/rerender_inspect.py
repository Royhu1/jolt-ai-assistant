"""Standalone CLI: re-render ``inspect_*.html`` viewers from existing artefacts.

Rewrites every report's ``inspect_*.html`` with the *current* HTML template by
re-running :func:`report_builder._write_html_viewer` against the validation
figures and ``<stem>.boxes.json`` sidecars already on disk — no PNG / sidecar is
re-rendered. Because it simply delegates to whatever ``_write_html_viewer`` is in
the package, it always emits the current viewer: the v2.2.6 interactive renderer
(``renderInteractive`` — default-hidden overlay labels, hover hotzones, a pinned
SoC info box and de-collided markers), which reads both the new
``{boxes, segments, soc_axis}`` dict sidecar and the legacy flat-list sidecars.
This lets HTML-template fixes ship without an expensive figure regeneration.

Usage
-----
    python -m jolt_toolkit.report_generator.rerender_inspect \
        --version 2.2.5 --db-root <db-root> [--reg <REG>]

For each ``jolt_report_<REG>_<YYYYMMDD>_<YYYYMMDD>.xlsx`` under
``<db-root>/<version>/<REG>/`` (``*_finetuned`` skipped — those inspect HTMLs are
owned by report-finetuner's ``regenerate_inspect_html``), the period
start/end are parsed from the filename and ``_write_html_viewer`` is called with
the REG directory as ``out_dir``. The function discovers the figures, sidecars
and active dates itself, so the HTML is rebuilt purely from on-disk artefacts.
Prints one line per report whose inspect HTML was rewritten.
"""

from __future__ import annotations

import argparse
import datetime
import re
from pathlib import Path

from jolt_toolkit.report_generator.report_builder import _write_html_viewer

# 报告文件名解析：jolt_report_<REG>_<YYYYMMDD>_<YYYYMMDD>[_finetuned].xlsx
# （与 validation_generator / diesel_pipeline 中的 _XLSX_RE 保持一致）
_XLSX_RE = re.compile(
    r"jolt_report_(?P<reg>\w+?)_(?P<ds>\d{8})_(?P<de>\d{8})"
    r"(?P<ft>_finetuned)?\.xlsx$"
)


def rerender_report(reg_dir: Path, reg: str, xlsx_name: str) -> bool:
    """Re-render one report's inspect HTML; return True iff the file changed.

    Parses the period from ``xlsx_name`` and re-runs ``_write_html_viewer`` with
    the existing figures/sidecars under ``reg_dir/validation_figures``. Uses the
    HTML file's mtime to decide whether it was actually (re)written —
    ``_write_html_viewer`` returns early without writing when no in-range figures
    exist.
    """
    m = _XLSX_RE.match(xlsx_name)
    if not m or m.group("ft"):
        return False
    p_start = datetime.datetime.strptime(m.group("ds"), "%Y%m%d").date()
    p_end = datetime.datetime.strptime(m.group("de"), "%Y%m%d").date()

    html_name = "inspect_" + xlsx_name.replace(".xlsx", ".html")
    html_path = reg_dir / html_name
    before = html_path.stat().st_mtime_ns if html_path.exists() else None

    _write_html_viewer(reg_dir, reg, p_start, p_end, xlsx_name)

    after = html_path.stat().st_mtime_ns if html_path.exists() else None
    return after is not None and after != before


def rerender_version(
    db_root: Path, version: str, reg_filter: str | None = None
) -> int:
    """Re-render inspect HTMLs for every report under ``<db-root>/<version>/``.

    ``reg_filter`` (optional) restricts to a single vehicle directory. Returns
    the number of inspect HTMLs rewritten.
    """
    version_dir = db_root / version
    if not version_dir.is_dir():
        raise SystemExit(f"version directory not found: {version_dir}")

    count = 0
    for reg_dir in sorted(p for p in version_dir.iterdir() if p.is_dir()):
        reg = reg_dir.name
        if reg_filter and reg != reg_filter:
            continue
        for xlsx in sorted(reg_dir.glob("jolt_report_*.xlsx")):
            try:
                changed = rerender_report(reg_dir, reg, xlsx.name)
            except Exception as exc:  # pragma: no cover - keep going on per-file errors
                print(f"  [skip] {reg}/{xlsx.name}: {exc}")
                continue
            if changed:
                print(f"  rewrote {reg}/inspect_{xlsx.stem}.html")
                count += 1
    return count


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        prog="python -m jolt_toolkit.report_generator.rerender_inspect",
        description=(
            "Re-render inspect_*.html viewers from existing figures/sidecars "
            "(no PNG / sidecar regeneration)."
        ),
    )
    ap.add_argument(
        "--version", required=True, help="report-database version, e.g. 2.2.5"
    )
    ap.add_argument(
        "--db-root",
        required=True,
        help="path to excel_report_database (the dir that holds <version>/)",
    )
    ap.add_argument(
        "--reg",
        default=None,
        help="optional single-vehicle filter, e.g. YK73WFN",
    )
    args = ap.parse_args(argv)

    db_root = Path(args.db_root)
    n = rerender_version(db_root, args.version, args.reg)
    scope = f" for {args.reg}" if args.reg else ""
    print(
        f"[rerender_inspect] rewrote {n} inspect HTML(s)"
        f" for version {args.version}{scope}"
    )


if __name__ == "__main__":
    main()
