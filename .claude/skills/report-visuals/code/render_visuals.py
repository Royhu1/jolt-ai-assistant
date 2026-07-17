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

Usage (from the repo root, so ``./cache`` and ``.env`` resolve)
---------------------------------------------------------------
    python .claude/skills/report-visuals/code/render_visuals.py \
        repaint --dir excel_report_database/2.2.8/YK73WFN

    python .claude/skills/report-visuals/code/render_visuals.py \
        rerender-html --version 2.2.8 --db-root excel_report_database [--reg YK73WFN]

Behaviour is identical to what each mode wraps (v3.1.0 P1 copy-first move —
see the skill README). ``*_finetuned.*`` artefacts are always left untouched;
explicit ``--finetuned`` support for the report-finetuner flow is a later
phase (TODO in the skill README).
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
