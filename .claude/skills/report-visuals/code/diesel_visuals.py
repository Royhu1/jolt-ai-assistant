"""
diesel_visuals (report-visuals skill)
=====================================
Diesel validation-figure painter + in-place repaint entry.

Skill-local copy (report-visuals skill, v3.1.0 P1) of the PLOTTING half of
``src/jolt_toolkit/report_generator/diesel_pipeline.py`` (copied 2026-07-17;
symbols: ``plot_diesel_leg_validation``, ``regenerate_diesel_validation``,
``_logger_day_df_from_csvs``, ``_XLSX_RE``, ``_LOGGER_DATE_RE``). Function
bodies are identical to the source; only the import header was adapted:

* still-shared row-generation helpers (``_finalise_logger_df``,
  ``_segments_from_df``, the ``DEFAULT_*`` channel-name constants) keep coming
  from ``jolt_toolkit.report_generator.diesel_pipeline`` — they STAY in the
  package because ``process_diesel_leg`` (xlsx row generation) also uses them;
* the shared figure-styling primitives (``_TEXT_BBOX``,
  ``_export_overlay_boxes``) and the html-viewer helpers now come from the
  skill-local ``validation_figure`` / ``html_viewer`` siblings (those names
  leave the package in Phase P2).

Reason: the v3.1.0 platform-slim plan moves all validation-figure +
inspect-HTML rendering out of the package into this skill (the package
originals are removed in Phase P2).
"""

from __future__ import annotations

import datetime
import json
import logging
import re
from math import nan
from pathlib import Path

import numpy as np
import pandas as pd

from jolt_toolkit.report_generator.diesel_pipeline import (
    DEFAULT_DISTANCE_COL,
    DEFAULT_FUEL_COL,
    DEFAULT_MASS_COL,
    DEFAULT_SPEED_COL,
    _finalise_logger_df,
    _segments_from_df,
)
from jolt_toolkit.report_generator.segmentation.constants import VEHICLE_CONFIG

# Skill-local siblings (require code/ on sys.path — the entry CLIs bootstrap it).
from html_viewer import (
    _clear_day_validation_figures,
    _group_paths_by_date,
    _write_html_viewer,
)
from validation_figure import _TEXT_BBOX, _export_overlay_boxes

logger = logging.getLogger(__name__)


def _logger_day_df_from_csvs(csv_paths: list[Path], cfg: dict) -> pd.DataFrame | None:
    """
    Merge multiple per-leg ``logger_<date>_<idx>.csv`` of the same calendar day into a single DataFrame.

    One figure per day (v2.2.6): the diesel logger often cuts a day into dozens of
    short legs, and plotting each separately fragments a day into dozens of
    figures. This function reads all of a day's leg CSVs and stacks them by row
    (axis=0, each leg covering a disjoint time window of the same channel set),
    then hands them to :func:`_finalise_logger_df` for the shared dedup + UTC index
    + speed fallback finishing. LFC fuel / VDHR mileage are vehicle-lifetime
    cumulative counters and remain monotonic across legs, so concatenating in time
    order does not affect :func:`_trip_metrics`'s per-trip differencing. Returns
    None when there are no usable rows at all.
    """
    raw_frames: list[pd.DataFrame] = []
    for p in csv_paths:
        try:
            df = pd.read_csv(p, index_col=0)
        except Exception as exc:
            logger.debug("  reading logger CSV failed %s: %s", p.name, exc)
            continue
        if df is None or df.empty:
            continue
        idx = pd.to_datetime(df.index, errors="coerce", utc=True)
        df = df.loc[~idx.isna()]
        df.index = idx[~idx.isna()]
        if not df.empty:
            raw_frames.append(df)
    if not raw_frames:
        return None
    df_all = pd.concat(raw_frames, axis=0)
    return _finalise_logger_df(df_all, cfg, source=f"{len(csv_paths)} legs/day")


def plot_diesel_leg_validation(
    df: pd.DataFrame,
    trips: list[tuple[pd.Timestamp, pd.Timestamp]],
    seg_metrics: list[dict],
    reg: str,
    suffix: str,
    out_path: Path,
    cfg: dict,
    export_overlay: bool = False,
) -> None:
    """
    Diesel 4-panel leg validation figure (in place of plot_leg_validation, which depends strongly on SOC).

    Panel 1 (Speed)                — CCVS wheel-based vehicle speed (or GPS fallback)
    Panel 2 (Cumulative Fuel Used) — zeroed cumulative curve of LFC engine total fuel used
    Panel 3 (Cumulative Distance)  — zeroed cumulative curve of VDHR hr total vehicle distance
    Panel 4 (Vehicle Mass)         — CVW gross combination vehicle weight
    Trip-window shading is overlaid on all panels; Panel 4 annotates the per-trip average mass on each trip.

    Font sizes / layout aligned with the EV :func:`plot_leg_validation` (v2.2.4):
    axis titles / axis labels use ``_LABEL_FONT=20``, ticks use ``_TICK_FONT=16``,
    and all four subplot legends use ``_LEGEND_FONT=18``. The rounded data
    annotations (per-trip fuel / mass) are drawn with ``bbox=_TEXT_BBOX``.

    ``export_overlay`` mirrors the EV's ``export_dsoc_overlay``: when True, after
    ``fig.canvas.draw()`` the shared :func:`_export_overlay_boxes` strips all
    rounded annotations from the PNG and writes them to a ``<png-stem>.boxes.json``
    sidecar (for the inspect HTML to render the interactive overlay), saving
    **without** ``bbox_inches='tight'`` to preserve the figure-fraction coordinate
    mapping; when False it keeps the old behaviour, baking the annotations into the
    PNG. The in-place redraw entry :func:`regenerate_diesel_validation` passes True.
    """
    try:
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
    except ImportError:
        logger.debug("matplotlib unavailable, skipping the diesel validation figure")
        return

    if df is None or df.empty:
        return

    speed_col = cfg.get("speed_col", DEFAULT_SPEED_COL)
    fuel_col = cfg.get("fuel_energy_col", DEFAULT_FUEL_COL)
    dist_col = cfg.get("distance_col", DEFAULT_DISTANCE_COL)
    mass_col = cfg.get("mass_col", DEFAULT_MASS_COL)

    _DISCHARGE_COLOR = "#C8E6C9"  # light green, consistent with the EV Trip colour
    # Two-line short format matching the EV plot_leg_validation. The previous
    # single-line '%Y-%m-%d %H:%M' was too wide and collided horizontally once
    # the tick font doubled to 16.
    _DATE_FMT = "%d %b\n%H:%M"
    # In-figure fonts aligned with the EV plot_leg_validation (v2.2.4, doubled).
    # The larger figure + DPI give the 2x two-line y-labels and the legends room
    # so nothing overlaps or clips at this scale.
    _LABEL_FONT = 20
    _TICK_FONT = 16
    _LEGEND_FONT = 18
    # Baked size for the rounded-bbox data labels — only visible when they are
    # NOT externalised (``export_overlay=False``); otherwise governed by viewer CSS.
    _DATA_FONT = 14
    _DPI = 150

    fig, (ax1, ax2, ax3, ax4) = plt.subplots(
        4,
        1,
        figsize=(18, 10),
        sharex=True,
        gridspec_kw={"height_ratios": [1.6, 1.2, 1.2, 1.6]},
    )

    def _overlay(ax):
        for t_s, t_e in trips:
            ax.axvspan(
                pd.Timestamp(t_s),
                pd.Timestamp(t_e),
                color=_DISCHARGE_COLOR,
                alpha=0.55,
                zorder=1,
            )

    # ── Panel 1: Speed ─────────────────────────────────────────────────
    if speed_col in df.columns:
        spd = pd.to_numeric(df[speed_col], errors="coerce")
        ax1.plot(
            df.index, spd, color="#1565C0", lw=1.0, alpha=0.9, label="CCVS speed (km/h)"
        )
    _overlay(ax1)
    ax1.set_ylabel("Speed (km/h)", fontsize=_LABEL_FONT)
    # Fixed 0–100 km/h: consistent with the EV plot_leg_validation's Panel 1 Speed axis
    ax1.set_ylim(0, 100)
    ax1.grid(True, alpha=0.3)
    legend_items1 = [
        Patch(color=_DISCHARGE_COLOR, alpha=0.6, label=f"Trip ({len(trips)} segs)"),
        Line2D([0], [0], color="#1565C0", lw=1.5, label="Speed"),
    ]
    ax1.legend(handles=legend_items1, fontsize=_LEGEND_FONT, loc="upper right")
    ax1.set_title(f"{reg}  {suffix}  [Diesel Segment Validation]", fontsize=_LABEL_FONT)

    # ── Panel 2: Cumulative Fuel Used (L) ──────────────────────────────
    if fuel_col in df.columns:
        fuel = pd.to_numeric(df[fuel_col], errors="coerce")
        mask = fuel.notna()
        if mask.any():
            base = float(fuel[mask].iloc[0])
            ax2.plot(
                df.index[mask],
                fuel[mask] - base,
                color="#8D6E63",
                lw=1.8,
                alpha=0.9,
                label="LFC total fuel used (normalised)",
            )
        # per-trip fuel annotation
        for seg in seg_metrics:
            if np.isnan(seg.get("fuel_l", nan)):
                continue
            t_s_seg = pd.Timestamp(seg["start_time"])
            t_e_seg = pd.Timestamp(seg["end_time"])
            mid = t_s_seg + (t_e_seg - t_s_seg) / 2
            # Annotation: an axvspan plus a text at the midpoint
            try:
                _fuel_mid = fuel.loc[:t_e_seg].dropna()
                if len(_fuel_mid) > 0:
                    y_lvl = float(_fuel_mid.iloc[-1]) - base
                    # Rounded-bbox data label so _export_overlay_boxes picks it up.
                    ax2.annotate(
                        f"{seg['fuel_l']:.1f} L",
                        xy=(mid, y_lvl),
                        fontsize=_DATA_FONT,
                        color="#4E342E",
                        ha="center",
                        va="bottom",
                        fontweight="bold",
                        bbox=_TEXT_BBOX,
                    )
            except Exception:
                pass
    _overlay(ax2)
    ax2.set_ylabel("Fuel Used\n(L, zeroed)", fontsize=_LABEL_FONT)
    # minimum ymax = 5.0 L: short trips are forced to show 0–5 L, long trips keep the data-driven larger range
    ymax2 = max(5.0, ax2.get_ylim()[1])
    ax2.set_ylim(0, ymax2)
    ax2.grid(True, alpha=0.3)
    if ax2.get_legend_handles_labels()[1]:
        ax2.legend(fontsize=_LEGEND_FONT, loc="upper left")

    # ── Panel 3: Cumulative Distance (km) ──────────────────────────────
    if dist_col in df.columns:
        d = pd.to_numeric(df[dist_col], errors="coerce")
        mask = d.notna()
        if mask.any():
            base = float(d[mask].iloc[0])
            ax3.plot(
                df.index[mask],
                d[mask] - base,
                color="#6A1B9A",
                lw=1.8,
                alpha=0.9,
                label="VDHR distance (normalised)",
            )
    _overlay(ax3)
    ax3.set_ylabel("Distance\n(km, zeroed)", fontsize=_LABEL_FONT)
    # minimum ymax = 10.0 km: short trips are forced to show 0–10 km, long trips keep the data-driven larger range
    ymax3 = max(10.0, ax3.get_ylim()[1])
    ax3.set_ylim(0, ymax3)
    ax3.grid(True, alpha=0.3)
    if ax3.get_legend_handles_labels()[1]:
        ax3.legend(fontsize=_LEGEND_FONT, loc="upper left")

    # ── Panel 4: GCVW ──────────────────────────────────────────────────
    has_gcvw = False
    if mass_col in df.columns:
        m = pd.to_numeric(df[mass_col], errors="coerce")
        mask = m.notna() & (m > 0)
        if mask.any():
            has_gcvw = True
            ax4.plot(df.index[mask], m[mask], color="#37474F", lw=1.4, alpha=0.8)
            ax4.scatter(df.index[mask], m[mask], color="#37474F", s=5, alpha=0.8)
    # per-trip average-mass annotation
    has_trip_mass = False
    for seg in seg_metrics:
        if np.isnan(seg.get("veh_mass", nan)):
            continue
        has_trip_mass = True
        t_s_seg = pd.Timestamp(seg["start_time"])
        t_e_seg = pd.Timestamp(seg["end_time"])
        seg_mass = float(seg["veh_mass"])
        ax4.plot(
            [t_s_seg, t_e_seg],
            [seg_mass, seg_mass],
            color="#2E7D32",
            lw=3.5,
            linestyle="--",
            alpha=0.9,
            zorder=5,
        )
        mid = t_s_seg + (t_e_seg - t_s_seg) / 2
        # Rounded-bbox data label so _export_overlay_boxes picks it up.
        ax4.text(
            mid,
            seg_mass,
            f" {seg_mass / 1000:.1f} t",
            ha="center",
            va="bottom",
            fontsize=_DATA_FONT,
            color="#2E7D32",
            fontweight="bold",
            zorder=8,
            bbox=_TEXT_BBOX,
        )
    _overlay(ax4)
    ax4.set_ylabel("GCVW\n(kg)", fontsize=_LABEL_FONT)
    ax4.set_ylim(0, 50000)
    ax4.set_yticks(range(0, 50001, 10000))
    ax4.grid(True, alpha=0.3)
    mass_legend = []
    if has_gcvw:
        mass_legend.append(
            Line2D(
                [0],
                [0],
                color="#37474F",
                lw=1.4,
                marker="o",
                markersize=5,
                label="GCVW reading",
            )
        )
    if has_trip_mass:
        mass_legend.append(
            Line2D(
                [0], [0], color="#2E7D32", lw=3.5, linestyle="--", label="Per-trip mean"
            )
        )
    if mass_legend:
        ax4.legend(handles=mass_legend, fontsize=_LEGEND_FONT, loc="upper right")

    # Fix the time axis to the full UTC calendar day [00:00, next 00:00) so that
    # diesel figures from different days share an identical midnight-to-midnight
    # grid (directly comparable across days) instead of autoscaling to each day's
    # actual data span. Mirrors the EV plot_leg_validation. ``df.index`` is a
    # tz-aware UTC DatetimeIndex (forced in _build_logger_df); the middle row is
    # robust against a stray early/late point, and ``.normalize()`` floors it to
    # 00:00:00 keeping the UTC tz so the limits stay in the same date units.
    _t_mid = pd.Timestamp(df.index[len(df.index) // 2])
    day_start = _t_mid.normalize()
    day_end = day_start + pd.Timedelta(days=1)

    fmt = mdates.DateFormatter(_DATE_FMT)
    for ax in (ax1, ax2, ax3, ax4):
        # Fresh locator per axis (DateLocators hold an axis ref). 3-hourly major
        # ticks give an even 00:00 → 24:00 grid that reads both midnights without
        # crowding the two-line '%d %b\n%H:%M' labels.
        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, 3)))
        ax.xaxis.set_major_formatter(fmt)
        # Size both axes' tick labels to the 2x EV scale (was only ax4 x-major).
        ax.tick_params(axis="both", labelsize=_TICK_FONT)
    # sharex=True → setting the limit once propagates to all four panels.
    ax4.set_xlim(day_start, day_end)
    ax4.set_xlabel("Time (UTC)", fontsize=_LABEL_FONT)

    # h_pad mirrors the EV figure: gives the 2x two-line y-labels of adjacent
    # panels room so they do not crowd at the panel boundaries.
    plt.tight_layout(h_pad=1.4)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if export_overlay:
        # Exact figure-fraction export requires the saved PNG to span the full
        # figure extent, so we save WITHOUT bbox_inches='tight' (which would crop
        # the margins and break the mapping). Draw first so transforms reflect the
        # laid-out axes, then collect + strip every bbox data label before saving.
        fig.canvas.draw()
        boxes = _export_overlay_boxes(fig)
        plt.savefig(out_path, dpi=_DPI)
        sidecar = out_path.with_suffix(".boxes.json")
        if boxes:
            with open(sidecar, "w", encoding="utf-8") as fh:
                json.dump(boxes, fh, ensure_ascii=False)
        elif sidecar.exists():
            # Stale sidecar from a previous run with labels → remove it so the
            # viewer does not overlay boxes onto a now-empty figure.
            sidecar.unlink()
    else:
        plt.savefig(out_path, dpi=_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("  fig: %s", out_path.name)


# Report file-name parsing: jolt_report_<REG>_<YYYYMMDD>_<YYYYMMDD>[_finetuned].xlsx
_XLSX_RE = re.compile(
    r"jolt_report_(?P<reg>\w+?)_(?P<ds>\d{8})_(?P<de>\d{8})"
    r"(?P<ft>_finetuned)?\.xlsx$"
)
# Local logger CSV name → calendar day: logger_<date>_<idx>.csv. One figure per
# day, grouped by <date> (:func:`_group_paths_by_date` uses ``.search`` to take
# group(1)'s date token).
_LOGGER_DATE_RE = re.compile(r"logger_(\d{4}-\d{2}-\d{2})")


def regenerate_diesel_validation(
    report_dir: str | Path,
    *,
    reg: str | None = None,
    cfg: dict | None = None,
) -> int:
    """
    Redraw the diesel vehicle's 4-panel validation figures + inspect HTML in place (**without re-running the xlsx**).

    The diesel counterpart of :meth:`ValidationGenerator.regenerate` — the latter
    is EV-only (it depends on SOC + FPS ``raw_telematics`` + ``run_segment_detection``,
    and early-returns for diesel). This function instead rebuilds the Logger
    DataFrame from local ``raw_logger_*/logger_*.csv`` (no SRF round-trip needed)
    and calls :func:`plot_diesel_leg_validation` with ``export_overlay=True``,
    externalising all rounded data annotations to a ``<png-stem>.boxes.json``
    sidecar (rendered as the interactive overlay by the inspect HTML).

    One figure per day (v2.2.6): the diesel logger often cuts a day into dozens of
    short legs, and plotting per leg fragments a day into dozens of figures (the
    inspect sidebar shows ``2025-09-01_0000`` / ``_0002`` / ``_0004`` …). This
    function first uses :func:`_group_paths_by_date` to group ``logger_<date>_*.csv``
    by calendar day, :func:`_logger_day_df_from_csvs` stitches all of a day's legs
    into a single DataFrame, and after segmentation draws just one
    ``validation_<reg>_<date>.png`` per day covering the whole UTC day
    (00:00→24:00) with all of that day's trip shading, so the sidecar / inspect
    sidebar has one entry per day. Before drawing, :func:`_clear_day_validation_figures`
    first clears the historical per-leg figures + sidecars (keeping
    ``*_finetuned.*``), to avoid old and new naming coexisting in the sidebar.

    Args:
        report_dir: the vehicle report directory, containing ``raw_logger_*/`` CSVs and ``jolt_report_*.xlsx``.
        reg:        registration; parsed from the first xlsx file name when omitted.
        cfg:        the vehicle config; read from VEHICLE_CONFIG by ``reg`` when omitted.

    Returns:
        The number of validation figures redrawn (= the number of active days with a valid trip).
    """
    report_dir = Path(report_dir)
    xlsx_files = sorted(report_dir.glob("jolt_report_*.xlsx"))

    if reg is None:
        if not xlsx_files:
            logger.error(
                "No report file found, cannot resolve the vehicle: %s", report_dir
            )
            return 0
        m = _XLSX_RE.match(xlsx_files[0].name)
        if not m:
            logger.error("Cannot parse the file name: %s", xlsx_files[0].name)
            return 0
        reg = m.group("reg")

    if cfg is None:
        cfg = VEHICLE_CONFIG.get(reg)
    if cfg is None:
        logger.error("Vehicle %s is not registered in vehicles.json", reg)
        return 0

    # Collect local raw_logger CSVs (a directory may have several version sub-directories such as raw_logger_v1)
    logger_dirs = [d for d in sorted(report_dir.glob("raw_logger*")) if d.is_dir()]
    csvs: list[Path] = []
    for d in logger_dirs:
        csvs.extend(sorted(d.glob("logger_*.csv")))
    if not csvs:
        logger.error("No raw_logger CSV under the directory: %s", report_dir)
        return 0

    fig_dir = report_dir / "validation_figures"
    # One figure per day: group all of the same day's leg CSVs together, first
    # clear the historical per-leg figures + sidecars, then draw one figure per day
    # covering the whole day (all of that day's trip shading in one figure).
    by_date = _group_paths_by_date(csvs, _LOGGER_DATE_RE)
    n_removed = _clear_day_validation_figures(fig_dir, reg)
    if n_removed:
        logger.info(
            "  Cleared historical per-leg validation figures + sidecars: %d files",
            n_removed,
        )

    fig_count = 0
    for day, day_csvs in by_date.items():
        df = _logger_day_df_from_csvs(day_csvs, cfg)
        if df is None or df.empty:
            continue
        trips, seg_metrics = _segments_from_df(df, cfg, source=f"{reg} {day}")
        # Consistent with the initial generation: no figure if there is no valid trip (seg_metrics empty)
        if not seg_metrics:
            continue
        out_path = fig_dir / f"validation_{reg}_{day}.png"
        try:
            plot_diesel_leg_validation(
                df,
                trips,
                seg_metrics,
                reg,
                day,
                out_path,
                cfg,
                export_overlay=True,
            )
            fig_count += 1
        except Exception as exc:
            logger.warning("Diesel validation figure redraw failed %s: %s", day, exc)

    # Rewrite an inspect HTML for each non-finetuned period xlsx (finetuned periods
    # are handled by the report-finetuner flow, skipped here to avoid overwriting
    # its *_finetuned.png references).
    html_count = 0
    for xlsx in xlsx_files:
        pm = _XLSX_RE.match(xlsx.name)
        if not pm or pm.group("ft"):
            continue
        p_start = datetime.datetime.strptime(pm.group("ds"), "%Y%m%d").date()
        p_end = datetime.datetime.strptime(pm.group("de"), "%Y%m%d").date()
        _write_html_viewer(report_dir, reg, p_start, p_end, xlsx.name)
        html_count += 1

    logger.info(
        "regenerate_diesel_validation: %s completed %d figures, %d inspect HTML files",
        reg,
        fig_count,
        html_count,
    )
    return fig_count
