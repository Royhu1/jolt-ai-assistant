"""
Per-leg validation figure (matplotlib) + interactive-overlay sidecar export.

Behaviour-preserving split of the former ``segment_algorithms.py`` (v3.0.0).
Importing this module sets the matplotlib ``Agg`` backend (headless) exactly as
the monolith did, so the side-effect is preserved via the facade.
"""

from __future__ import annotations

import json as _json
import logging
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from .constants import (
    AC_COL,
    DC_COL,
    MASS_COL,
    MOVING_COL,
    MOVING_SPEED_THRESHOLD_KMH,
    RECUP_COL,
    SOC_COL,
    TIME_COL,
    TOTAL_ENERGY_COL,
)
from .mass_aggregation import _agg_mass
from .timeutil import _to_utc

logger = logging.getLogger(__name__)

# =============================================================================
# Validation-figure plotting (requires matplotlib)
# =============================================================================
try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.colors as mcolors
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False

_CHARGE_COLOR = "#2ca02c"
_DISCHARGE_COLOR = "#d62728"
# v2.2.4: figure enlarged from (13, 7) so the doubled fonts (see below) keep
# clear of one another and of the tick labels under ``tight_layout``.
_FIGURE_SIZE = (18, 10)
_DPI = 150
# In-figure font sizes were doubled in v2.2.4 so the static PNG reads at roughly
# 2x the previous scale. Only the *chrome* — axis titles / ticks / sub-titles /
# legends — is baked into the PNG at these sizes. Later within v2.2.4 every rounded-bbox
# *data label* (Panel-1 dSOC, Panel-2/3 energy + charger-meter deltas, Panel-3
# recuperation deltas, Panel-4 mass labels) is stripped from the PNG and exported
# to a sidecar JSON, then rendered as an interactive HTML overlay (see
# ``plot_leg_validation(export_dsoc_overlay=...)``); their size is then governed by
# the viewer CSS, not by these constants.
_LABEL_FONT = 20
_TICK_FONT = 16
# Unified legend font across all four subplots. v2.2.6: scaled to ~0.6x the
# previous 18 pt so the baked-in legends sit more discreetly over the data lines
# (axis titles ``_LABEL_FONT`` left unchanged — only the legends were requested).
_LEGEND_FONT = 11
# Baked-text size for the rounded-bbox data labels — only used when they are NOT
# externalised (``export_dsoc_overlay=False`` — e.g. the finetune comparison path).
_DSOC_FONT = 14
_DATE_FMT = "%d %b\n%H:%M"


def _build_energy_series(df_raw: pd.DataFrame, *cols):
    """Return (times_np, values_np): zeroed relative to the leg start, in kWh."""
    sub = df_raw[[TIME_COL] + list(cols)].copy()
    for c in cols:
        sub[c] = pd.to_numeric(sub[c], errors="coerce")
    sub = sub.dropna(subset=list(cols)).sort_values(TIME_COL)
    if len(sub) < 2:
        return None, None
    combined = sub[list(cols)].sum(axis=1)
    base = combined.iloc[0]
    return sub[TIME_COL].values, ((combined - base) / 1000.0).values


_TEXT_BBOX = dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.75)


def _overlay(
    ax,
    df_seg: pd.DataFrame,
    color: str,
    kwh_col: str | None = None,
    *,
    span_alpha: float = 0.12,
    line_alpha: float = 0.85,
    label_prefix: str = "",
    y_offset_frac: float = 0.0,
    z_base: int = 1,
    seg_prefix: str = "",
    panel: int | None = None,
):
    """Overlay segment intervals on ax (shading + vertical lines + optional SOC annotation).

    Parameters
    ----------
    span_alpha : axvspan opacity (base segs default 0.12; overlay default 0.40)
    line_alpha : axvline opacity
    label_prefix : annotation text prefix (overlay uses '[FT] ' to distinguish)
    y_offset_frac : annotation vertical shift fraction (relative to the y-axis range; overlay shifts up ~10%)
    z_base : zorder base for axvspan / axvline (overlay uses a larger value to sit on top)

    Note: the dSOC label (when ``kwh_col`` is set) is always drawn with a rounded
    ``_TEXT_BBOX`` background. In the interactive-overlay export path
    (``export_dsoc_overlay=True``) the generic post-draw collector
    :func:`_export_overlay_boxes` strips every such bbox label from the PNG and
    re-emits it as an HTML overlay; in the legacy path it stays baked in.
    """
    # Compute the y-axis range for the offset
    ylim = ax.get_ylim()
    y_span = ylim[1] - ylim[0] if ylim[1] > ylim[0] else 1.0
    y_shift = y_offset_frac * y_span

    for idx, (_, row) in enumerate(df_seg.iterrows()):
        t_s = _to_utc(row["start_time"])
        t_e = _to_utc(row["end_time"])
        ax.axvspan(t_s, t_e, alpha=span_alpha, color=color, zorder=z_base)
        ax.axvline(
            t_s,
            color=color,
            lw=2.0,
            linestyle="--",
            alpha=line_alpha,
            zorder=z_base + 1,
        )
        ax.axvline(
            t_e, color=color, lw=2.0, linestyle=":", alpha=line_alpha, zorder=z_base + 1
        )
        if kwh_col is not None:
            # ``row.get(..., nan)`` does not trigger the default when the value is
            # ``None``, so None / empty strings must be explicitly converted to NaN
            # (some fields in the xlsx-reconstructed overlay segs may be empty, see
            # :func:`reconstruct_segs_from_xlsx`).
            def _f(val, default=float("nan")):
                if val is None or val == "":
                    return default
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return default

            dsoc = _f(row.get("delta_soc_pct"))
            kwh = _f(row.get(kwh_col))
            eff = _f(row.get("effective_capacity_kwh"))
            mid_t = t_s + (t_e - t_s) / 2
            # Alternate above/below placement to avoid overlapping text on adjacent segments
            end_soc = _f(row.get("end_soc"), 50.0)
            start_soc = _f(row.get("start_soc"), end_soc)
            if idx % 2 == 0:
                y_pos = min(max(start_soc, end_soc) + 3, 105)
                va = "bottom"
            else:
                y_pos = max(min(start_soc, end_soc) - 3, 5)
                va = "top"
            # Overlay vertical stagger: a positive y_shift pushes upward (both the
            # bottom and top positions move up), clamped to [0, 110] to prevent overrun
            y_pos = max(0, min(y_pos + y_shift, 110))
            lines = [f"dSOC={dsoc:+.0f}%"]
            if not np.isnan(kwh):
                lines.append(f"{kwh:+.1f} kWh")
            if not np.isnan(eff):
                lines.append(f"C={eff:.0f} kWh")
            # energy performance for discharge (delta_soc < 0)
            if not np.isnan(dsoc) and dsoc < 0:
                try:
                    odo_s = row.get("odo_start_km")
                    odo_e = row.get("odo_end_km")
                    if odo_s is not None and odo_e is not None:
                        dist = float(odo_e) - float(odo_s)
                        if dist > 0 and not np.isnan(kwh):
                            ep = abs(kwh) / dist
                            lines.append(f"EP={ep:.3f} kWh/km")
                except (TypeError, ValueError):
                    pass
            text_body = "\n".join(lines)
            if label_prefix:
                text_body = f"{label_prefix} " + text_body
            _t = ax.text(
                mid_t,
                y_pos,
                text_body,
                ha="center",
                va=va,
                fontsize=_DSOC_FONT,
                color=color,
                bbox=_TEXT_BBOX,
                zorder=8,
            )
            # v2.2.6: tag the Panel-1 dSOC block as the segment's ``info`` label so
            # the interactive viewer can route it to the pinned info box on hover.
            if seg_prefix and panel is not None:
                _t.set_gid(f"{seg_prefix}{idx}|p{panel}|info")


def _mark_anchors_stored(
    ax,
    df_seg: pd.DataFrame,
    color: str,
    *,
    label_prefix: str = "",
    y_offset_frac: float = 0.0,
    z_base: int = 5,
    seg_prefix: str = "",
    panel: int | None = None,
):
    """
    Annotate the algorithm-recorded anchors (▼▲) and delta dashed lines on the energy subplot.

    NaN anchors (the soc_estimate case, or when the finetune overlay lacks the original cumulative data) are skipped automatically.

    Parameters
    ----------
    label_prefix : text prefix (overlay uses ``'[FT]'``); an empty string means no prefix (original figure style)
    y_offset_frac : text vertical offset fraction (relative to the y-axis range); overlay uses a positive value to
        stagger upward and avoid overwriting the original annotation. The triangles themselves are not offset, only the text position.
    z_base : zorder base for the triangles and dashed lines (overlay uses a larger value to sit on top of the original figure)
    """
    if df_seg.empty or "_anchor_start_time" not in df_seg.columns:
        return
    ylim = ax.get_ylim()
    y_span = ylim[1] - ylim[0] if ylim[1] > ylim[0] else 1.0
    y_shift = y_offset_frac * y_span
    for idx, (_, row) in enumerate(df_seg.iterrows()):
        t_s_raw = row.get("_anchor_start_time")
        t_e_raw = row.get("_anchor_end_time")
        v_s = float(row.get("_anchor_start_rel_kwh", float("nan")))
        v_e = float(row.get("_anchor_end_rel_kwh", float("nan")))
        if t_s_raw is None or t_e_raw is None or np.isnan(v_s) or np.isnan(v_e):
            continue
        t_s = _to_utc(t_s_raw)
        t_e = _to_utc(t_e_raw)
        delta_raw = row.get("delta_energy_kwh", v_e - v_s)
        try:
            delta = (
                float(delta_raw)
                if delta_raw is not None and delta_raw != ""
                else v_e - v_s
            )
        except (TypeError, ValueError):
            delta = v_e - v_s
        ax.scatter(
            t_s,
            v_s,
            marker="v",
            s=60,
            color=color,
            zorder=z_base,
            edgecolors="white",
            linewidths=1.0,
        )
        ax.scatter(
            t_e,
            v_e,
            marker="^",
            s=60,
            color=color,
            zorder=z_base,
            edgecolors="white",
            linewidths=1.0,
        )
        ax.plot(
            [t_s, t_e],
            [v_s, v_s],
            color=color,
            lw=2.0,
            linestyle="--",
            alpha=0.85,
            zorder=z_base - 1,
        )
        ax.plot(
            [t_e, t_e],
            [v_s, v_e],
            color=color,
            lw=1.6,
            linestyle=":",
            alpha=0.8,
            zorder=z_base - 1,
        )
        mid_t = t_s + (t_e - t_s) / 2
        text_body = f"{delta:+.1f}kWh"
        if label_prefix:
            text_body = f"{label_prefix} " + text_body
        _t = ax.text(
            mid_t,
            v_s + y_shift,
            text_body,
            ha="center",
            va="bottom",
            fontsize=13,
            color=color,
            fontweight="bold",
            bbox=_TEXT_BBOX,
            zorder=z_base + 3,
        )
        if seg_prefix and panel is not None:
            _t.set_gid(f"{seg_prefix}{idx}|p{panel}|value")


def _annotate_overlay_energy_delta(
    ax,
    df_seg: pd.DataFrame,
    color: str,
    *,
    label_prefix: str = "[FT]",
    y_offset_frac: float = 0.10,
    fontsize: float = 12.0,
    seg_prefix: str = "",
    panel: int | None = None,
):
    """Annotate ``[FT] ±X.X kWh`` for overlay segments on the energy subplot
    (Panel 2 AC+DC delta / Panel 3 Total Energy Used).

    Unlike :func:`_mark_anchors_stored`, overlay segs are reconstructed from the
    xlsx by :func:`reconstruct_segs_from_xlsx` and have no internal anchor fields
    (``_anchor_*``), so the position is based on the midpoint of
    ``start_time``/``end_time``, staggered near the top of the y-axis by the
    ``y_offset_frac`` fraction to avoid overwriting the original annotation.
    The font is 0.5pt smaller than the original, and the colour matches the overlay shading.
    """
    if df_seg is None or df_seg.empty:
        return
    ylim = ax.get_ylim()
    y_span = ylim[1] - ylim[0] if ylim[1] > ylim[0] else 1.0
    # Place the overlay annotation above the segment near y_max, offset downward by y_offset_frac × span
    y_pos = ylim[1] - y_offset_frac * y_span
    for idx, (_, row) in enumerate(df_seg.iterrows()):
        t_s = _to_utc(row["start_time"])
        t_e = _to_utc(row["end_time"])
        _raw_kwh = row.get("delta_energy_kwh")
        if _raw_kwh is None or _raw_kwh == "":
            continue
        try:
            kwh = float(_raw_kwh)
        except (TypeError, ValueError):
            continue
        if np.isnan(kwh):
            continue
        mid_t = t_s + (t_e - t_s) / 2
        _t = ax.text(
            mid_t,
            y_pos,
            f"{label_prefix} {kwh:+.1f} kWh",
            ha="center",
            va="top",
            fontsize=fontsize,
            color=color,
            fontweight="bold",
            bbox=_TEXT_BBOX,
            zorder=9,
        )
        if seg_prefix and panel is not None:
            _t.set_gid(f"{seg_prefix}{idx}|p{panel}|value")


def _parse_box_gid(gid):
    """Decode a label ``gid`` of the form ``"<seg>|p<panel>|<role>"`` into the
    ``(seg, panel, role)`` triple used by the interactive viewer.

    Returns ``(None, None, None)`` for any artist without a recognised gid
    (legacy / diesel labels, charger-meter session totals), which the viewer
    treats as always-visible, non-segment annotations.
    """
    if not gid or "|" not in gid:
        return None, None, None
    parts = gid.split("|")
    if len(parts) != 3:
        return None, None, None
    seg, panel_tok, role = parts
    try:
        panel = int(panel_tok.lstrip("p"))
    except (TypeError, ValueError):
        panel = None
    return (seg or None), panel, (role or None)


def _export_overlay_boxes(fig, soc_ax=None, seg_specs=None):
    """Collect **every** rounded-bbox data label across all panels and map each to
    figure-fraction coordinates (origin **top-left**, matching how an ``<img>`` is
    laid out in HTML). The collected text artists are **removed from the figure**
    so they are *not* baked into the saved PNG — they live only as the interactive
    HTML overlay.

    Detection is structural and future-proof: it walks ``fig.axes`` (primary axes
    *and* their twins) and picks out the text artists that carry a background patch
    (``t.get_bbox_patch() is not None`` — i.e. drawn with ``bbox=_TEXT_BBOX``).
    Chrome that is *not* a data label — axis titles, sub-titles, legends and tick
    labels — lives outside ``ax.texts`` (in ``ax.title`` / ``ax.{x,y}axis`` / the
    Legend), carries no bbox patch, and therefore stays baked in the PNG at 2x.

    Each output box carries ``x`` / ``y`` in [0, 1] (fraction of the saved PNG,
    from the left / top edge respectively), the alignment (``ha`` / ``va``) so the
    viewer can anchor the div, the multi-line ``text``, the CSS ``color`` and —
    when the artist was drawn with a ``set_gid`` tag (v2.2.6) — the owning
    ``seg`` / ``role`` / ``panel`` so the viewer can group a segment's labels.

    Return shape (v2.2.6):
      * ``soc_ax is None and seg_specs is None`` → a **flat list** of boxes
        (legacy behaviour; the diesel figure and any other caller stay
        byte-compatible and render via the viewer's back-compat path).
      * otherwise → a **dict** ``{"boxes": [...], "segments": [...],
        "soc_axis": {...}}`` driving the hover redesign, where:
          - ``segments`` is ``[{seg, x0, x1}]`` — each segment's figure-fraction
            x-range (full-height hover hotzones), mapped through the SAME
            transData→figure transform as the boxes;
          - ``soc_axis`` is the SOC panel's ``{x0, y0, x1, y1}`` in figure
            fraction, **top-left origin** — the anchor for the pinned info box.

    Must be called AFTER ``fig.canvas.draw()`` and with a layout that matches the
    saved-PNG extent (i.e. saved WITHOUT ``bbox_inches='tight'``), otherwise the
    fractions would not line up with the rendered image.
    """
    out: list[dict] = []
    inv = fig.transFigure.inverted()
    for ax in fig.axes:
        # Snapshot the list: ``t.remove()`` mutates ``ax.texts`` during iteration.
        for t in list(ax.texts):
            if t.get_bbox_patch() is None:
                continue
            try:
                # ``get_unitless_position()`` strips axis units (e.g. converts a
                # date x-coordinate to its date2num float), so ``get_transform()``
                # (transData of the owning axis, twins included) maps it straight
                # to display px. ``get_position()`` would return the raw Timestamp,
                # which ``transData`` cannot transform.
                disp = t.get_transform().transform(t.get_unitless_position())
                fx, fy = inv.transform(disp)
            except (TypeError, ValueError):
                continue
            if not (np.isfinite(fx) and np.isfinite(fy)):
                continue
            seg, panel, role = _parse_box_gid(t.get_gid())
            out.append(
                {
                    "x": round(float(fx), 5),
                    # Flip vertically: matplotlib figure fraction is bottom-up, but an
                    # HTML image positions from the top-down.
                    "y": round(float(1.0 - fy), 5),
                    "ha": t.get_ha(),
                    "va": t.get_va(),
                    "text": t.get_text(),
                    "color": mcolors.to_hex(t.get_color()),
                    "seg": seg,
                    "role": role,
                    "panel": panel,
                }
            )
            # Strip from the PNG; the box now lives only as an HTML overlay div.
            t.remove()

    # Legacy / diesel callers (no extras) get the flat list unchanged.
    if soc_ax is None and seg_specs is None:
        return out

    # ── New schema: segment hotzone x-ranges + SOC-panel anchor box ──────────
    segments: list[dict] = []
    if seg_specs:
        for segid, t_s, t_e in seg_specs:
            try:
                x_s = soc_ax.transData.transform((mdates.date2num(t_s), 0.0))[0]
                x_e = soc_ax.transData.transform((mdates.date2num(t_e), 0.0))[0]
                fx0 = inv.transform((x_s, 0.0))[0]
                fx1 = inv.transform((x_e, 0.0))[0]
            except (TypeError, ValueError):
                continue
            if not (np.isfinite(fx0) and np.isfinite(fx1)):
                continue
            if fx1 < fx0:
                fx0, fx1 = fx1, fx0
            segments.append(
                {
                    "seg": segid,
                    "x0": round(float(fx0), 5),
                    "x1": round(float(fx1), 5),
                }
            )

    soc_axis = None
    if soc_ax is not None:
        pos = soc_ax.get_position()  # figure-fraction Bbox, bottom-up origin
        soc_axis = {
            "x0": round(float(pos.x0), 5),
            "x1": round(float(pos.x1), 5),
            # Flip to top-left origin: top edge = 1 - y1, bottom edge = 1 - y0.
            "y0": round(float(1.0 - pos.y1), 5),
            "y1": round(float(1.0 - pos.y0), 5),
        }

    return {"boxes": out, "segments": segments, "soc_axis": soc_axis}


def plot_leg_validation(
    df_raw: pd.DataFrame,
    charge_segs: list[dict],
    discharge_segs: list[dict],
    reg: str,
    suffix: str,
    out_path,
    ac_col: str = AC_COL,
    dc_col: str = DC_COL,
    panel3_col: str = MOVING_COL,
    mass_col: str = MASS_COL,
    speed_col: str = "wheel_based_speed",
    logger_speed_df: pd.DataFrame | None = None,
    logger_mass_df: pd.DataFrame | None = None,
    charger_meter_df: pd.DataFrame | None = None,
    mass_from_logger: bool = False,
    mass_agg: str = "mean",
    *,
    overlay_charge_segs: list[dict] | None = None,
    overlay_discharge_segs: list[dict] | None = None,
    overlay_label_prefix: str = "[FT]",
    overlay_color_discharge: str = "#FF9933",
    overlay_color_charge: str = "#00CCCC",
    export_dsoc_overlay: bool = False,
) -> None:
    """
    Generate a four-panel validation figure for one leg and save it as a PNG.

    Panel 1 (SOC + Speed)         — SOC on the left axis, Speed on the right axis (Telematics + optional Logger)
    Panel 2 (AC+DC Delta)         — cumulative charge-energy line + charge anchors ▼▲
    Panel 3 (Discharge Energy)    — panel3_col cumulative delta line + discharge anchors ▼▲
    Panel 4 (Vehicle Mass)        — mass_col time-series scatter (kg) + optional Logger CVW, with segment shading overlaid

    Overlay (added in v2.2.4):
    When ``overlay_charge_segs`` / ``overlay_discharge_segs`` are non-empty, a
    second set of shading (default orange / cyan) is overlaid on the base segment
    shading (red / green), for before/after finetune comparison. The overlay
    annotations gain an ``overlay_label_prefix`` (default ``[FT]``) prefix,
    staggered vertically to avoid overlap. The legend expands to 4 items (Original
    charge / Original discharge / Finetuned charge / Finetuned discharge).
    When both overlay parameters are None, the function behaves identically to
    v2.2.3 (backward compatible).

    Interactive overlay (``export_dsoc_overlay``, introduced and later generalised within v2.2.4):
    when ``True``, **every** rounded-bbox data label across all four panels — the
    Panel-1 ``dSOC=...`` boxes, the Panel-2/3 ``±X kWh`` energy deltas and
    charger-meter total, the Panel-3 recuperation deltas, and the Panel-4 mass
    labels — is **not** baked into the PNG. After the layout is finalised they are
    collected (:func:`_export_overlay_boxes`), converted to figure-fraction
    coordinates (0–1, origin top-left), removed from the figure, and written to a
    sidecar ``<png-stem>.boxes.json`` next to the PNG, so the HTML viewer can render
    them as hover-reactive overlay ``<div>``s. To keep the figure-fraction →
    saved-pixel mapping exact, this mode saves WITHOUT ``bbox_inches='tight'``
    (which would crop the whitespace and shift the mapping); ``tight_layout()``
    still prevents overlap. When ``False`` (default, e.g. the finetune comparison
    path) all labels stay baked into the PNG.
    """
    if not _HAS_MPL:
        warnings.warn("matplotlib not available; skipping validation figure")
        return

    df_c = pd.DataFrame(charge_segs)
    df_d = pd.DataFrame(discharge_segs)

    # Overlay (v2.2.4): additional finetuned segs, overlaid on the base in a different hue
    _has_overlay = overlay_charge_segs is not None or overlay_discharge_segs is not None
    df_oc = pd.DataFrame(overlay_charge_segs) if overlay_charge_segs else pd.DataFrame()
    df_od = (
        pd.DataFrame(overlay_discharge_segs)
        if overlay_discharge_segs
        else pd.DataFrame()
    )

    df_r = df_raw.copy()
    df_r[TIME_COL] = pd.to_datetime(df_r[TIME_COL], errors="coerce", utc=True)
    df_r = df_r.dropna(subset=[TIME_COL]).sort_values(TIME_COL)
    df_r[SOC_COL] = pd.to_numeric(df_r[SOC_COL], errors="coerce")
    df_r.loc[df_r[SOC_COL] == 0, SOC_COL] = np.nan
    soc_rows = df_r[df_r[SOC_COL].notna()].sort_values(TIME_COL)
    if len(soc_rows) < 2:
        return

    has_acdc = {ac_col, dc_col}.issubset(df_r.columns)
    t2, v2 = _build_energy_series(df_r, ac_col, dc_col) if has_acdc else (None, None)
    t3, v3 = (
        _build_energy_series(df_r, panel3_col)
        if panel3_col in df_r.columns
        else (None, None)
    )

    if panel3_col == TOTAL_ENERGY_COL:
        ylabel3 = "Total Energy\nUsed Delta (kWh)"
    elif panel3_col == MOVING_COL:
        ylabel3 = "Moving Energy\nDelta (kWh)"
    else:
        ylabel3 = f"{panel3_col[:15]}\nDelta (kWh)"

    fig, (ax1, ax2, ax3, ax4) = plt.subplots(
        4,
        1,
        figsize=(_FIGURE_SIZE[0], _FIGURE_SIZE[1] + 2),
        sharex=True,
        gridspec_kw={"height_ratios": [2.4, 1, 1, 1.6]},
    )

    # ── Panel 1: SOC ──────────────────────────────────────────────────────────
    ax1.plot(soc_rows[TIME_COL], soc_rows[SOC_COL], color="#555555", lw=1.6, alpha=0.8)
    ax1.scatter(
        soc_rows[TIME_COL], soc_rows[SOC_COL], color="#555555", s=6, alpha=0.6, zorder=2
    )
    if not df_d.empty:
        _overlay(
            ax1,
            df_d,
            _DISCHARGE_COLOR,
            kwh_col="delta_energy_kwh",
            seg_prefix="d",
            panel=1,
        )
    if not df_c.empty:
        _overlay(
            ax1,
            df_c,
            _CHARGE_COLOR,
            kwh_col="delta_energy_kwh",
            seg_prefix="c",
            panel=1,
        )
    # Overlay (finetuned) — different hue + deeper alpha + vertically-staggered annotations
    if _has_overlay:
        if not df_od.empty:
            _overlay(
                ax1,
                df_od,
                overlay_color_discharge,
                kwh_col="delta_energy_kwh",
                span_alpha=0.40,
                line_alpha=0.95,
                label_prefix=overlay_label_prefix,
                y_offset_frac=0.10,
                z_base=2,
                seg_prefix="od",
                panel=1,
            )
        if not df_oc.empty:
            _overlay(
                ax1,
                df_oc,
                overlay_color_charge,
                kwh_col="delta_energy_kwh",
                span_alpha=0.40,
                line_alpha=0.95,
                label_prefix=overlay_label_prefix,
                y_offset_frac=0.10,
                z_base=2,
                seg_prefix="oc",
                panel=1,
            )
    # ── Panel 1 right axis: Speed ─────────────────────────────────────────
    ax1_speed = ax1.twinx()
    _tele_speed_plotted = False
    _logger_speed_plotted = False
    if speed_col in df_r.columns:
        spd = pd.to_numeric(df_r[speed_col], errors="coerce").fillna(0.0)
        ax1_speed.plot(df_r[TIME_COL], spd, color="#1565C0", lw=1.0, alpha=0.7)
        _tele_speed_plotted = True
    if logger_speed_df is not None and not logger_speed_df.empty:
        ax1_speed.plot(
            logger_speed_df.index,
            logger_speed_df.iloc[:, 0],
            color="#E65100",
            lw=1.0,
            alpha=0.8,
        )
        _logger_speed_plotted = True
    if _tele_speed_plotted or _logger_speed_plotted:
        ax1_speed.set_ylabel("Speed (km/h)", fontsize=_LABEL_FONT, color="#1565C0")
        ax1_speed.tick_params(axis="y", labelcolor="#1565C0", labelsize=_TICK_FONT)
        # Fixed 0–100 km/h: a project-wide consistent speed axis, for easy comparison across legs
        ax1_speed.set_ylim(0, 100)
    else:
        ax1_speed.set_yticks([])

    if _has_overlay:
        legend_items = [
            Patch(
                color=_CHARGE_COLOR,
                alpha=0.6,
                label=f"Original charge ({len(df_c)} segs)",
            ),
            Patch(
                color=_DISCHARGE_COLOR,
                alpha=0.6,
                label=f"Original discharge ({len(df_d)} segs)",
            ),
            Patch(
                color=overlay_color_charge,
                alpha=0.7,
                label=f"Finetuned charge ({len(df_oc)} segs)",
            ),
            Patch(
                color=overlay_color_discharge,
                alpha=0.7,
                label=f"Finetuned discharge ({len(df_od)} segs)",
            ),
        ]
    else:
        legend_items = [
            Patch(color=_CHARGE_COLOR, alpha=0.6, label=f"Charge ({len(df_c)} segs)"),
            Patch(
                color=_DISCHARGE_COLOR,
                alpha=0.6,
                label=f"Discharge/Trip ({len(df_d)} segs)",
            ),
        ]
    if _tele_speed_plotted or _logger_speed_plotted:
        from matplotlib.lines import Line2D

        legend_items.append(
            Line2D([0], [0], color="#1565C0", lw=2, alpha=0.8, label="Telematics Speed")
        )
        if _logger_speed_plotted:
            legend_items.append(
                Line2D([0], [0], color="#E65100", lw=2, alpha=0.8, label="Logger Speed")
            )
    ax1.legend(handles=legend_items, fontsize=_LEGEND_FONT, loc="upper right")
    ax1.set_ylabel("SOC (%)", fontsize=_LABEL_FONT)
    ax1.set_ylim(0, 110)
    ax1.grid(True, alpha=0.3)
    ax1.set_title(f"{reg}  {suffix}  [Segment Validation]", fontsize=_LABEL_FONT)

    # ── Panel 2: AC+DC cumulative delta + charge anchors ──────────────────────
    if t2 is not None:
        ax2.plot(t2, v2, color=_CHARGE_COLOR, lw=1.8, alpha=0.9)
    if not df_d.empty:
        _overlay(ax2, df_d, _DISCHARGE_COLOR)
    if not df_c.empty:
        _overlay(ax2, df_c, _CHARGE_COLOR)
        _mark_anchors_stored(ax2, df_c, _CHARGE_COLOR, seg_prefix="c", panel=2)
    if _has_overlay:
        if not df_od.empty:
            _overlay(
                ax2,
                df_od,
                overlay_color_discharge,
                span_alpha=0.40,
                line_alpha=0.95,
                z_base=2,
            )
        if not df_oc.empty:
            _overlay(
                ax2,
                df_oc,
                overlay_color_charge,
                span_alpha=0.40,
                line_alpha=0.95,
                z_base=2,
            )
            # ▼▲ anchors for the charge-segment overlay (on the AC+DC cumulative
            # curve) + `[FT] +XX.X kWh`. The anchors are linearly interpolated from
            # df_raw by reconstruct_segs_from_xlsx → attach_anchors_from_df, styled
            # identically to the original production figure (_mark_anchors_stored).
            # If the overlay segs lack the _anchor_* fields (backward compat),
            # degrade to a top-of-panel text annotation.
            if "_anchor_start_time" in df_oc.columns:
                _mark_anchors_stored(
                    ax2,
                    df_oc,
                    overlay_color_charge,
                    label_prefix=overlay_label_prefix,
                    y_offset_frac=0.05,
                    z_base=6,
                    seg_prefix="oc",
                    panel=2,
                )
            else:
                _annotate_overlay_energy_delta(
                    ax2,
                    df_oc,
                    overlay_color_charge,
                    label_prefix=overlay_label_prefix,
                    y_offset_frac=0.10,
                    seg_prefix="oc",
                    panel=2,
                )
    ax2.set_ylabel("AC+DC Delta\n(kWh)", fontsize=_LABEL_FONT)
    ax2.set_ylim(bottom=0)
    ax2.grid(True, alpha=0.3)
    # ── Panel 2 right axis: Charger Meter ───────────────────────────────
    if charger_meter_df is not None and not charger_meter_df.empty:
        from matplotlib.lines import Line2D

        ax2_r = ax2.twinx()
        meter_vals = charger_meter_df["meter_kwh"].values
        meter_times = charger_meter_df.index
        # Normalise: start from 0 (subtract the first reading)
        meter_base = meter_vals[0] if len(meter_vals) else 0.0
        meter_normed = meter_vals - meter_base
        ax2_r.plot(
            meter_times,
            meter_normed,
            color="#6A1B9A",
            lw=2.4,
            alpha=0.9,
            marker="o",
            markersize=4,
        )
        ax2_r.set_ylabel("Charger Meter\n(kWh)", fontsize=_LABEL_FONT, color="#6A1B9A")
        ax2_r.tick_params(axis="y", labelcolor="#6A1B9A", labelsize=_TICK_FONT)
        ax2_r.set_ylim(bottom=0)
        # Annotate the charger's total energy change (first reading → last
        # reading). Use ``ax.text`` rather than ``ax.annotate`` so it matches the
        # other data annotation boxes and can be collected uniformly by
        # _export_overlay_boxes as an HTML overlay.
        if len(meter_vals) >= 2:
            total_delta = meter_vals[-1] - meter_vals[0]
            mid_time = meter_times[0] + (meter_times[-1] - meter_times[0]) / 2
            mid_val = (meter_normed[0] + meter_normed[-1]) / 2
            ax2_r.text(
                mid_time,
                mid_val,
                f"{total_delta:+.1f} kWh",
                fontsize=12,
                color="#6A1B9A",
                ha="center",
                va="bottom",
                fontweight="bold",
                bbox=_TEXT_BBOX,
                zorder=8,
            )
        # Legend
        legend_p2 = [
            Line2D([0], [0], color=_CHARGE_COLOR, lw=2, alpha=0.9, label="AC+DC Delta"),
            Line2D(
                [0],
                [0],
                color="#6A1B9A",
                lw=2.4,
                alpha=0.9,
                marker="o",
                markersize=4,
                label="Charger Meter",
            ),
        ]
        ax2.legend(handles=legend_p2, fontsize=_LEGEND_FONT, loc="upper left")

    # ── Panel 3: discharge-energy delta + recuperation-energy delta + discharge anchors ──
    _RECUP_PLOT_COLOR = "#2E7D32"  # dark green to distinguish recuperation
    if t3 is not None:
        ax3.plot(
            t3, v3, color=_DISCHARGE_COLOR, lw=1.8, alpha=0.9, label="Total Energy Used"
        )
    if not df_d.empty:
        _overlay(ax3, df_d, _DISCHARGE_COLOR)
        _mark_anchors_stored(ax3, df_d, _DISCHARGE_COLOR, seg_prefix="d", panel=3)
    if not df_c.empty:
        _overlay(ax3, df_c, _CHARGE_COLOR)
    if _has_overlay:
        if not df_od.empty:
            _overlay(
                ax3,
                df_od,
                overlay_color_discharge,
                span_alpha=0.40,
                line_alpha=0.95,
                z_base=2,
            )
            # ▼▲ anchors for the discharge-segment overlay (on the Total Energy
            # Used cumulative curve) + `[FT] -XX.X kWh`. As in Panel 2, styled like
            # the original production figure. Backward compat: degrade to top text
            # when _anchor_* is missing.
            if "_anchor_start_time" in df_od.columns:
                _mark_anchors_stored(
                    ax3,
                    df_od,
                    overlay_color_discharge,
                    label_prefix=overlay_label_prefix,
                    y_offset_frac=0.05,
                    z_base=6,
                    seg_prefix="od",
                    panel=3,
                )
            else:
                _annotate_overlay_energy_delta(
                    ax3,
                    df_od,
                    overlay_color_discharge,
                    label_prefix=overlay_label_prefix,
                    y_offset_frac=0.10,
                    seg_prefix="od",
                    panel=3,
                )
        if not df_oc.empty:
            _overlay(
                ax3,
                df_oc,
                overlay_color_charge,
                span_alpha=0.40,
                line_alpha=0.95,
                z_base=2,
            )
    ax3.set_ylabel(ylabel3, fontsize=_LABEL_FONT)
    ax3.set_ylim(bottom=0)
    ax3.grid(True, alpha=0.3)

    # ── Panel 3 right Y axis: Recuperation Energy (zeroed) ──────────────────
    t_recup, v_recup = (
        _build_energy_series(df_r, RECUP_COL)
        if RECUP_COL in df_r.columns
        else (None, None)
    )
    if t_recup is not None and len(t_recup) > 1:
        ax3r = ax3.twinx()
        ax3r.plot(
            t_recup,
            v_recup,
            color=_RECUP_PLOT_COLOR,
            lw=1.8,
            alpha=0.9,
            label="Recuperation Energy",
        )
        ax3r.set_ylabel(
            "Recuperation\nDelta (kWh)", fontsize=_LABEL_FONT, color=_RECUP_PLOT_COLOR
        )
        ax3r.tick_params(axis="y", labelcolor=_RECUP_PLOT_COLOR, labelsize=_TICK_FONT)
        ax3r.set_ylim(bottom=0)
        # Annotate the recuperation data points at the discharge-segment anchor positions
        if not df_d.empty and "_anchor_start_time" in df_d.columns:
            recup_idx = pd.DatetimeIndex(t_recup, tz="UTC")
            recup_s = pd.Series(v_recup, index=recup_idx)
            for _ridx, (_, row) in enumerate(df_d.iterrows()):
                t_s_raw = row.get("_anchor_start_time")
                t_e_raw = row.get("_anchor_end_time")
                if t_s_raw is None or t_e_raw is None:
                    continue
                t_s_a = _to_utc(t_s_raw)
                t_e_a = _to_utc(t_e_raw)
                # Find the nearest recup data point
                try:
                    idx_s = recup_s.index.searchsorted(t_s_a)
                    idx_e = recup_s.index.searchsorted(t_e_a)
                    if 0 < idx_s < len(recup_s) and 0 < idx_e < len(recup_s):
                        rs = recup_s.iloc[max(0, idx_s - 1) : idx_s + 1].iloc[-1]
                        re = recup_s.iloc[max(0, idx_e - 1) : idx_e + 1].iloc[-1]
                        delta_recup = re - rs
                        ax3r.scatter(
                            t_s_a,
                            rs,
                            marker="v",
                            s=40,
                            color=_RECUP_PLOT_COLOR,
                            zorder=5,
                            edgecolors="white",
                            linewidths=1.0,
                        )
                        ax3r.scatter(
                            t_e_a,
                            re,
                            marker="^",
                            s=40,
                            color=_RECUP_PLOT_COLOR,
                            zorder=5,
                            edgecolors="white",
                            linewidths=1.0,
                        )
                        mid_t = t_s_a + (t_e_a - t_s_a) / 2
                        _t = ax3r.text(
                            mid_t,
                            re,
                            f"{delta_recup:+.1f}kWh",
                            ha="center",
                            va="bottom",
                            fontsize=12,
                            color=_RECUP_PLOT_COLOR,
                            fontweight="bold",
                            bbox=_TEXT_BBOX,
                            zorder=8,
                        )
                        # recup delta belongs to the same discharge segment as the
                        # Panel-3 anchor (shares the ``d{idx}`` id across panels).
                        _t.set_gid(f"d{_ridx}|p3|value")
                except (IndexError, KeyError):
                    pass
        # Unify the left/right Y-axis scales: take the Total Energy Used (left
        # axis) range as primary, and give Recuperation (right axis) the same
        # range so the two curves are directly comparable.
        ymax_left = ax3.get_ylim()[1]
        ymax_right = ax3r.get_ylim()[1]
        ymax_unified = max(ymax_left, ymax_right, 5.0)  # at least 5 kWh
        ax3.set_ylim(0, ymax_unified)
        ax3r.set_ylim(0, ymax_unified)

        # Combined legend (left and right axes)
        from matplotlib.lines import Line2D

        lines3_left = [
            Line2D(
                [0],
                [0],
                color=_DISCHARGE_COLOR,
                lw=1.8,
                alpha=0.9,
                label=ylabel3.replace("\n", " "),
            )
        ]
        lines3_right = [
            Line2D(
                [0],
                [0],
                color=_RECUP_PLOT_COLOR,
                lw=1.8,
                alpha=0.9,
                label="Recuperation Delta",
            )
        ]
        ax3.legend(
            handles=lines3_left + lines3_right, fontsize=_LEGEND_FONT, loc="upper left"
        )

    # ── Panel 4: Vehicle Mass ──────────────────────────────────────────────
    _tele_mass_plotted = False
    _logger_mass_plotted = False
    if mass_col in df_r.columns and not mass_from_logger:
        mass_s = pd.to_numeric(df_r[mass_col], errors="coerce")
        mask_m = mass_s.notna() & (mass_s > 0)
        if mask_m.any():
            ax4.scatter(
                df_r.loc[mask_m, TIME_COL],
                mass_s[mask_m],
                s=6,
                color="#37474F",
                alpha=0.8,
                zorder=2,
            )
            ax4.plot(
                df_r.loc[mask_m, TIME_COL],
                mass_s[mask_m],
                color="#37474F",
                lw=1.4,
                alpha=0.7,
            )
            _tele_mass_plotted = True
    if logger_mass_df is not None and not logger_mass_df.empty:
        ax4.plot(
            logger_mass_df.index,
            logger_mass_df.iloc[:, 0],
            color="#E65100",
            lw=1.4,
            alpha=0.8,
            zorder=3,
        )
        _logger_mass_plotted = True
    if not df_d.empty:
        _overlay(ax4, df_d, _DISCHARGE_COLOR)
    if not df_c.empty:
        _overlay(ax4, df_c, _CHARGE_COLOR)
    if _has_overlay:
        if not df_od.empty:
            _overlay(
                ax4,
                df_od,
                overlay_color_discharge,
                span_alpha=0.40,
                line_alpha=0.95,
                z_base=2,
            )
        if not df_oc.empty:
            _overlay(
                ax4,
                df_oc,
                overlay_color_charge,
                span_alpha=0.40,
                line_alpha=0.95,
                z_base=2,
            )

    # ── Average mass of each segment (dashed line + annotation) ──────────────
    # v2.2.6: the Panel-4 segment mass now uses the SAME filter + aggregation as
    # the Excel "Vehicle Mass (kg)" column (report_builder._get_vehicle_mass):
    # window -> valid (>0) -> moving-only (speed > MOVING_SPEED_THRESHOLD_KMH,
    # falling back to all-valid when fewer than two moving samples), then `_agg_mass`
    # by the resolved `mass_agg` method. This keeps the figure annotation consistent
    # with the report value and, for vehicles configured with a robust method
    # (median / iqr_median), drops a transient GCW spike. The old `mass_cluster`
    # filter is no longer needed: the robust median already ignores a few
    # tractor-only low readings.
    def _telemetry_mass(t_s, t_e):
        """Return ``(sel, timestamps)`` — the filtered positive (moving-preferred)
        telemetry mass Series for a segment window and its index-aligned
        ``eventDatetime`` axis (for ``mad_tw_mean``) — or ``(None, None)`` when
        fewer than two samples remain."""
        if mass_col not in df_raw.columns:
            return None, None
        _times = pd.to_datetime(df_raw[TIME_COL], errors="coerce", utc=True)
        _win = (_times >= t_s) & (_times <= t_e)
        _vals = pd.to_numeric(df_raw.loc[_win, mass_col], errors="coerce")
        _valid = _vals.notna() & (_vals > 0)
        if speed_col in df_raw.columns:
            _spd = pd.to_numeric(df_raw.loc[_win, speed_col], errors="coerce")
            _moving = _valid & _spd.notna() & (_spd > MOVING_SPEED_THRESHOLD_KMH)
            if _moving.sum() >= 2:
                _valid = _moving
        _sel = _vals[_valid]
        if len(_sel) < 2:
            return None, None
        return _sel, _times.loc[_sel.index]

    _mean_mass_tele = False
    _mean_mass_logger = False
    for _df_seg, _col, _seg_pfx in (
        (df_d, _DISCHARGE_COLOR, "d"),
        (df_c, _CHARGE_COLOR, "c"),
    ):
        for _midx, (_, row) in enumerate(_df_seg.iterrows()):
            t_s = _to_utc(row["start_time"])
            t_e = _to_utc(row["end_time"])
            _seg_mass = None
            _from_logger = False
            # Prefer telematics mass (same filter as the Excel column + mass_agg aggregation)
            _sel, _sel_ts = _telemetry_mass(t_s, t_e)
            if _sel is not None:
                _mkg, _ = _agg_mass(_sel, mass_agg, timestamps=_sel_ts)
                if np.isfinite(_mkg):
                    _seg_mass = float(_mkg)
                    _from_logger = mass_from_logger
            # Fallback: if telematics mass is unavailable, use Logger CVW (also mass_agg aggregation)
            if (
                _seg_mass is None
                and logger_mass_df is not None
                and not logger_mass_df.empty
            ):
                _log_slice = logger_mass_df.loc[t_s:t_e]
                if not _log_slice.empty:
                    _log_vals = pd.to_numeric(
                        _log_slice.iloc[:, 0], errors="coerce"
                    ).dropna()
                    _log_vals = _log_vals[_log_vals > 0]
                    if len(_log_vals) >= 2:
                        _mkg, _ = _agg_mass(
                            _log_vals, mass_agg, timestamps=_log_vals.index.to_series()
                        )
                        if np.isfinite(_mkg):
                            _seg_mass = float(_mkg)
                            _from_logger = True
            if _seg_mass is not None:
                _ls = ":" if _from_logger else "--"
                ax4.plot(
                    [t_s, t_e],
                    [_seg_mass, _seg_mass],
                    color=_col,
                    lw=4.0,
                    linestyle=_ls,
                    alpha=0.9,
                    zorder=5,
                )
                _t = ax4.text(
                    t_s + (t_e - t_s) / 2,
                    _seg_mass,
                    f" {_seg_mass / 1000:.1f} t",
                    ha="center",
                    va="bottom",
                    fontsize=14,
                    color=_col,
                    fontweight="bold",
                    bbox=_TEXT_BBOX,
                    zorder=8,
                )
                _t.set_gid(f"{_seg_pfx}{_midx}|p4|value")
                if _from_logger:
                    _mean_mass_logger = True
                else:
                    _mean_mass_tele = True
    # ── Overlay (v2.2.4+): mean-mass horizontal line for the finetuned segments + `[FT] XX.X t` annotation ──
    # Same mass computation as the base segments, but the line / text use the
    # overlay colour; both the line and the text are shifted up by ~3% of y_span to
    # avoid occluding the base's same-height dashed line (typically the base and
    # overlay mean masses are very close, and without the shift the orange / cyan
    # line would completely cover the red / green line).
    # The text is raised a little more to stagger it from the line.
    if _has_overlay:
        _y4_lim = ax4.get_ylim()
        _y4_span = _y4_lim[1] - _y4_lim[0] if _y4_lim[1] > _y4_lim[0] else 10000.0
        _y4_line_shift = (
            0.03 * _y4_span
        )  # raise the line ~3% to avoid covering the base
        _y4_text_shift = (
            0.08 * _y4_span
        )  # raise the text further ~5% to avoid overwriting the original t annotation
        for _df_ov, _ov_col, _ov_pfx in (
            (df_od, overlay_color_discharge, "od"),
            (df_oc, overlay_color_charge, "oc"),
        ):
            if _df_ov is None or _df_ov.empty:
                continue
            for _midx, (_, row) in enumerate(_df_ov.iterrows()):
                t_s = _to_utc(row["start_time"])
                t_e = _to_utc(row["end_time"])
                _seg_mass = None
                _from_logger = False
                # Same convention as the base segments: window -> valid -> moving -> mass_agg aggregation
                _sel, _sel_ts = _telemetry_mass(t_s, t_e)
                if _sel is not None:
                    _mkg, _ = _agg_mass(_sel, mass_agg, timestamps=_sel_ts)
                    if np.isfinite(_mkg):
                        _seg_mass = float(_mkg)
                        _from_logger = mass_from_logger
                if (
                    _seg_mass is None
                    and logger_mass_df is not None
                    and not logger_mass_df.empty
                ):
                    _log_slice = logger_mass_df.loc[t_s:t_e]
                    if not _log_slice.empty:
                        _log_vals = pd.to_numeric(
                            _log_slice.iloc[:, 0], errors="coerce"
                        ).dropna()
                        _log_vals = _log_vals[_log_vals > 0]
                        if len(_log_vals) >= 2:
                            _mkg, _ = _agg_mass(
                                _log_vals,
                                mass_agg,
                                timestamps=_log_vals.index.to_series(),
                            )
                            if np.isfinite(_mkg):
                                _seg_mass = float(_mkg)
                                _from_logger = True
                if _seg_mass is None:
                    continue
                _ls = ":" if _from_logger else "--"
                # Raise the line itself by _y4_line_shift to avoid covering the base's same-height dashed line
                _line_y = min(_seg_mass + _y4_line_shift, _y4_lim[1])
                ax4.plot(
                    [t_s, t_e],
                    [_line_y, _line_y],
                    color=_ov_col,
                    lw=4.0,
                    linestyle=_ls,
                    alpha=0.9,
                    zorder=6,
                )
                # Place the text a little higher than the line to avoid covering the original segment's t annotation
                _label_y = min(_seg_mass + _y4_text_shift, _y4_lim[1])
                _t = ax4.text(
                    t_s + (t_e - t_s) / 2,
                    _label_y,
                    f"{overlay_label_prefix} {_seg_mass / 1000:.1f} t",
                    ha="center",
                    va="bottom",
                    fontsize=12.0,
                    color=_ov_col,
                    fontweight="bold",
                    bbox=_TEXT_BBOX,
                    zorder=9,
                )
                _t.set_gid(f"{_ov_pfx}{_midx}|p4|value")
    ax4.set_ylabel("Vehicle Mass\n(kg)", fontsize=_LABEL_FONT)
    ax4.set_ylim(0, 50000)
    ax4.set_yticks(range(0, 50001, 10000))
    ax4.grid(True, alpha=0.3)
    if (
        _tele_mass_plotted
        or _logger_mass_plotted
        or _mean_mass_tele
        or _mean_mass_logger
    ):
        from matplotlib.lines import Line2D

        mass_legend = []
        if _tele_mass_plotted:
            mass_legend.append(
                Line2D(
                    [0],
                    [0],
                    color="#37474F",
                    lw=2,
                    alpha=0.8,
                    label="Telematics Weight",
                )
            )
        if _logger_mass_plotted:
            mass_legend.append(
                Line2D(
                    [0],
                    [0],
                    color="#E65100",
                    lw=2,
                    alpha=0.8,
                    label="SRF Logger Weight",
                )
            )
        if _mean_mass_tele:
            mass_legend.append(
                Line2D(
                    [0],
                    [0],
                    color="#333333",
                    lw=4,
                    linestyle="--",
                    alpha=0.9,
                    label="Seg. Mean Mass",
                )
            )
        if _mean_mass_logger:
            mass_legend.append(
                Line2D(
                    [0],
                    [0],
                    color="#333333",
                    lw=4,
                    linestyle=":",
                    alpha=0.9,
                    label="Seg. Mean Mass (Logger)",
                )
            )
        ax4.legend(handles=mass_legend, fontsize=_LEGEND_FONT, loc="upper right")

    # Fix the time axis to the full UTC calendar day [00:00, next 00:00) so that
    # figures from different days share an identical midnight-to-midnight grid
    # (directly comparable across days) instead of matplotlib autoscaling the x
    # axis to each day's actual data start/end. The day is derived from the data
    # timestamps themselves (tz-aware UTC) — the middle row is robust against a
    # stray early/late point that brushes the previous/next midnight. ``.normalize()``
    # floors a tz-aware Timestamp to 00:00:00 while keeping its UTC tz, so the
    # limits stay in the same date units (date2num) the panels already plot in.
    _t_mid = df_r[TIME_COL].iloc[len(df_r) // 2]
    day_start = _t_mid.normalize()
    day_end = day_start + pd.Timedelta(days=1)

    fmt = mdates.DateFormatter(_DATE_FMT)
    for ax in (ax1, ax2, ax3, ax4):
        # Fresh locator per axis — DateLocators hold an axis reference, so a
        # single shared instance must not be attached to multiple shared axes.
        # 3-hourly major ticks give an even 00:00 → 24:00 grid (00,03,…,21 plus
        # the next-day 00:00 at the right edge) that reads both midnights without
        # crowding the two-line '%d %b\n%H:%M' labels at the 2x tick font.
        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, 3)))
        ax.xaxis.set_major_formatter(fmt)
    # sharex=True → setting the limit once propagates to all four panels.
    ax4.set_xlim(day_start, day_end)
    plt.setp(ax4.xaxis.get_majorticklabels(), fontsize=_TICK_FONT)
    ax3.set_xlabel("")  # move xlabel to bottom panel
    ax4.set_xlabel("Time (UTC)", fontsize=_LABEL_FONT)

    # h_pad gives the 2x two-line y-axis labels of adjacent panels room so they
    # do not crowd at the panel boundaries.
    plt.tight_layout(h_pad=1.4)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if export_dsoc_overlay:
        # Exact figure-fraction export requires that the saved PNG span the full
        # figure [0,1]×[0,1]. ``bbox_inches='tight'`` would crop the outer
        # whitespace and break the mapping, so we save without it (tight_layout
        # already keeps the margins snug). Draw first so the transforms reflect
        # the final, laid-out axes positions, then collect + strip all bbox data
        # labels before saving so they are externalised rather than baked in.
        fig.canvas.draw()
        # v2.2.6: build the per-segment hotzone specs (id + time range) so the
        # exporter can map each segment to a figure-fraction x-range. The ids match
        # the ``set_gid`` tags on every panel's labels (``d``/``c`` base, ``od``/``oc``
        # overlay), so one hover reveals a segment's labels across all panels.
        seg_specs = []
        for _sd, _spfx in ((df_d, "d"), (df_c, "c"), (df_od, "od"), (df_oc, "oc")):
            if _sd is None or _sd.empty:
                continue
            for _i, (_, _r) in enumerate(_sd.iterrows()):
                try:
                    seg_specs.append(
                        (
                            f"{_spfx}{_i}",
                            _to_utc(_r["start_time"]),
                            _to_utc(_r["end_time"]),
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    continue
        result = _export_overlay_boxes(fig, soc_ax=ax1, seg_specs=seg_specs)
        plt.savefig(out_path, dpi=_DPI)
        sidecar = out_path.with_suffix(".boxes.json")
        if result["boxes"]:
            with open(sidecar, "w", encoding="utf-8") as fh:
                _json.dump(result, fh, ensure_ascii=False)
        elif sidecar.exists():
            # Stale sidecar from a previous run with labels → remove it so the
            # viewer does not overlay boxes onto a now-empty figure.
            sidecar.unlink()
        # Tidy the legacy sidecar name from earlier builds (pre overlay-rename,
        # before ``.boxes.json``) so a re-paint never leaves an
        # orphaned ``.dsoc.json`` next to the new ``.boxes.json``.
        legacy = out_path.with_suffix(".dsoc.json")
        if legacy.exists():
            legacy.unlink()
    else:
        plt.savefig(out_path, dpi=_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("  fig: %s", out_path.name)
