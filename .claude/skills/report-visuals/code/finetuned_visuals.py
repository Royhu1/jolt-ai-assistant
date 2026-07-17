"""
finetuned_visuals (report-visuals skill)
========================================
Rendering half of the report-finetuner flow: paint ``*_finetuned`` validation
figures (plain or original-vs-finetuned overlay) and write the
``inspect_*_finetuned.html`` viewer for a finetuned xlsx.

Skill-local port (report-visuals skill, v3.1.0 P2b, 2026-07-17) of the
RENDERING half of the report-finetuner skill's ``finetune.py``
(``regenerate_figures``'s painting loop + ``regenerate_inspect_html``'s HTML
writer, plus their private helpers ``attach_anchors_from_df`` /
``_cumulative_relative_kwh`` / ``_interp_at`` / ``_segs_equal`` /
``_leg_time_bounds`` / ``_overlap`` / ``_slice_logger`` / ``_try_fetch_logger``
/ ``_reg_from_name`` — those helpers were MOVED here, not duplicated; the
finetune library now delegates to this module through the
``render_visuals.py repaint-finetuned`` CLI). Function bodies are identical to
the source; only the seams changed:

* segment RECONSTRUCTION stays finetune-owned (``reconstruct_segs_from_xlsx``
  reads the xlsx) — this module receives the already-reconstructed segments
  through a JSON file (schema below), never by importing the finetune library
  (no cross-skill Python imports — CLI contracts only, per the v3.1.0 plan);
* the painter is the skill-local sibling ``validation_figure`` (was the
  package's ``segment_algorithms.plot_leg_validation``);
* the best-effort SRF Logger fetch uses the skill-local sibling
  ``validation_generator.ValidationGenerator`` (was the package's).

Segments-JSON contract (produced by finetune's ``dump_segs_json``)
------------------------------------------------------------------
Schema tag ``report-visuals.finetuned-segs/v1``::

    {
      "schema": "report-visuals.finetuned-segs/v1",
      "reg": "YK73WFN",
      "original_available": true,
      "by_date": {
        "2024-06-11": {
          "finetuned": {"charge": [<seg>...], "discharge": [<seg>...]},
          "original":  {"charge": [<seg>...], "discharge": [<seg>...]}
        }, ...
      }
    }

Each ``<seg>`` carries the keys ``reconstruct_segs_from_xlsx`` produces
(start_time / end_time as ISO-8601 UTC strings, start_soc / end_soc /
delta_soc_pct / delta_energy_kwh / effective_capacity_kwh / energy_source,
plus charge latitude/longitude/charge_type or discharge lat_/lon_ endpoints
and odo_start_km/odo_end_km). ``original`` is present on every date iff
``original_available`` is true; anchors (``_anchor_*``) are NOT in the JSON —
they are interpolated here from the raw CSVs (:func:`attach_anchors_from_df`).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from jolt_toolkit.report_generator.segmentation.constants import (
    AC_COL,
    DC_COL,
    MASS_COL,
    MOVING_COL,
    SOC_COL,
    TIME_COL,
    TOTAL_ENERGY_COL,
    VEHICLE_CONFIG,
)
from jolt_toolkit.report_generator.segmentation.mass_aggregation import (
    resolve_mass_agg,
)
from jolt_toolkit.report_generator.segmentation.mass_clustering import (
    cluster_mass_data,
)
from jolt_toolkit.report_generator.segmentation.timeutil import _to_utc

# Skill-local siblings (require code/ on sys.path — the entry CLIs bootstrap it).
from validation_figure import plot_leg_validation

logger = logging.getLogger(__name__)

#: Schema tag both sides of the CLI contract assert on.
SEGS_JSON_SCHEMA = "report-visuals.finetuned-segs/v1"


# =============================================================================
# Segments-JSON loading
# =============================================================================


def _seg_from_jsonable(seg: dict) -> dict:
    """Inverse of finetune's ``_seg_to_jsonable``: ISO strings → UTC Timestamps."""
    out = dict(seg)
    for key in ("start_time", "end_time"):
        v = out.get(key)
        if isinstance(v, str):
            ts = pd.Timestamp(v)
            out[key] = (
                ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
            )
    return out


def _load_segs_json(path: str | Path) -> tuple[bool, dict]:
    """Parse the segments JSON → ``(original_available, by_date)``.

    ``by_date[date]`` is ``(ft_charge, ft_discharge, orig_charge, orig_discharge)``
    with the original pair ``(None, None)`` when no original xlsx was available.
    Seg dicts are shared per date (NOT copied per leg) — this mirrors the old
    in-process caching, where ``attach_anchors_from_df`` mutated the same dicts
    across a date's legs.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    schema = payload.get("schema")
    if schema != SEGS_JSON_SCHEMA:
        raise ValueError(
            f"segments JSON schema mismatch: got {schema!r}, "
            f"expected {SEGS_JSON_SCHEMA!r}"
        )
    original_available = bool(payload.get("original_available", False))
    by_date: dict = {}
    for date_str, entry in (payload.get("by_date") or {}).items():
        ft = entry.get("finetuned") or {}
        ft_c = [_seg_from_jsonable(s) for s in ft.get("charge", [])]
        ft_d = [_seg_from_jsonable(s) for s in ft.get("discharge", [])]
        if original_available:
            og = entry.get("original") or {}
            og_c = [_seg_from_jsonable(s) for s in og.get("charge", [])]
            og_d = [_seg_from_jsonable(s) for s in og.get("discharge", [])]
        else:
            og_c, og_d = None, None
        by_date[date_str] = (ft_c, ft_d, og_c, og_d)
    return original_available, by_date


# =============================================================================
# Helpers moved verbatim from finetune.py (rendering half)
# =============================================================================


def _reg_from_name(filename: str) -> str:
    """Parse 'jolt_report_REG_DATE_DATE[.*].xlsx' → 'REG'."""
    m = re.match(r"jolt_report_([A-Z0-9]+)_\d{8}_\d{8}", filename)
    if not m:
        raise ValueError(f"Cannot infer vehicle REG from filename: {filename}")
    return m.group(1)


def _cumulative_relative_kwh(
    df_leg: pd.DataFrame,
    *cols: str,
) -> tuple[pd.Series, pd.DatetimeIndex] | tuple[None, None]:
    """Build a relative-kWh cumulative series from one or more Wh columns.

    Returns ``(values_kwh, times_utc)`` where ``values_kwh[i]`` is the sum of
    ``cols`` at time ``times_utc[i]`` minus the first sample (so the series
    starts at 0). Mirrors the segmentation ``_build_energy_series`` exactly so
    ``_anchor_*_rel_kwh`` values land on the same curve the original
    algorithm's triangles sit on.
    """
    if not cols or TIME_COL not in df_leg.columns:
        return None, None
    missing = [c for c in cols if c not in df_leg.columns]
    if missing:
        return None, None
    sub = df_leg[[TIME_COL, *cols]].copy()
    for c in cols:
        sub[c] = pd.to_numeric(sub[c], errors="coerce")
    sub[TIME_COL] = pd.to_datetime(sub[TIME_COL], errors="coerce", utc=True)
    sub = sub.dropna(subset=[TIME_COL, *cols]).sort_values(TIME_COL)
    if len(sub) < 2:
        return None, None
    combined = sub[list(cols)].sum(axis=1)
    base = combined.iloc[0]
    values_kwh = (combined - base) / 1000.0
    times_utc = pd.DatetimeIndex(sub[TIME_COL].values, tz="UTC")
    return values_kwh.reset_index(drop=True), times_utc


def _interp_at(
    values: pd.Series,
    times: pd.DatetimeIndex,
    t: pd.Timestamp,
) -> float:
    """Linear interpolation of ``values[times]`` at timestamp ``t``.

    Clamps to first / last sample when ``t`` falls outside the range so the
    nearest-endpoint fallback still produces a sane anchor rather than NaN.
    """
    if values is None or times is None or len(values) == 0:
        return float("nan")
    if t <= times[0]:
        return float(values.iloc[0])
    if t >= times[-1]:
        return float(values.iloc[-1])
    idx_right = int(times.searchsorted(t, side="left"))
    if idx_right <= 0:
        return float(values.iloc[0])
    if idx_right >= len(values):
        return float(values.iloc[-1])
    t_l = times[idx_right - 1]
    t_r = times[idx_right]
    v_l = float(values.iloc[idx_right - 1])
    v_r = float(values.iloc[idx_right])
    span = (t_r - t_l).total_seconds()
    if span <= 0:
        return v_r
    frac = (t - t_l).total_seconds() / span
    return v_l + (v_r - v_l) * frac


def attach_anchors_from_df(
    segs: list[dict],
    df_leg: pd.DataFrame,
    *,
    kind: str,
    ac_col: str,
    dc_col: str,
    panel3_col: str,
) -> None:
    """Populate ``_anchor_*`` fields on reconstructed segs in place.

    Charge segs → anchors sit on the AC+DC cumulative kWh curve (Panel 2).
    Discharge segs → anchors sit on the ``panel3_col`` cumulative kWh curve
    (Panel 3). The time axis is taken from each seg's own ``start_time`` /
    ``end_time`` (the xlsx rows are the authoritative boundaries after
    finetune); values are linearly interpolated from the raw CSV.

    If required columns are missing or the leg CSV is empty the seg is left
    untouched (``_mark_anchors_stored`` then silently skips it).
    """
    if not segs:
        return
    if kind == "charge":
        values, times = _cumulative_relative_kwh(df_leg, ac_col, dc_col)
    elif kind == "discharge":
        values, times = _cumulative_relative_kwh(df_leg, panel3_col)
    else:
        raise ValueError(
            f"attach_anchors_from_df: kind must be "
            f'"charge" or "discharge", got {kind!r}'
        )
    if values is None or times is None:
        return
    for seg in segs:
        t_s = _to_utc(seg.get("start_time"))
        t_e = _to_utc(seg.get("end_time"))
        if t_s is None or t_e is None:
            continue
        v_s = _interp_at(values, times, t_s)
        v_e = _interp_at(values, times, t_e)
        seg["_anchor_start_time"] = t_s
        seg["_anchor_end_time"] = t_e
        seg["_anchor_start_rel_kwh"] = (
            round(v_s, 4) if not np.isnan(v_s) else float("nan")
        )
        seg["_anchor_end_rel_kwh"] = (
            round(v_e, 4) if not np.isnan(v_e) else float("nan")
        )


def _segs_equal(a: list[dict], b: list[dict]) -> bool:
    """Compare two seg lists by (start_time, end_time) tuples.

    Used by :func:`paint_finetuned_figures` to decide whether a date's
    finetuned segs match the original segs byte-for-byte (so we can skip
    redrawing and just fall back to the original PNG). We intentionally ignore
    numeric fields (kwh, soc_estimate floating-point noise) and compare only
    the temporal boundary tuples, which fully determine segment identity.
    """
    if len(a) != len(b):
        return False
    ka = sorted((_to_utc(s["start_time"]), _to_utc(s["end_time"])) for s in a)
    kb = sorted((_to_utc(s["start_time"]), _to_utc(s["end_time"])) for s in b)
    return ka == kb


def _leg_time_bounds(df: pd.DataFrame):
    times = pd.to_datetime(df[TIME_COL], errors="coerce", utc=True).dropna()
    if times.empty:
        return None, None
    return times.min(), times.max()


def _overlap(seg: dict, t_s, t_e) -> bool:
    if t_s is None or t_e is None:
        return True
    try:
        s = _to_utc(seg["start_time"])
        e = _to_utc(seg["end_time"])
    except KeyError:
        return True
    return s <= t_e and e >= t_s


def _slice_logger(df: pd.DataFrame | None, t_s, t_e):
    if df is None or df.empty or t_s is None or t_e is None:
        return None
    try:
        sliced = df.loc[t_s:t_e]
        return sliced if not sliced.empty else None
    except Exception:
        return None


def _try_fetch_logger(reg: str, xlsx_name: str):
    """Best-effort SRF fetch for Logger speed / mass.

    Returns ``(speed_df, mass_df)`` or ``(None, None)`` on any failure. Do not
    block the finetuned repaint on missing Logger data. Skips silently if
    ``SRF_API_KEY`` is not set in the environment. (Port of the finetune
    library's ``_try_fetch_logger``; the orchestrator is the skill-local
    sibling ``validation_generator`` now, not the removed package module.)
    """
    import os as _os

    if not _os.environ.get("SRF_API_KEY"):
        return None, None
    try:
        from validation_generator import ValidationGenerator

        cfg = VEHICLE_CONFIG.get(reg, {})
        reg_srf = cfg.get("srf_reg")
        if not reg_srf:
            return None, None
        m = re.search(r"(\d{8})_(\d{8})", xlsx_name)
        if not m:
            return None, None
        ds = datetime.strptime(m.group(1), "%Y%m%d")
        de = datetime.strptime(m.group(2), "%Y%m%d")
        gen = ValidationGenerator()
        return gen._fetch_logger_data(reg_srf, ds, de)
    except Exception as exc:
        logger.info("paint_finetuned_figures: Logger fetch skipped (%s)", exc)
        return None, None


# =============================================================================
# Public: paint_finetuned_figures (was finetune.regenerate_figures' loop)
# =============================================================================


def paint_finetuned_figures(
    xlsx_path: str | Path,
    segs_json_path: str | Path,
    raw_telematics_dir: str | Path,
    out_dir: str | Path,
    fig_suffix: str = "_finetuned",
) -> int:
    """Paint ``*{fig_suffix}.png`` validation figures from a segments JSON.

    For every ``raw_<date>_<idx>.csv`` inside the xlsx's ``[start, end]``
    date range we:
      1. Look up that date's reconstructed ``(charge_segs, discharge_segs)``
         in the segments JSON (finetuned + optional original — produced by
         the report-finetuner skill's ``dump_segs_json``)
      2. If the JSON carries original segs, compare per date:
           - Segs identical (same start/end tuple set)
             → **skip** entirely — no ``_finetuned.png`` is produced (a stale
             one from a previous run is removed). The finetuned inspect HTML
             falls back to the original ``validation_<...>.png`` for that day.
           - Segs differ
             → draw with base = original (red/green), overlay = finetuned
             (orange/cyan) so visual comparison is obvious
      3. If no original is available (legacy behaviour), draw with only the
         finetuned segs and no overlay.

    Returns the number of ``{fig_suffix}.png`` files produced (overlay + plain
    draws only; skipped-unchanged days contribute zero). Never touches the
    original ``validation_*.png`` (output names always carry ``fig_suffix``).
    """
    xlsx_path = Path(xlsx_path)
    raw_dir = Path(raw_telematics_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    reg = _reg_from_name(xlsx_path.name)
    cfg = VEHICLE_CONFIG.get(reg, {})
    ac_col = cfg.get("ac_col", AC_COL)
    dc_col = cfg.get("dc_col", DC_COL)
    total_col = cfg.get("total_energy_col", TOTAL_ENERGY_COL)
    moving_col = cfg.get("moving_energy_col", MOVING_COL)
    mass_col = cfg.get("mass_col", MASS_COL)
    speed_col = cfg.get("speed_col", "wheel_based_speed")
    mass_agg = resolve_mass_agg(reg)  # v2.2.6: 图上质量与报告同口径稳健聚合

    # Derive [period_start, period_end] from xlsx name so we skip raw CSVs
    # outside the report's date range (a vehicle's raw_telematics/ folder is
    # shared across all periods).
    m = re.search(r"(\d{8})_(\d{8})", xlsx_path.name)
    if m:
        period_start = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}"
        period_end = f"{m.group(2)[:4]}-{m.group(2)[4:6]}-{m.group(2)[6:]}"
    else:
        period_start = "0000-00-00"
        period_end = "9999-99-99"

    original_available, segs_by_date = _load_segs_json(segs_json_path)

    # Best-effort Logger fetch (optional)
    logger_speed_all, logger_mass_all = _try_fetch_logger(reg, xlsx_path.name)

    raw_csvs = sorted(raw_dir.glob("raw_*.csv"))
    n_out = 0
    n_skipped = 0
    n_overlay = 0
    n_plain = 0
    for csv_path in raw_csvs:
        m2 = re.match(r"raw_(\d{4}-\d{2}-\d{2})_(\d+)\.csv$", csv_path.name)
        if not m2:
            continue
        date_str, idx_str = m2.group(1), m2.group(2)
        if not (period_start <= date_str <= period_end):
            continue
        leg_suffix = f"{date_str}_{idx_str}"

        df_leg = pd.read_csv(csv_path, dtype=str, low_memory=False)
        if df_leg.empty or SOC_COL not in df_leg.columns:
            continue
        # 在 plot_leg_validation 之前跑 mass 聚类，生成 ``mass_cluster`` 列。
        # Panel 4 的 seg-mean mass 标注（含 overlay ``[FT] XX.X t``）依赖该列
        # 做去噪聚合；若缺失则 Panel 4 会退化为只画原始散点（见 v2.2.2
        # 限制），finetune 图与 production 图因此不一致。
        if mass_col in df_leg.columns:
            try:
                # v2.2.4: 传 speed_col 让 finetune 图的 mass 聚类与 production 一致
                # （聚类均值只用行驶中读数；speed 列缺失时自动回退全部有效读数）。
                df_leg = cluster_mass_data(
                    df_leg, mass_col=mass_col, speed_col=speed_col
                )
            except Exception as exc:
                logger.debug(
                    "paint_finetuned_figures: cluster_mass_data failed "
                    "on %s (%s) — Panel 4 mass labels skipped",
                    csv_path.name,
                    exc,
                )

        # Dates absent from the JSON behave like reconstruct-with-no-rows
        # (empty seg lists) — cannot happen when the JSON was produced by
        # dump_segs_json over the same raw dir/period, but keeps manual
        # invocations sane.
        ft_c_segs, ft_d_segs, orig_c_all, orig_d_all = segs_by_date.get(
            date_str, ([], [], None, None)
        )
        orig_c_segs: list[dict] = orig_c_all if orig_c_all is not None else []
        orig_d_segs: list[dict] = orig_d_all if orig_d_all is not None else []

        # Keep only segs that overlap this leg's time window
        t_s, t_e = _leg_time_bounds(df_leg)
        ft_c_segs = [s for s in ft_c_segs if _overlap(s, t_s, t_e)]
        ft_d_segs = [s for s in ft_d_segs if _overlap(s, t_s, t_e)]
        orig_c_segs = [s for s in orig_c_segs if _overlap(s, t_s, t_e)]
        orig_d_segs = [s for s in orig_d_segs if _overlap(s, t_s, t_e)]

        out_path = out_dir / f"validation_{reg}_{leg_suffix}{fig_suffix}.png"

        # ── Path 1: no original → fall back to plain finetuned draw ────────
        if not original_available:
            panel3_col = moving_col
            if ft_d_segs and ft_d_segs[0].get("energy_source") == "total_energy":
                panel3_col = total_col
            leg_logger_spd = _slice_logger(logger_speed_all, t_s, t_e)
            leg_logger_mass = _slice_logger(logger_mass_all, t_s, t_e)
            # 从 df_leg 的累积能量列线性插值出 ▼▲ 锚点位置，使 plain 图的
            # Panel 2 / 3 三角形与原 production 图风格一致。
            attach_anchors_from_df(
                ft_c_segs,
                df_leg,
                kind="charge",
                ac_col=ac_col,
                dc_col=dc_col,
                panel3_col=panel3_col,
            )
            attach_anchors_from_df(
                ft_d_segs,
                df_leg,
                kind="discharge",
                ac_col=ac_col,
                dc_col=dc_col,
                panel3_col=panel3_col,
            )
            try:
                plot_leg_validation(
                    df_leg,
                    ft_c_segs,
                    ft_d_segs,
                    reg,
                    leg_suffix,
                    out_path,
                    ac_col=ac_col,
                    dc_col=dc_col,
                    panel3_col=panel3_col,
                    mass_col=mass_col,
                    speed_col=speed_col,
                    logger_speed_df=leg_logger_spd,
                    logger_mass_df=leg_logger_mass,
                    mass_agg=mass_agg,
                )
                n_out += 1
                n_plain += 1
            except Exception as exc:
                logger.warning(
                    "paint_finetuned_figures: skip %s (%s)", leg_suffix, exc
                )
            continue

        # ── Path 2: segs unchanged → skip entirely ───────────────────────
        # No ``_finetuned.png`` is produced for unchanged days; the inspect
        # HTML falls back to the original ``validation_<...>.png`` so the
        # viewer still shows every day. Stale ``_finetuned.png`` from a
        # previous run is removed so the HTML falls back correctly.
        if _segs_equal(ft_c_segs, orig_c_segs) and _segs_equal(ft_d_segs, orig_d_segs):
            if out_path.exists():
                try:
                    out_path.unlink()
                except Exception as exc:
                    logger.warning(
                        "paint_finetuned_figures: could not remove stale %s " "(%s)",
                        out_path.name,
                        exc,
                    )
            n_skipped += 1
            continue

        # ── Path 3: segs changed → draw base=original + overlay=finetuned ─
        panel3_col = moving_col
        # Pick panel3 col based on the original (base) segs for consistency
        # with how the original PNG was drawn.
        if orig_d_segs and orig_d_segs[0].get("energy_source") == "total_energy":
            panel3_col = total_col
        elif ft_d_segs and ft_d_segs[0].get("energy_source") == "total_energy":
            panel3_col = total_col
        leg_logger_spd = _slice_logger(logger_speed_all, t_s, t_e)
        leg_logger_mass = _slice_logger(logger_mass_all, t_s, t_e)
        # 为 base（原 segs）和 overlay（finetuned segs）都补齐 ▼▲ 锚点，
        # 让 Panel 2 / 3 能同时画出红绿 ▼▲（original）+ 橙青 ▼▲（[FT]）。
        attach_anchors_from_df(
            orig_c_segs,
            df_leg,
            kind="charge",
            ac_col=ac_col,
            dc_col=dc_col,
            panel3_col=panel3_col,
        )
        attach_anchors_from_df(
            orig_d_segs,
            df_leg,
            kind="discharge",
            ac_col=ac_col,
            dc_col=dc_col,
            panel3_col=panel3_col,
        )
        attach_anchors_from_df(
            ft_c_segs,
            df_leg,
            kind="charge",
            ac_col=ac_col,
            dc_col=dc_col,
            panel3_col=panel3_col,
        )
        attach_anchors_from_df(
            ft_d_segs,
            df_leg,
            kind="discharge",
            ac_col=ac_col,
            dc_col=dc_col,
            panel3_col=panel3_col,
        )
        try:
            plot_leg_validation(
                df_leg,
                orig_c_segs,
                orig_d_segs,
                reg,
                leg_suffix,
                out_path,
                ac_col=ac_col,
                dc_col=dc_col,
                panel3_col=panel3_col,
                mass_col=mass_col,
                speed_col=speed_col,
                logger_speed_df=leg_logger_spd,
                logger_mass_df=leg_logger_mass,
                overlay_charge_segs=ft_c_segs,
                overlay_discharge_segs=ft_d_segs,
                mass_agg=mass_agg,
            )
            n_out += 1
            n_overlay += 1
        except Exception as exc:
            logger.warning("paint_finetuned_figures: skip %s (%s)", leg_suffix, exc)

    logger.info(
        "paint_finetuned_figures: skipped %d, overlaid %d (plain=%d) — "
        "wrote %d PNG(s) to %s",
        n_skipped,
        n_overlay,
        n_plain,
        n_out,
        out_dir,
    )
    return n_out


# =============================================================================
# Public: write_finetuned_inspect_html (was finetune.regenerate_inspect_html)
# =============================================================================


def write_finetuned_inspect_html(
    xlsx_path: str | Path,
    out_path: str | Path | None = None,
    fig_suffix: str = "_finetuned",
) -> Path:
    """Generate an inspect HTML pointing at ``validation_*{fig_suffix}.png``.

    If ``out_path`` is None, writes
    ``inspect_<basename>_finetuned.html`` next to the xlsx.

    This is a lightweight variant of the base ``_write_html_viewer`` (sibling
    ``html_viewer``) — we can't reuse the base viewer directly because it
    globs ``validation_{REG}_*.png`` unconditionally and would pick up the
    non-finetuned figures too.
    """
    xlsx_path = Path(xlsx_path)
    reg = _reg_from_name(xlsx_path.name)
    m = re.search(r"(\d{8})_(\d{8})", xlsx_path.name)
    if not m:
        raise ValueError(f"Cannot parse date range from {xlsx_path.name}")
    ds_str, de_str = m.group(1), m.group(2)
    period_start = f"{ds_str[:4]}-{ds_str[4:6]}-{ds_str[6:]}"
    period_end = f"{de_str[:4]}-{de_str[4:6]}-{de_str[6:]}"

    out_dir = xlsx_path.parent
    fig_dir = out_dir / "validation_figures"
    if not fig_dir.exists():
        raise FileNotFoundError(f"{fig_dir} does not exist")

    # Enumerate every original ``validation_<reg>_<date>_<idx>.png`` in the
    # period. For each one, if a ``*_finetuned.png`` sibling exists → the
    # day was modified by apply_operations / the finetuned repaint; else →
    # unchanged, fall back to the original. This lets the HTML cover every
    # day of the period even when most days have no finetuned output.
    all_originals = sorted(
        p
        for p in fig_dir.glob(f"validation_{reg}_*.png")
        if not p.stem.endswith(fig_suffix)
    )
    if not all_originals:
        raise FileNotFoundError(f"No validation_{reg}_*.png figures in {fig_dir}")

    date_re = re.compile(rf"validation_{re.escape(reg)}_(\d{{4}}-\d{{2}}-\d{{2}})_")
    figs: list[Path] = []
    is_modified: list[bool] = []
    for p in all_originals:
        dm = date_re.match(p.name)
        if not (dm and period_start <= dm.group(1) <= period_end):
            continue
        ft_png = p.with_name(p.stem + fig_suffix + p.suffix)
        if ft_png.exists():
            figs.append(ft_png)
            is_modified.append(True)
        else:
            figs.append(p)
            is_modified.append(False)
    if not figs:
        raise FileNotFoundError(
            f"No figures in date range {period_start}..{period_end}"
        )

    rel = [f"validation_figures/{p.name}" for p in figs]
    # Append a lightweight tag so users can see at a glance which days were
    # touched by the finetune pass and which fell back to the original PNG.
    labels = [
        p.stem + (" [modified]" if mod else " (unchanged — original)")
        for p, mod in zip(figs, is_modified)
    ]

    if out_path is None:
        # Avoid doubling the suffix when xlsx stem already ends with it
        # (e.g. jolt_report_X_..._finetuned.xlsx → inspect_..._finetuned.html,
        # NOT ..._finetuned_finetuned.html).
        stem = xlsx_path.stem
        if not stem.endswith(fig_suffix):
            stem += fig_suffix
        out_path = out_dir / ("inspect_" + stem + ".html")
    else:
        out_path = Path(out_path)

    imgs_js = "[\n" + ",\n".join(f'        "{r}"' for r in rel) + "\n    ]"
    labels_js = "[\n" + ",\n".join(f'        "{l}"' for l in labels) + "\n    ]"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>JOLT Inspection (finetuned) — {reg} {period_start} – {period_end}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ display: flex; height: 100vh; font-family: Arial, sans-serif; }}
  #sidebar {{ width: 260px; min-width: 160px; background: #1e1e2e; color: #cdd6f4;
              overflow-y: auto; flex-shrink: 0; padding: 8px 0; }}
  #sidebar h2 {{ font-size: 13px; padding: 8px 12px 4px; color: #89b4fa;
                 border-bottom: 1px solid #313244; margin-bottom: 4px; }}
  #sidebar ul {{ list-style: none; }}
  #sidebar li {{ padding: 5px 12px; cursor: pointer; font-size: 12px;
                  border-left: 3px solid transparent; }}
  #sidebar li:hover {{ background: #313244; }}
  #sidebar li.active {{ background: #313244; border-left-color: #f9e2af;
                         color: #f9e2af; }}
  #main {{ flex: 1; display: flex; flex-direction: column;
            background: #11111b; overflow: hidden; }}
  #toolbar {{ display: flex; align-items: center; gap: 10px;
               padding: 8px 16px; background: #181825; border-bottom: 1px solid #313244; }}
  #toolbar button {{ padding: 4px 14px; background: #313244; color: #cdd6f4;
                      border: 1px solid #45475a; border-radius: 4px;
                      cursor: pointer; font-size: 13px; }}
  #toolbar button:hover {{ background: #45475a; }}
  #counter {{ color: #a6adc8; font-size: 13px; }}
  #label {{ color: #f9e2af; font-size: 12px; font-family: monospace;
             flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  #img-wrap {{ flex: 1; display: flex; align-items: center;
               justify-content: center; overflow: auto; padding: 12px; }}
  #fig {{ max-width: 100%; max-height: 100%; object-fit: contain; }}
  #badge {{ background: #f9e2af; color: #1e1e2e; padding: 2px 8px;
            border-radius: 3px; font-size: 11px; font-weight: bold; }}
  /* Row tags: subtle grey 'unchanged' vs amber 'modified', small size */
  .tag {{ font-size: 10px; margin-left: 6px; padding: 1px 4px;
          border-radius: 2px; font-family: sans-serif; }}
  .tag-mod {{ background: #f9e2af; color: #1e1e2e; font-weight: bold; }}
  .tag-unchanged {{ background: transparent; color: #7f849c;
                    font-style: italic; }}
</style>
</head>
<body>
<div id="sidebar">
  <h2>{reg} &nbsp;{period_start} – {period_end}<br><span id="badge">FINETUNED</span></h2>
  <ul id="list"></ul>
</div>
<div id="main">
  <div id="toolbar">
    <button onclick="go(-1)">&#9664; Prev</button>
    <button onclick="go(1)">Next &#9654;</button>
    <span id="counter"></span>
    <span id="label"></span>
  </div>
  <div id="img-wrap"><img id="fig" src="" alt="validation figure"></div>
</div>
<script>
const imgs   = {imgs_js};
const labels = {labels_js};
let cur = 0;
const listEl    = document.getElementById("list");
const figEl     = document.getElementById("fig");
const counterEl = document.getElementById("counter");
const labelEl   = document.getElementById("label");
labels.forEach((lb, i) => {{
  const li = document.createElement("li");
  // Strip the ``validation_<REG>_`` prefix so the sidebar shows
  // ``<date>_<idx>[_finetuned] [modified]`` (or the unchanged variant).
  // Split off the bracketed tag and render it as a coloured pill.
  const short = lb.replace(/^validation_[^_]+_/, "");
  const m = short.match(/^(.*?)\s+(\[modified\]|\(unchanged — original\))$/);
  if (m) {{
    const base = document.createTextNode(m[1]);
    li.appendChild(base);
    const tag = document.createElement("span");
    tag.textContent = m[2];
    tag.className = "tag " + (m[2] === "[modified]" ? "tag-mod" : "tag-unchanged");
    li.appendChild(tag);
  }} else {{
    li.textContent = short;
  }}
  li.onclick = () => show(i);
  listEl.appendChild(li);
}});
function show(i) {{
  cur = i;
  figEl.src = imgs[i];
  counterEl.textContent = (i + 1) + " / " + imgs.length;
  labelEl.textContent   = labels[i];
  document.querySelectorAll("#list li").forEach((el, j) =>
    el.classList.toggle("active", j === i));
  document.querySelectorAll("#list li")[i]
    .scrollIntoView({{block: "nearest"}});
}}
function go(d) {{ show((cur + d + imgs.length) % imgs.length); }}
document.addEventListener("keydown", e => {{
  if (e.key === "ArrowLeft"  || e.key === "ArrowUp")   go(-1);
  if (e.key === "ArrowRight" || e.key === "ArrowDown")  go(1);
}});
show(0);
</script>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")
    logger.info(
        "finetuned_visuals: wrote inspect HTML %s (%d figures)",
        out_path.name,
        len(figs),
    )
    return out_path
