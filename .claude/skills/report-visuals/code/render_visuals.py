"""report-visuals skill — single entry CLI for validation-figure + inspect-HTML rendering.

Subcommands
-----------
repaint
    Repaint validation figures (one per day, ``validation_<REG>_<date>.png`` +
    ``.boxes.json`` overlay sidecar) and rewrite ``inspect_*.html`` for a
    vehicle report directory, from the on-disk raw artefacts
    (``raw_telematics/`` for EVs, ``raw_logger_*/`` for diesels). Wraps the
    skill-local :class:`validation_generator.ValidationGenerator` — EVs route
    through the package's ``run_segment_detection`` (segmentation stays in
    ``jolt_toolkit``), diesels through the skill-local
    :func:`diesel_visuals.regenerate_diesel_validation`. If ``--dir`` is a
    BASE directory of several vehicle dirs (no raw data directly inside it),
    every vehicle sub-directory is processed (``regenerate_folder``
    equivalent); ``--reg`` then restricts to one vehicle.

rerender-html
    Rewrite every ``inspect_*.html`` under ``<db-root>/<version>/`` from the
    figures + sidecars already on disk — no PNG / sidecar is re-rendered
    (wraps the skill-local :mod:`rerender_inspect`).

repaint-finetuned
    Rendering half of the report-finetuner flow (v3.1.0 P2b): given a
    ``*_finetuned.xlsx`` plus a segments JSON (produced by the finetune
    library's ``dump_segs_json`` — schema
    ``report-visuals.finetuned-segs/v1``, see :mod:`finetuned_visuals`),
    paint the ``validation_*_finetuned.png`` figures (original-vs-finetuned
    overlay, or plain when no original segs are supplied; unchanged days are
    skipped and stale finetuned PNGs removed) and write the
    ``inspect_*_finetuned.html`` viewer. ``--figures-only`` / ``--html-only``
    restrict to one half (``--html-only`` needs no segments JSON — it only
    enumerates figures already on disk). Never overwrites non-finetuned
    originals. Prints machine-parsable summary lines
    ``[report-visuals] repaint-finetuned: figures=<N>`` / ``html=<path>``
    that the finetune library's wrappers parse.

Usage (from the repo root, so ``./cache`` and ``.env`` resolve)
---------------------------------------------------------------
    python .claude/skills/report-visuals/code/render_visuals.py \
        repaint --dir excel_report_database/2.2.8/YK73WFN

    python .claude/skills/report-visuals/code/render_visuals.py \
        rerender-html --version 2.2.8 --db-root excel_report_database [--reg YK73WFN]

    python .claude/skills/report-visuals/code/render_visuals.py \
        repaint-finetuned --xlsx <...>/jolt_report_<REG>_<start>_<end>_finetuned.xlsx \
        --segs-json <segments.json> [--raw-dir <...>/raw_telematics] \
        [--out-dir <...>/validation_figures] [--fig-suffix _finetuned] \
        [--figures-only | --html-only] [--html-out <path>]

Behaviour is identical to what each mode wraps (see the skill README).
``repaint``/``rerender-html`` always leave ``*_finetuned.*`` artefacts
untouched; regenerating those is exactly what ``repaint-finetuned`` is for
(driven by the report-finetuner skill through this CLI — no cross-skill
Python imports).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Bootstrap: make the skill's code/ importable when run as a plain script.
_CODE_DIR = str(Path(__file__).resolve().parent)
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)


def _load_env() -> None:
    """Best-effort .env load (SRF_API_KEY for the EV logger-overlay API fallback).

    Mirrors the package CLI: dotenv is optional at runtime; with local
    ``raw_logger_*`` CSVs present no API call is made and the key is unneeded.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass


def _has_raw_data(vehicle_dir: Path) -> bool:
    """True when the dir carries repaint inputs (EV raw_telematics / diesel raw_logger*)."""
    return (vehicle_dir / "raw_telematics").exists() or any(
        vehicle_dir.glob("raw_logger*")
    )


def cmd_repaint(args: argparse.Namespace) -> int:
    from validation_generator import ValidationGenerator

    target = Path(args.dir)
    if not target.is_dir():
        print(f"[report-visuals] directory not found: {target}", file=sys.stderr)
        return 2

    gen = ValidationGenerator(cache_dir=args.cache_dir)
    use_local = not args.no_local_logger

    if _has_raw_data(target):
        # Single vehicle directory (ValidationGenerator.regenerate equivalent;
        # it parses the REG from the xlsx name and routes EV / diesel itself).
        if args.reg and args.reg not in target.name:
            print(
                f"[report-visuals] note: --reg {args.reg} does not match "
                f"directory name {target.name} (REG is parsed from the xlsx)"
            )
        n = gen.regenerate(target, use_local_logger=use_local)
        print(f"[report-visuals] repaint: {n} day figure(s) repainted in {target}")
        return 0 if n > 0 else 1

    # Base directory of vehicle sub-directories (regenerate_folder equivalent).
    results: dict[str, int] = {}
    for sub in sorted(p for p in target.iterdir() if p.is_dir()):
        if args.reg and sub.name != args.reg:
            continue
        if _has_raw_data(sub):
            results[sub.name] = gen.regenerate(sub, use_local_logger=use_local)
    if not results:
        print(
            f"[report-visuals] nothing to repaint under {target}"
            + (f" (reg filter: {args.reg})" if args.reg else "")
            + " — no raw_telematics/ or raw_logger_*/ found",
            file=sys.stderr,
        )
        return 1
    for reg, n in results.items():
        print(f"[report-visuals] repaint: {reg}: {n} day figure(s)")
    return 0


def cmd_repaint_finetuned(args: argparse.Namespace) -> int:
    from finetuned_visuals import (
        paint_finetuned_figures,
        write_finetuned_inspect_html,
    )

    xlsx = Path(args.xlsx)
    if not xlsx.is_file():
        print(f"[report-visuals] xlsx not found: {xlsx}", file=sys.stderr)
        return 2
    if args.figures_only and args.html_only:
        print(
            "[report-visuals] --figures-only and --html-only are mutually "
            "exclusive",
            file=sys.stderr,
        )
        return 2

    try:
        if not args.html_only:
            if not args.segs_json:
                print(
                    "[report-visuals] --segs-json is required unless "
                    "--html-only (the xlsx-side reconstruction is "
                    "finetune-owned: produce the JSON with the "
                    "report-finetuner skill's finetune.dump_segs_json)",
                    file=sys.stderr,
                )
                return 2
            segs_json = Path(args.segs_json)
            if not segs_json.is_file():
                print(
                    f"[report-visuals] segments JSON not found: {segs_json}",
                    file=sys.stderr,
                )
                return 2
            raw_dir = (
                Path(args.raw_dir) if args.raw_dir else xlsx.parent / "raw_telematics"
            )
            out_dir = (
                Path(args.out_dir)
                if args.out_dir
                else xlsx.parent / "validation_figures"
            )
            n = paint_finetuned_figures(
                xlsx, segs_json, raw_dir, out_dir, fig_suffix=args.fig_suffix
            )
            print(f"[report-visuals] repaint-finetuned: figures={n}")

        if not args.figures_only:
            html_out = Path(args.html_out) if args.html_out else None
            out_path = write_finetuned_inspect_html(
                xlsx, html_out, fig_suffix=args.fig_suffix
            )
            print(f"[report-visuals] repaint-finetuned: html={out_path}")
    except (FileNotFoundError, ValueError) as exc:
        print(f"[report-visuals] repaint-finetuned failed: {exc}", file=sys.stderr)
        return 3
    return 0


def cmd_rerender_html(args: argparse.Namespace) -> int:
    from rerender_inspect import rerender_version

    n = rerender_version(Path(args.db_root), args.version, args.reg)
    scope = f" for {args.reg}" if args.reg else ""
    print(
        f"[report-visuals] rerender-html: rewrote {n} inspect HTML(s)"
        f" for version {args.version}{scope}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="render_visuals.py",
        description=(
            "report-visuals skill CLI: repaint validation figures + overlay "
            "sidecars and (re)write inspect_*.html from on-disk artefacts."
        ),
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_re = sub.add_parser(
        "repaint",
        help=(
            "repaint one-figure-per-day validation PNGs + .boxes.json sidecars "
            "and rewrite inspect HTML for a vehicle dir (or a base dir of "
            "vehicle dirs)"
        ),
    )
    p_re.add_argument(
        "--dir",
        required=True,
        help=(
            "vehicle report directory (contains raw_telematics/ or "
            "raw_logger_*/ + jolt_report_*.xlsx), or a base directory of such "
            "vehicle directories"
        ),
    )
    p_re.add_argument(
        "--reg",
        default=None,
        help=(
            "optional vehicle filter (base-dir mode); in single-dir mode the "
            "REG is parsed from the xlsx filename"
        ),
    )
    p_re.add_argument(
        "--no-local-logger",
        action="store_true",
        help=(
            "force the SRF-API logger fetch instead of the local "
            "raw_logger_*/ CSVs (EV speed/mass overlay)"
        ),
    )
    p_re.add_argument(
        "--cache-dir",
        default="./cache",
        help="SRF API cache directory (default ./cache — run from the repo root)",
    )
    p_re.set_defaults(func=cmd_repaint)

    p_ft = sub.add_parser(
        "repaint-finetuned",
        help=(
            "paint validation_*_finetuned.png overlays from a finetuned xlsx "
            "+ segments JSON, and write the inspect_*_finetuned.html viewer "
            "(rendering half of the report-finetuner flow)"
        ),
    )
    p_ft.add_argument(
        "--xlsx",
        required=True,
        help="path to the jolt_report_<REG>_<start>_<end>_finetuned.xlsx",
    )
    p_ft.add_argument(
        "--segs-json",
        default=None,
        help=(
            "segments JSON (schema report-visuals.finetuned-segs/v1) produced "
            "by the report-finetuner skill's finetune.dump_segs_json; "
            "required unless --html-only"
        ),
    )
    p_ft.add_argument(
        "--raw-dir",
        default=None,
        help="raw telematics dir (default: <xlsx dir>/raw_telematics)",
    )
    p_ft.add_argument(
        "--out-dir",
        default=None,
        help="figure output dir (default: <xlsx dir>/validation_figures)",
    )
    p_ft.add_argument(
        "--fig-suffix",
        default="_finetuned",
        help="suffix for the produced figures/HTML (default: _finetuned)",
    )
    p_ft.add_argument(
        "--figures-only",
        action="store_true",
        help="paint the finetuned figures but skip the inspect HTML",
    )
    p_ft.add_argument(
        "--html-only",
        action="store_true",
        help=(
            "write only the finetuned inspect HTML from figures already on "
            "disk (no segments JSON needed)"
        ),
    )
    p_ft.add_argument(
        "--html-out",
        default=None,
        help=(
            "explicit inspect-HTML output path (default: "
            "inspect_<xlsx stem[+fig-suffix]>.html next to the xlsx)"
        ),
    )
    p_ft.set_defaults(func=cmd_repaint_finetuned)

    p_rr = sub.add_parser(
        "rerender-html",
        help=(
            "rewrite inspect_*.html for every report under <db-root>/<version>/ "
            "from existing figures/sidecars (no PNG re-render)"
        ),
    )
    p_rr.add_argument(
        "--version", required=True, help="report-database version, e.g. 2.2.8"
    )
    p_rr.add_argument(
        "--db-root",
        required=True,
        help="path to excel_report_database (the dir that holds <version>/)",
    )
    p_rr.add_argument(
        "--reg", default=None, help="optional single-vehicle filter, e.g. YK73WFN"
    )
    p_rr.set_defaults(func=cmd_rerender_html)

    args = ap.parse_args(argv)

    logging.basicConfig(format="%(levelname)-5s %(message)s", level=logging.INFO)
    _load_env()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
