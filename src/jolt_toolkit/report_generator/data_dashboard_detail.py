"""Per-day drill-down detail pages for the data-availability dashboard.

The three-panel ``data_dashboard.html`` (see :mod:`data_dashboard`) shows *which*
calendar days carry telematics / logger / charger data. This module adds the
*drill-down*: one self-contained ``detail_<REG>.html`` per vehicle that embeds
every data-bearing day's raw time-series channels and renders them as a left
channel checklist + a right column of stacked interactive charts (vendored
uPlot), with trip / charge segment bands like ``inspect.html``.

Design (see the approved plan)
------------------------------
- **One page per vehicle** — all the vehicle's days are embedded, so a page opens
  offline by double-click with no cross-page ``fetch``. The dashboard calendar
  links a data-bearing cell to ``detail_<REG>.html?date=YYYY-MM-DD&mode=…``.
- **Channel concepts** — ``CONCEPT_REGISTRY`` maps ``(source, raw_column)`` to a
  display concept. Same-meaning channels from different sources collapse to one
  concept (one chart, one overlaid series per source): e.g. ``speed`` from the
  telematics feed *and* the logger CAN/GPS bus. :func:`resolve_vehicle_concepts`
  keeps only the concepts a given vehicle actually has columns for.
- **Resolution** — telematics is stored at native rate (already sparse). Logger
  is stored twice: a downsampled ``lo`` (≤3000 pts) plus a full 1 Hz ``hi``. Both
  tiers are gzip+base64 and lazily inflated in the browser via the built-in
  ``DecompressionStream("gzip")`` (offline, no dependency): the ``lo`` series is
  decoded on first view of a day, the ``hi`` series only when the user flips the
  low/high toggle. Decoded series are cached per day so re-renders are instant.
- **Compact payload** — time is ``int`` seconds-from-UTC-midnight (LE ``Uint32``)
  and values are LE ``Float32`` (``NaN`` = gap). Each ``lo`` series is one gzipped
  buffer = its ``Uint32`` time samples concatenated with its ``Float32`` values
  (one inflate per series). The logger ``hi`` time grid is gzipped once per day
  (all logger concepts ride the same concatenated 1 Hz index) and each ``hi``
  value block is gzipped on its own.
- **Axes** — the time x-axis is FIXED to the full day (0…86400 s) on every chart
  via injected ``[0, 86400]`` sentinels + zero x-padding (zoom/pan stays live;
  double-click resets to the full day). Each concept carries a y-axis spec: a
  fixed ``[min, max]`` for bounded physical signals (speed, SOC, mass, pedals,
  weather…) or ``None`` = autoscale for cumulative counters (energy, distance)
  and route-dependent channels (altitude, lat, lon). See ``_Y_SPECS``.

Public API
----------
``CONCEPT_REGISTRY`` / ``resolve_vehicle_concepts`` — channel-concept catalogue.
``group_raw_files_by_date`` / ``read_telematics_day`` / ``read_logger_day`` /
``read_charger_windows`` — raw scan-by-day (reusing the CSV-read patterns from
:mod:`diesel_pipeline` and :mod:`validation_generator`).
``downsample_minmax`` / ``pack_u32`` / ``pack_f32`` — series compaction.
``build_vehicle_payload`` / ``render_detail_html`` / ``write_detail_pages`` —
orchestration. ``_load_uplot_assets`` / ``fetch_uplot`` — offline uPlot vendoring.
"""

from __future__ import annotations

import base64
import csv
import gzip
import html
import json
import logging
import urllib.request
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from jolt_toolkit.report_generator.data_dashboard import (
    _LOGGER_FNAME_RE,
    _TELEMATICS_FNAME_RE,
    RAW_CHARGER_CSV,
    RAW_CHARGER_DIR,
    RAW_LOGGER_DIRS,
    RAW_TELEMATICS_DIR,
    _raw_date_sane,
    build_day_segments,
)
from jolt_toolkit.report_generator.segment_algorithms import (
    MIN_CLUSTER_GAP_KG,
    MOVING_SPEED_THRESHOLD_KMH,
    TRACTOR_ONLY_MAX_KG,
    _agg_mass,
    cluster_mass_data,
    resolve_mass_agg,
)

LOG = logging.getLogger("data_dashboard.detail")

# ── Source identity / colours (mirror the dashboard category colours) ─────────
TELEMATICS = "telematics"
LOGGER = "logger"
CHARGER = "charger"
SOURCE_COLOURS = {
    TELEMATICS: "#2563EB",  # blue
    LOGGER: "#16A34A",  # green
    CHARGER: "#F59E0B",  # amber
}
SOURCE_LABELS = {TELEMATICS: "Telematics", LOGGER: "Logger", CHARGER: "Charger"}

# Per-day downsample budget for the eager ``lo`` series (min/max keeps spikes).
LO_MAX_PTS = 3000

# uPlot vendored asset location (see assets/uplot/PROVENANCE.txt).
_UPLOT_DIR = Path(__file__).resolve().parent / "assets" / "uplot"
_UPLOT_JS = _UPLOT_DIR / "uPlot.iife.min.js"
_UPLOT_CSS = _UPLOT_DIR / "uPlot.min.css"
_UPLOT_VERSION = "1.6.32"
_UPLOT_BASE = f"https://cdn.jsdelivr.net/npm/uplot@{_UPLOT_VERSION}/dist"


# ── Value transforms (raw column units → display units) ───────────────────────
def _t_id(s: pd.Series) -> pd.Series:
    return s


def _t_wh_to_kwh(s: pd.Series) -> pd.Series:
    return s / 1000.0


def _t_ms_to_kmh(s: pd.Series) -> pd.Series:
    return s * 3.6


def _t_kg_to_t(s: pd.Series) -> pd.Series:
    return s / 1000.0


def _t_m_to_km(s: pd.Series) -> pd.Series:
    return s / 1000.0


_TRANSFORMS = {
    "id": _t_id,
    "wh_to_kwh": _t_wh_to_kwh,
    "ms_to_kmh": _t_ms_to_kmh,
    "kg_to_t": _t_kg_to_t,
    "m_to_km": _t_m_to_km,
}


# ── Channel-concept registry ──────────────────────────────────────────────────
# Each concept lists, per source, an ordered list of candidate columns; the first
# candidate present (after resolving any ``cfg_key`` against the vehicle config)
# wins. A candidate is ``{"col": <fixed name>, "cfg_key": <vehicles.json key>,
# "transform": <name in _TRANSFORMS>}``. Cross-source concepts (both telematics
# and logger candidates) collapse to one chart with one overlaid series each.
def _cand(col=None, cfg_key=None, transform="id") -> dict:
    return {"col": col, "cfg_key": cfg_key, "transform": transform}


CONCEPT_REGISTRY: list[dict] = [
    # ── Motion ────────────────────────────────────────────────────────────────
    {
        "id": "speed",
        "name": "Vehicle speed",
        "unit": "km/h",
        "group": "Motion",
        "default": True,
        "sources": {
            TELEMATICS: [
                _cand(cfg_key="speed_col"),
                _cand(col="speed"),
                _cand(col="wheel_based_speed"),
                _cand(col="gnss_speed"),
            ],
            LOGGER: [
                _cand(col="CCVS wheel based vehicle speed"),
                _cand(col="2 speed", transform="ms_to_kmh"),
            ],
        },
    },
    {
        "id": "distance",
        "name": "Total distance",
        "unit": "km",
        "group": "Motion",
        "default": False,
        # Cumulative odometer / total-vehicle-distance counter (→ km). Telematics
        # reports ``odometer`` in km (the column the PDF-briefing raw-KPI path
        # reads), with the J1939 high-resolution ``hr_total_vehicle_distance`` (m)
        # as a finer fallback for feeds that omit the km odometer. The logger
        # carries the diesel pipeline's VDHR ``hr total vehicle distance`` (already
        # km — see diesel_pipeline.DEFAULT_DISTANCE_COL), so diesel vehicles get
        # the channel too. A cumulative counter → y autoscales (see _Y_SPECS).
        "sources": {
            TELEMATICS: [
                _cand(cfg_key="odometer_col"),
                _cand(col="odometer"),
                _cand(col="hr_total_vehicle_distance", transform="m_to_km"),
            ],
            LOGGER: [_cand(col="VDHR hr total vehicle distance")],
        },
    },
    # ── Battery ───────────────────────────────────────────────────────────────
    {
        "id": "soc",
        "name": "State of charge",
        "unit": "%",
        "group": "Battery",
        "default": True,
        # Telematics only. The logger channel "6 charge" is the logger/phone
        # device battery, NOT the vehicle's state-of-charge, so it must never
        # feed this concept (it was previously mislabelled as vehicle SoC).
        "sources": {
            TELEMATICS: [_cand(col="electricBatteryLevelPercent")],
        },
    },
    # ── Weight ────────────────────────────────────────────────────────────────
    {
        "id": "mass",
        "name": "Gross combination mass",
        "unit": "t",
        "group": "Weight",
        "default": False,
        "sources": {
            TELEMATICS: [
                _cand(cfg_key="mass_col", transform="kg_to_t"),
                _cand(col="gross_combination_vehicle_weight", transform="kg_to_t"),
            ],
            LOGGER: [
                _cand(col="CVW gross combination vehicle weight", transform="kg_to_t"),
                _cand(col="VW cargo weight", transform="kg_to_t"),
            ],
        },
    },
    # ── Energy counters (telematics, cumulative Wh → kWh) ──────────────────────
    {
        "id": "energy_total",
        "name": "Total energy used",
        "unit": "kWh",
        "group": "Energy",
        "default": False,
        "sources": {
            TELEMATICS: [
                _cand(cfg_key="total_energy_col", transform="wh_to_kwh"),
                _cand(
                    col="total_electric_energy_used_plugged_in_included",
                    transform="wh_to_kwh",
                ),
                _cand(col="total_electric_energy_used", transform="wh_to_kwh"),
            ]
        },
    },
    {
        "id": "energy_ac",
        "name": "Energy charged AC",
        "unit": "kWh",
        "group": "Energy",
        "default": False,
        "sources": {
            TELEMATICS: [
                _cand(cfg_key="ac_col", transform="wh_to_kwh"),
                _cand(col="battery_pack_ac_watthours", transform="wh_to_kwh"),
            ]
        },
    },
    {
        "id": "energy_dc",
        "name": "Energy charged DC",
        "unit": "kWh",
        "group": "Energy",
        "default": False,
        "sources": {
            TELEMATICS: [
                _cand(cfg_key="dc_col", transform="wh_to_kwh"),
                _cand(col="battery_pack_dc_watthours", transform="wh_to_kwh"),
            ]
        },
    },
    {
        "id": "energy_propulsion",
        "name": "Propulsion energy",
        "unit": "kWh",
        "group": "Energy",
        "default": False,
        "sources": {
            TELEMATICS: [_cand(col="electric_energy_propulsion", transform="wh_to_kwh")]
        },
    },
    {
        "id": "energy_recup",
        "name": "Recuperated energy",
        "unit": "kWh",
        "group": "Energy",
        "default": False,
        "sources": {
            TELEMATICS: [
                _cand(
                    col="electric_energy_recuperation_watthours", transform="wh_to_kwh"
                )
            ]
        },
    },
    {
        "id": "energy_moving",
        "name": "Energy while moving",
        "unit": "kWh",
        "group": "Energy",
        "default": False,
        "sources": {
            TELEMATICS: [
                _cand(cfg_key="moving_energy_col", transform="wh_to_kwh"),
                _cand(
                    col="electric_energy_wheelbased_speed_over_zero",
                    transform="wh_to_kwh",
                ),
            ]
        },
    },
    # ── Position ──────────────────────────────────────────────────────────────
    {
        "id": "altitude",
        "name": "Altitude",
        "unit": "m",
        "group": "Position",
        "default": False,
        "sources": {
            TELEMATICS: [_cand(cfg_key="altitude_col"), _cand(col="gnss_altitude")],
            LOGGER: [_cand(col="2 altitude")],
        },
    },
    {
        "id": "latitude",
        "name": "Latitude",
        "unit": "°",
        "group": "Position",
        "default": False,
        "sources": {
            TELEMATICS: [_cand(col="latitude")],
            LOGGER: [_cand(col="2 latitude")],
        },
    },
    {
        "id": "longitude",
        "name": "Longitude",
        "unit": "°",
        "group": "Position",
        "default": False,
        "sources": {
            TELEMATICS: [_cand(col="longitude")],
            LOGGER: [_cand(col="2 longitude")],
        },
    },
    # ── Weather (logger channel 7) ────────────────────────────────────────────
    {
        "id": "weather_temp",
        "name": "Ambient temperature",
        "unit": "°C",
        "group": "Weather",
        "default": False,
        "sources": {LOGGER: [_cand(col="7 temperature")]},
    },
    {
        "id": "weather_pressure",
        "name": "Air pressure",
        "unit": "hPa",
        "group": "Weather",
        "default": False,
        "sources": {LOGGER: [_cand(col="7 pressure")]},
    },
    {
        "id": "weather_humidity",
        "name": "Humidity",
        "unit": "%",
        "group": "Weather",
        "default": False,
        "sources": {LOGGER: [_cand(col="7 humidity")]},
    },
    {
        "id": "weather_wind",
        "name": "Wind speed",
        "unit": "m/s",
        "group": "Weather",
        "default": False,
        "sources": {LOGGER: [_cand(col="7 wind speed")]},
    },
    # ── Driver inputs (CAN loggers only) ──────────────────────────────────────
    {
        "id": "pedal_accel",
        "name": "Accelerator pedal",
        "unit": "%",
        "group": "Driver inputs",
        "default": False,
        "sources": {LOGGER: [_cand(col="EEC2 accelerator pedal position 1")]},
    },
    {
        "id": "pedal_brake",
        "name": "Brake pedal",
        "unit": "%",
        "group": "Driver inputs",
        "default": False,
        "sources": {LOGGER: [_cand(col="EBC1 brake pedal position")]},
    },
]

# Group display order for the left checklist.
GROUP_ORDER = [
    "Motion",
    "Battery",
    "Weight",
    "Energy",
    "Position",
    "Weather",
    "Driver inputs",
]

# ── Per-concept y-axis spec ───────────────────────────────────────────────────
# ``(y_min, y_max)`` = a FIXED axis range (bounded physical signal — the chart
# always reads on the same data-characteristic scale, like the published figures);
# ``None`` = AUTO (let uPlot autoscale). The cumulative energy counters and the
# route-dependent position channels (altitude / lat / lon) have no universal range
# so they autoscale. Fixed bounds for speed (0–90 km/h) and mass (0–45 t) reuse
# the fleet-wide axis limits in ``report_builder.CHART_SPECS_*`` for consistency.
_Y_SPECS: dict[str, tuple[float, float] | None] = {
    "speed": (0, 90),  # km/h  — matches report EP-vs-Speed x-axis
    "distance": None,  # km    — cumulative odometer counter → AUTO
    "soc": (0, 100),  # %
    "mass": (0, 45),  # t     — matches report 0–45000 kg x-axis
    "energy_total": None,  # kWh   — cumulative counter → AUTO
    "energy_ac": None,
    "energy_dc": None,
    "energy_propulsion": None,
    "energy_recup": None,
    "energy_moving": None,
    "altitude": None,  # m     — route-dependent → AUTO
    "latitude": None,  # °     → AUTO
    "longitude": None,  # °     → AUTO
    "weather_temp": (-10, 40),  # °C
    "weather_pressure": (950, 1050),  # hPa
    "weather_humidity": (0, 100),  # %
    "weather_wind": (0, 30),  # m/s
    "pedal_accel": (0, 100),  # %     — J1939 SPN 91 (0–100 %)
    "pedal_brake": (0, 100),  # %     — J1939 SPN 521 (0–100 %)
}


def _resolve_candidate(cand: dict, cfg: dict, cols: set[str]) -> dict | None:
    """Resolve one candidate against a vehicle config + available columns."""
    col = cand.get("col")
    cfg_key = cand.get("cfg_key")
    if cfg_key:
        cfg_col = cfg.get(cfg_key)
        if cfg_col and cfg_col in cols:
            return {"col": cfg_col, "transform": cand.get("transform", "id")}
        # cfg key absent / column missing → fall through to a fixed candidate
        return None
    if col and col in cols:
        return {"col": col, "transform": cand.get("transform", "id")}
    return None


def resolve_vehicle_concepts(
    reg: str, cfg: dict, telem_cols: set[str], logger_cols: set[str]
) -> list[dict]:
    """Resolve ``CONCEPT_REGISTRY`` for one vehicle's available columns.

    ``telem_cols`` / ``logger_cols`` are the column names actually present (for a
    day, or the union across days). Returns the concepts that resolve at least
    one source, each as ``{"id", "name", "unit", "group", "default",
    "sources_resolved": {source: {"col", "transform"}}}`` — in registry order.
    """
    cols_by_source = {TELEMATICS: telem_cols, LOGGER: logger_cols}
    out: list[dict] = []
    for concept in CONCEPT_REGISTRY:
        resolved: dict[str, dict] = {}
        for source, candidates in concept["sources"].items():
            cols = cols_by_source.get(source, set())
            if not cols:
                continue
            for cand in candidates:
                res = _resolve_candidate(cand, cfg, cols)
                if res is not None:
                    resolved[source] = res
                    break
        if resolved:
            out.append(
                {
                    "id": concept["id"],
                    "name": concept["name"],
                    "unit": concept["unit"],
                    "group": concept["group"],
                    "default": concept["default"],
                    "y": _Y_SPECS.get(concept["id"]),  # fixed (min,max) | None=auto
                    "sources_resolved": resolved,
                }
            )
    return out


# ── Raw scan by day ───────────────────────────────────────────────────────────
def group_raw_files_by_date(reg_dir: Path) -> dict[str, dict[str, list[Path]]]:
    """Group a reg dir's raw CSVs by date → ``{date_iso: {telematics, logger}}``.

    Reuses the dashboard's filename regexes + the date sanity window. Logger
    files from ``raw_logger_v1`` and ``raw_logger_v2`` are merged under one date.
    """
    out: dict[str, dict[str, list[Path]]] = defaultdict(
        lambda: {"telematics": [], "logger": []}
    )
    tdir = reg_dir / RAW_TELEMATICS_DIR
    if tdir.is_dir():
        for f in sorted(tdir.glob("raw_*.csv")):
            m = _TELEMATICS_FNAME_RE.match(f.name)
            if not m:
                continue
            try:
                d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            except ValueError:
                continue
            if _raw_date_sane(d):
                out[d.isoformat()]["telematics"].append(f)
    for sub in RAW_LOGGER_DIRS:
        ldir = reg_dir / sub
        if not ldir.is_dir():
            continue
        for f in sorted(ldir.glob("logger_*.csv")):
            m = _LOGGER_FNAME_RE.match(f.name)
            if not m:
                continue
            try:
                d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            except ValueError:
                continue
            if _raw_date_sane(d):
                out[d.isoformat()]["logger"].append(f)
    return dict(out)


def read_telematics_day(paths: list[Path]) -> pd.DataFrame | None:
    """Read one day's telematics CSV(s) → UTC-indexed numeric-string DataFrame.

    Mirrors :mod:`validation_generator` (``dtype=str``, ``eventDatetime`` parsed
    as UTC). Columns stay as strings; callers ``to_numeric`` the ones they need.
    """
    frames: list[pd.DataFrame] = []
    for p in paths:
        try:
            df = pd.read_csv(p, dtype=str)
        except Exception as exc:  # noqa: BLE001
            LOG.debug("  telematics read failed %s: %s", p.name, exc)
            continue
        if df.empty or "eventDatetime" not in df.columns:
            continue
        frames.append(df)
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    ts = pd.to_datetime(df["eventDatetime"], errors="coerce", utc=True)
    keep = ts.notna()
    df = df.loc[keep].copy()
    df.index = ts[keep]
    df = df[~df.index.duplicated(keep="first")].sort_index()
    return df if not df.empty else None


def read_logger_day(paths: list[Path], cfg: dict) -> pd.DataFrame | None:
    """Read one day's logger CSV legs → a single UTC-indexed DataFrame.

    Reuses :func:`diesel_pipeline._logger_df_from_csv`'s read pattern (first
    column = timestamp index). Legs are concatenated (outer-join columns, so v1
    and v2 schemas coexist) and the index is de-duplicated + sorted, giving the
    shared 1 Hz time grid every logger concept rides.
    """
    frames: list[pd.DataFrame] = []
    for p in paths:
        try:
            df = pd.read_csv(p, index_col=0)
        except Exception as exc:  # noqa: BLE001
            LOG.debug("  logger read failed %s: %s", p.name, exc)
            continue
        if df.empty:
            continue
        idx = pd.to_datetime(df.index, errors="coerce", utc=True)
        df = df.loc[~idx.isna()]
        df.index = idx[~idx.isna()]
        if df.empty:
            continue
        frames.append(df)
    if not frames:
        return None
    df = pd.concat(frames)
    df = df[~df.index.duplicated(keep="first")].sort_index()
    return df if not df.empty else None


def read_charger_windows(reg_dir: Path) -> dict[str, list[dict]]:
    """Parse ``raw_charger/charger_transactions.csv`` → per-day charge windows.

    Returns ``{date_iso: [{"s": int, "e": int, "kwh": float}]}`` with ``s`` / ``e``
    seconds from that date's midnight (``start_time`` is ISO with a tz offset).
    """
    out: dict[str, list[dict]] = defaultdict(list)
    csv_path = reg_dir / RAW_CHARGER_DIR / RAW_CHARGER_CSV
    if not csv_path.is_file():
        return {}
    try:
        with csv_path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                s_dt = _parse_charger_ts(row.get("start_time"))
                if s_dt is None:
                    continue
                e_dt = _parse_charger_ts(row.get("end_time")) or s_dt
                d = s_dt.date()
                if not _raw_date_sane(d):
                    continue
                midnight = datetime(d.year, d.month, d.day, tzinfo=s_dt.tzinfo)
                s = int((s_dt - midnight).total_seconds())
                e = int((e_dt - midnight).total_seconds())
                s = max(0, min(s, 86400))
                e = max(s, min(e, 86400))
                kwh = _safe_float(row.get("energy_delivered_kwh"))
                out[d.isoformat()].append({"s": s, "e": e, "kwh": kwh})
    except OSError as exc:  # noqa: BLE001
        LOG.error("FAIL reading charger CSV %s: %s", csv_path, exc)
    return dict(out)


def _parse_charger_ts(value) -> datetime | None:
    if not value:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        try:
            return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


def _safe_float(value) -> float | None:
    try:
        f = float(value)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


# ── Downsample + base64 typed-array packing ──────────────────────────────────
def downsample_minmax(t, v, max_pts: int = LO_MAX_PTS):
    """Min/max-bucket downsample preserving spikes (and ``NaN`` gaps).

    ``t`` is int seconds, ``v`` float. If ``len <= max_pts`` the inputs are
    returned unchanged. Otherwise the series is split into ``max_pts // 2``
    contiguous buckets; each bucket emits its min and its max sample (in time
    order) so peaks survive. An all-``NaN`` bucket emits a single ``NaN`` at its
    start so the gap is preserved.
    """
    t = np.asarray(t)
    v = np.asarray(v, dtype=float)
    n = len(t)
    if n <= max_pts:
        return t, v
    n_buckets = max(1, max_pts // 2)
    edges = np.linspace(0, n, n_buckets + 1).astype(int)
    out_t: list = []
    out_v: list = []
    for i in range(n_buckets):
        a, b = int(edges[i]), int(edges[i + 1])
        if b <= a:
            continue
        seg_t = t[a:b]
        seg_v = v[a:b]
        finite = np.isfinite(seg_v)
        if not finite.any():
            out_t.append(seg_t[0])
            out_v.append(np.nan)
            continue
        fv = seg_v[finite]
        ft = seg_t[finite]
        i_min = int(fv.argmin())
        i_max = int(fv.argmax())
        pair = sorted(
            ((ft[i_min], fv[i_min]), (ft[i_max], fv[i_max])), key=lambda p: p[0]
        )
        for tt, vv in pair:
            out_t.append(tt)
            out_v.append(vv)
    return np.asarray(out_t), np.asarray(out_v, dtype=float)


def _u32_bytes(arr) -> bytes:
    return np.asarray(arr, dtype="<u4").tobytes()


def _f32_bytes(arr) -> bytes:
    return np.asarray(arr, dtype="<f4").tobytes()


def pack_u32(arr) -> str:
    """Pack ints as little-endian ``Uint32`` → base64 (time = seconds)."""
    return base64.b64encode(_u32_bytes(arr)).decode("ascii")


def pack_f32(arr) -> str:
    """Pack floats as little-endian ``Float32`` → base64 (``NaN`` preserved)."""
    return base64.b64encode(_f32_bytes(arr)).decode("ascii")


def _gz_b64(raw: bytes) -> str:
    """gzip + base64 a raw byte buffer (lazily inflated in the browser).

    Generation is an offline batch step, so we compress at the maximum level (9)
    to keep the embedded pages as small as possible.
    """
    return base64.b64encode(gzip.compress(raw, compresslevel=9)).decode("ascii")


def _shuffle_bytes(raw: bytes, itemsize: int = 4) -> bytes:
    """Transpose a byte buffer into ``itemsize`` byte-planes (HDF5 "shuffle").

    Reorders ``[w0b0 w0b1 .. w1b0 ..]`` into ``[all b0][all b1]…`` so that the
    repetitive high bytes of each 4-byte word (sign / exponent of slowly-varying
    1 Hz floats, high bytes of monotone seconds) sit together and gzip far
    better — a *lossless* pre-filter (≈ −33 % on the 1 Hz logger arrays). The
    browser reverses it with ``unshuffle`` after inflating. ``raw`` length must
    be a multiple of ``itemsize``.
    """
    a = np.frombuffer(raw, dtype=np.uint8).reshape(-1, itemsize)
    return np.ascontiguousarray(a.T).tobytes()


def _gz_shuf_b64(raw: bytes, itemsize: int = 4) -> str:
    """Byte-shuffle (``itemsize``), then gzip + base64 — the wire format for all
    embedded series. Inverted in the browser by ``gunzipB64`` + ``unshuffle``."""
    return _gz_b64(_shuffle_bytes(raw, itemsize))


def _pack_lo_gz(t, v) -> dict:
    """Pack a downsampled lo series as one byte-shuffled gzip+base64 blob.

    Logical layout (pre-shuffle): ``n`` little-endian ``Uint32`` time samples
    (seconds from midnight) immediately followed by ``n`` little-endian
    ``Float32`` values (``NaN`` = gap) — all 4-byte words, so the whole buffer is
    byte-shuffled at ``itemsize=4`` before gzip. The browser inflates, unshuffles,
    then reads the time block as ``Uint32`` and the value block (4-byte aligned at
    offset ``n * 4``) as ``Float32``. Returns ``{"d": <gz+b64>, "n": n}``.
    """
    tb = np.asarray(t, dtype="<u4").tobytes()
    vb = np.asarray(v, dtype="<f4").tobytes()
    return {"d": _gz_shuf_b64(tb + vb, 4), "n": int(len(t))}


def _sec_from_midnight(index: pd.DatetimeIndex, day: date) -> np.ndarray:
    """UTC-indexed timestamps → int seconds from that date's midnight (>= 0).

    Resolution-agnostic: pandas 2.x parses these sub-second-free timestamps to a
    ``datetime64[us]`` (microsecond) index, so the old ``index.asi8`` / ``.value``
    arithmetic — which assumed nanoseconds — produced a huge negative number that
    clipped to all-zeros, collapsing every chart onto x=0. Subtracting two
    tz-aware datetimes yields a ``TimedeltaIndex`` that divides by
    ``np.timedelta64(1, "s")`` to give exact seconds regardless of the underlying
    unit. Midnight maps to 0; the last sample of a day stays < 86400.
    """
    midnight = pd.Timestamp(year=day.year, month=day.month, day=day.day, tz="UTC")
    delta = index.tz_convert("UTC") - midnight  # TimedeltaIndex, unit-safe
    sec = (delta / np.timedelta64(1, "s")).to_numpy().astype("int64")
    return np.clip(sec, 0, None)


# ── Payload assembly ──────────────────────────────────────────────────────────
def _encode_telematics(series: pd.Series, day: date) -> dict | None:
    """Encode a telematics column from its non-NaN samples only (gzipped lo).

    Telematics events are heterogeneous: each event row carries only some
    channels, so a given column is NaN on every row that did not report it.
    Keeping those NaNs would shred the rendered line into disconnected fragments.
    A value of ``0`` is REAL data and must be kept (and later connected); only a
    genuinely-absent reading should create a gap. So we ``dropna`` here and take
    each remaining sample on its own timestamp — the series becomes the channel's
    actual samples on its actual times, with no interior NaN for the (single)
    telematics source. Downsampling then operates on these real samples.
    """
    vals = pd.to_numeric(series, errors="coerce").dropna()
    if vals.empty:
        return None
    t = _sec_from_midnight(vals.index, day)
    t_lo, v_lo = downsample_minmax(t, vals.values)
    return {"lo": _pack_lo_gz(t_lo, v_lo)}


def _encode_logger(series: pd.Series, t_hi: np.ndarray, day: date) -> dict | None:
    """Encode a logger column: gzipped lo + (gzipped) full-res hi on shared grid.

    Same heterogeneity fix as :func:`_encode_telematics` for the ``lo`` tier: a
    channel is NaN wherever it had no reading, and a ``0`` is real data. The lo
    tier is therefore built from this channel's non-NaN samples only (on their own
    timestamps), so the downsampled line connects the real samples instead of
    being shredded by interior NaNs. The ``hi`` tier must stay positionally
    aligned with the shared per-day logger time grid (``t_hi``), so it keeps the
    full-length value block (interior NaNs included → null on the client, where
    ``spanGaps`` reconnects the real points).
    """
    num = pd.to_numeric(series, errors="coerce")
    vals = num.values
    if not np.isfinite(vals).any():
        return None
    # lo: downsample the channel's real (non-NaN) samples on their own timestamps.
    real = num.dropna()
    t_real = _sec_from_midnight(real.index, day)
    t_lo, v_lo = downsample_minmax(t_real, real.values)
    entry = {"lo": _pack_lo_gz(t_lo, v_lo)}
    # hi: full-res values on the shared grid; carry only when genuinely finer than
    # the lo decimation (i.e. the real samples were actually downsampled).
    if len(real) > len(t_lo):
        entry["vHi"] = _gz_shuf_b64(_f32_bytes(vals), 4)
        entry["nHi"] = int(len(vals))
    return entry


def _merge_catalog(catalog: dict, concept: dict, sources_present: set[str]) -> None:
    """Accumulate a concept (union of sources seen) into the page catalogue."""
    entry = catalog.get(concept["id"])
    if entry is None:
        catalog[concept["id"]] = {
            "id": concept["id"],
            "name": concept["name"],
            "unit": concept["unit"],
            "group": concept["group"],
            "default": concept["default"],
            "y": concept.get("y"),
            "sources": set(sources_present),
        }
    else:
        entry["sources"] |= sources_present


def _vehicle_fuel(cfg: dict) -> str:
    """Human label for the vehicle's drivetrain (``"Electric"`` / ``"Diesel"``)."""
    pipeline = str(cfg.get("pipeline", "")).lower()
    is_diesel = (
        str(cfg.get("fuel_type", "")).upper() == "DIESEL" or "diesel" in pipeline
    )
    return "Diesel" if is_diesel else "Electric"


def _annotate_segment_mean_mass(
    segments: list[dict],
    tdf: pd.DataFrame | None,
    ldf: pd.DataFrame | None,
    mass_concept: dict | None,
    cfg: dict,
    day: date,
    mass_agg: str = "mean",
) -> None:
    """Attach each trip/charge segment's robust mean mass (tonnes) in place.

    Mirrors :func:`segment_algorithms.plot_leg_validation`'s Panel-4 *Seg. Mean
    Mass* so the dashboard's dashed mean-mass line matches the validation figure
    — and the Excel report's mass column — for the same vehicle/day. The per-event
    central value uses the report's resolved ``mass_agg`` method
    (:func:`segment_algorithms._agg_mass`, passed in by the caller) rather than a
    fixed estimator, so the dashed line reflects the same mass the report does:

    - **Telematics mass** (preferred — the figure's primary path) is clustered
      once per day with :func:`cluster_mass_data` (cluster means from moving-speed
      readings, the tractor-only cluster dropped to ``NaN``); the per-event value
      is :func:`_agg_mass` (the report's ``mass_agg``) over the in-window
      ``mass_cluster.notna()`` & ``> 0`` LOADED readings — the figure's exact
      selection. Day-wide (rather than per-leg) clustering is used because the
      dashboard only has the report's per-row segments, not the figure's FPS-leg
      grouping; a whole day gives the stable read count a single short segment
      lacks. Unlike the Excel column, the dashboard **displays bare-tractor /
      bobtail events too**, marked distinctly (user request "10 t 也要标出来而不是
      忽略"): the readings ``cluster_mass_data`` drops as tractor-only are recovered
      via its opt-in ``keep_tractor_only_label`` flag and aggregated separately, so
      an event with no loaded reading in-window (e.g. a ~10–11 t empty run) still
      gets a mean line — flagged ``seg['massTractorOnly'] = True`` for the muted
      client-side style. The old per-event guard (a loaded-window robust mean below
      ``TRACTOR_ONLY_MAX_KG``, from empty-running reads absorbed into a loaded
      cluster) is likewise no longer dropped but shown and flagged tractor-only.
    - **Logger mass** is the fallback (the inspect.html "Seg. Mean Mass (Logger)"
      dotted line): :func:`_agg_mass` (the report's ``mass_agg``) over the in-window
      ``> 0`` logger readings (the figure's logger path has no clustering / tractor
      exclusion — mirror it).

    ``mass_agg`` is the report's resolved aggregation method
    (``"mean"`` / ``"median"`` / ``"iqr_median"``); a window with fewer than two
    samples yields ``NaN`` (no dashed line for that event).

    Values are stored in the mass chart's display units (tonnes) as
    ``seg['massMeanT']`` with ``seg['massMeanSrc']`` (``"telematics"``/``"logger"``)
    and, for report-excluded bare-tractor events, ``seg['massTractorOnly'] = True``.
    Segments with no usable reading are left untouched (no dashed line client-side).
    """
    if not segments or mass_concept is None:
        return
    res = mass_concept.get("sources_resolved", {})

    # ── Telematics source (preferred): cluster the day once, then select per event.
    #   ``tele_*`` = LOADED readings (mass_cluster.notna()) → the normal dashed line
    #   matching the Excel column / figure. ``tract_*`` = the tractor-only readings
    #   the report drops (recovered via keep_tractor_only_label) → still DISPLAYED,
    #   marked, for bare-tractor / bobtail events.
    tele_sec = tele_kg = None
    tract_sec = tract_kg = None
    tele = res.get(TELEMATICS)
    if tele is not None and tdf is not None and tele["col"] in tdf.columns:
        mass_col = tele["col"]
        # cluster_mass_data emits INFO logs (tractor-only / fallback); silence for
        # this one per-day call so the dashboard build stays quiet.
        seg_logger = logging.getLogger(
            "jolt_toolkit.report_generator.segment_algorithms"
        )
        prev_level = seg_logger.level
        seg_logger.setLevel(logging.WARNING)
        try:
            clustered = cluster_mass_data(
                tdf,
                mass_col=mass_col,
                min_cluster_gap_kg=float(
                    cfg.get("min_cluster_gap_kg", MIN_CLUSTER_GAP_KG)
                ),
                speed_col=cfg.get("speed_col", "wheel_based_speed"),
                speed_threshold_kmh=MOVING_SPEED_THRESHOLD_KMH,
                keep_tractor_only_label=True,  # recover the dropped tractor reads
            )
        finally:
            seg_logger.setLevel(prev_level)
        mass_kg = pd.to_numeric(clustered[mass_col], errors="coerce")
        valid = mass_kg.notna() & (mass_kg > 0)
        loaded = (valid & clustered["mass_cluster"].notna()).to_numpy()
        if loaded.any():
            tele_sec = _sec_from_midnight(clustered.index[loaded], day)
            tele_kg = mass_kg.to_numpy(dtype=float)[loaded]
        if "mass_tractor_only" in clustered.columns:
            tract = (valid & clustered["mass_tractor_only"].astype(bool)).to_numpy()
            if tract.any():
                tract_sec = _sec_from_midnight(clustered.index[tract], day)
                tract_kg = mass_kg.to_numpy(dtype=float)[tract]

    # ── Logger source (fallback): in-window > 0 robust mean (no tractor exclusion).
    log_sec = log_kg = None
    log = res.get(LOGGER)
    if log is not None and ldf is not None and log["col"] in ldf.columns:
        lm = pd.to_numeric(ldf[log["col"]], errors="coerce")  # raw kg
        keep = (lm.notna() & (lm > 0)).to_numpy()
        if keep.any():
            log_sec = _sec_from_midnight(ldf.index[keep], day)
            log_kg = lm.to_numpy(dtype=float)[keep]

    def _win_agg(sec_arr, kg_arr, lo, hi):
        """Report-``mass_agg`` robust mean (kg) of in-[lo,hi] samples; NaN if none.

        ``sec_arr`` is the position-aligned seconds axis (used only by the
        ``mad_tw_mean`` time-weighted method) — mirrors the Excel column / figure.
        """
        w = (sec_arr >= lo) & (sec_arr <= hi)
        if not w.any():
            return float("nan")
        return _agg_mass(
            pd.Series(kg_arr[w]), mass_agg, timestamps=pd.Series(sec_arr[w])
        )[0]

    for sg in segments:
        s, e = sg["s"], sg["e"]
        mean_kg = None
        src = None
        tractor_only = False
        # 1) Loaded telematics reading in-window. >= threshold → normal line; below
        #    it (the old "guard" case — empty-running reads absorbed into a loaded
        #    cluster) → keep the value but MARK it tractor-only instead of dropping.
        if tele_sec is not None:
            val = _win_agg(tele_sec, tele_kg, s, e)
            if np.isfinite(val):
                mean_kg, src = val, TELEMATICS
                tractor_only = val < TRACTOR_ONLY_MAX_KG
        # 2) No loaded reading in-window → recover the tractor-only cluster so a
        #    bare-tractor / bobtail event still shows its ~10–11 t line, marked.
        if mean_kg is None and tract_sec is not None:
            val = _win_agg(tract_sec, tract_kg, s, e)
            if np.isfinite(val):
                mean_kg, src, tractor_only = val, TELEMATICS, True
        # 3) Logger fallback (no clustering / tractor split — mirror the figure).
        if mean_kg is None and log_sec is not None:
            val = _win_agg(log_sec, log_kg, s, e)
            if np.isfinite(val):
                mean_kg, src = val, LOGGER
        if mean_kg is not None:
            sg["massMeanT"] = round(float(mean_kg) / 1000.0, 3)  # kg → tonnes
            sg["massMeanSrc"] = src
            if tractor_only:
                sg["massTractorOnly"] = True


def build_vehicle_payload(
    reg: str,
    reg_dir: Path,
    cfg: dict,
    legs: list[dict],
    *,
    version: str,
    operator_meta: dict | None = None,
) -> dict:
    """Build the embedded ``PAYLOAD`` for one vehicle's detail page.

    Streams day-by-day: each day's DataFrames are read, encoded to compact gzipped
    base64 typed-array strings, then released before the next day (only the
    compact encoded payload is retained). ``operator_meta`` (this vehicle's
    operator periods + fleet colour / name maps, from
    :func:`data_dashboard.build_operator_assignment`) lets the page resolve and
    colour the operator per day. Returns ``{"reg", "version", "fuel", "make",
    "model", "operator", "concepts" (union catalogue), "sourceColors", "days"}``.
    """
    segments_by_date = build_day_segments(legs)
    charger_by_date = read_charger_windows(reg_dir)
    by_date = group_raw_files_by_date(reg_dir)
    # Resolve the report's mass-aggregation method once (vehicle > pipeline >
    # default), so the per-event dashed mean-mass line matches the report's mass.
    mass_agg = resolve_mass_agg(reg)

    catalog: dict[str, dict] = {}
    days: dict[str, dict] = {}

    for date_iso in sorted(by_date):
        files = by_date[date_iso]
        day = date.fromisoformat(date_iso)
        tdf = read_telematics_day(files["telematics"]) if files["telematics"] else None
        ldf = read_logger_day(files["logger"], cfg) if files["logger"] else None
        if tdf is None and ldf is None:
            continue

        telem_cols = set(tdf.columns) if tdf is not None else set()
        logger_cols = set(ldf.columns) if ldf is not None else set()
        resolved = resolve_vehicle_concepts(reg, cfg, telem_cols, logger_cols)

        day_obj: dict = {
            "concepts": {},
            "segments": segments_by_date.get(date_iso, []),
            "chargerWindows": charger_by_date.get(date_iso, []),
        }

        # Shared logger 1 Hz time grid (gzipped once; all logger concepts ride it).
        t_hi: np.ndarray | None = None
        if ldf is not None:
            t_hi = _sec_from_midnight(ldf.index, day)
            day_obj["loggerTimeHi"] = _gz_shuf_b64(_u32_bytes(t_hi), 4)
            day_obj["nHi"] = int(len(t_hi))

        for concept in resolved:
            cobj: dict = {}
            for source, res in concept["sources_resolved"].items():
                fn = _TRANSFORMS[res["transform"]]
                if (
                    source == TELEMATICS
                    and tdf is not None
                    and res["col"] in tdf.columns
                ):
                    series = fn(pd.to_numeric(tdf[res["col"]], errors="coerce"))
                    enc = _encode_telematics(series, day)
                    if enc is not None:
                        cobj[TELEMATICS] = enc
                elif source == LOGGER and ldf is not None and res["col"] in ldf.columns:
                    series = fn(pd.to_numeric(ldf[res["col"]], errors="coerce"))
                    enc = _encode_logger(series, t_hi, day)
                    if enc is not None:
                        cobj[LOGGER] = enc
            if cobj:
                day_obj["concepts"][concept["id"]] = cobj
                _merge_catalog(catalog, concept, set(cobj.keys()))

        # Per-event mean mass (tonnes) for the mass chart's dashed line — matches
        # the validation figure's Panel-4 "Seg. Mean Mass" (see helper docstring).
        mass_concept = next((c for c in resolved if c["id"] == "mass"), None)
        _annotate_segment_mean_mass(
            day_obj["segments"], tdf, ldf, mass_concept, cfg, day, mass_agg
        )

        if day_obj["concepts"]:
            days[date_iso] = day_obj
        # tdf / ldf drop out of scope here → only encoded payload is retained.

    # Catalogue in registry order; sources as a sorted list for the JSON blob.
    order = {c["id"]: i for i, c in enumerate(CONCEPT_REGISTRY)}
    concepts = []
    for cid in sorted(catalog, key=lambda x: order.get(x, 1_000)):
        meta = catalog[cid]
        y_spec = meta.get("y")
        concepts.append(
            {
                "id": meta["id"],
                "name": meta["name"],
                "unit": meta["unit"],
                "group": meta["group"],
                "default": meta["default"],
                # Fixed [min,max] (bounded signal) or null (autoscale). The frontend
                # sets scale.range accordingly per chart.
                "y": list(y_spec) if y_spec is not None else None,
                "sources": [
                    s for s in (TELEMATICS, LOGGER, CHARGER) if s in meta["sources"]
                ],
            }
        )

    return {
        "reg": reg,
        "version": version,
        "fuel": _vehicle_fuel(cfg),
        "make": cfg.get("make") or "",
        "model": cfg.get("model") or "",
        "operator": operator_meta or None,
        "concepts": concepts,
        "sourceColors": SOURCE_COLOURS,
        "sourceLabels": SOURCE_LABELS,
        "groupOrder": GROUP_ORDER,
        "days": days,
    }


# ── uPlot asset loading / fetching ────────────────────────────────────────────
def _load_uplot_assets() -> tuple[str, str]:
    """Return ``(uplot_js, uplot_css)`` from the vendored offline assets.

    Raises a clear error (telling the user to run ``--fetch-uplot``) if either
    asset is missing, so a detail page is never rendered with a broken chart lib.
    """
    if not _UPLOT_JS.is_file() or not _UPLOT_CSS.is_file():
        raise FileNotFoundError(
            "Vendored uPlot assets missing under "
            f"{_UPLOT_DIR} — run `python -m "
            "jolt_toolkit.report_generator.data_dashboard --fetch-uplot` first."
        )
    return (
        _UPLOT_JS.read_text(encoding="utf-8"),
        _UPLOT_CSS.read_text(encoding="utf-8"),
    )


def fetch_uplot(dest: Path | None = None) -> Path:
    """Download the vendored uPlot JS + CSS from jsDelivr (one-off network step).

    Writes ``uPlot.iife.min.js`` and ``uPlot.min.css`` into ``dest`` (default: the
    package ``assets/uplot`` directory). Returns the destination directory.
    """
    dest = dest or _UPLOT_DIR
    dest.mkdir(parents=True, exist_ok=True)
    for fname in ("uPlot.iife.min.js", "uPlot.min.css"):
        url = f"{_UPLOT_BASE}/{fname}"
        LOG.info("Fetching %s", url)
        with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
            data = resp.read()
        (dest / fname).write_bytes(data)
        LOG.info("  wrote %s (%d bytes)", dest / fname, len(data))
    return dest


# ── HTML rendering ────────────────────────────────────────────────────────────
def render_detail_html(
    payload: dict, *, version: str, uplot_js: str, uplot_css: str
) -> str:
    """Render one vehicle's payload to a self-contained detail-page HTML string.

    uPlot JS + CSS are inlined verbatim (offline), and the compact ``PAYLOAD`` is
    embedded as JSON. No external / CDN references are emitted.
    """
    reg = payload["reg"]
    n_days = len(payload["days"])
    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    reg_disp = html.escape(reg)
    ver_disp = html.escape(version)
    generated = date.today().isoformat()
    fuel = payload.get("fuel") or "Electric"
    fuel_disp = html.escape(fuel)
    fuel_cls = "pill-dz" if fuel == "Diesel" else "pill-ev"
    model_bits = " ".join(b for b in (payload.get("make"), payload.get("model")) if b)
    model_disp = html.escape(model_bits)

    head = (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>JOLT detail — {reg_disp} ({ver_disp})</title>\n"
        "<style>\n" + uplot_css + "\n" + _DETAIL_CSS + "</style>\n"
        "</head>\n<body>\n"
    )
    model_html = f'<span class="tb-model">{model_disp}</span>' if model_disp else ""
    topbar = f"""<header class="topbar">
  <div class="tb-left">
    <a class="back" href="data_dashboard.html">&larr; Dashboard</a>
    <span class="tb-reg">{reg_disp}</span>
    <span class="veh-badge {fuel_cls}">{fuel_disp}</span>
    {model_html}
  </div>
  <div class="tb-mid">
    <span class="chip op-chip" id="opChip" hidden></span>
    <span class="chip day-chip" id="dayLabel">&mdash;</span>
    <span class="chip mode-chip" id="modeChip">&mdash;</span>
  </div>
  <div class="tb-right">
    <span class="tb-ctl day-ctl">Day
      <button type="button" class="day-nav" id="dayPrev" title="Previous day" aria-label="Previous day">&#9664;</button>
      <select id="daySel"></select>
      <button type="button" class="day-nav" id="dayNext" title="Next day" aria-label="Next day">&#9654;</button>
    </span>
    <label class="tb-ctl" title="Logger channels carry a downsampled Low tier (fast) and a full 1 Hz High tier (inflated on demand)">Logger detail
      <select id="resSel">
        <option value="lo">Low (fast)</option>
        <option value="hi">High (1 Hz)</option>
      </select>
    </label>
    <label class="tb-ctl" title="Shade trip / charge events behind every chart"><input type="checkbox" id="segChk"> Event bands</label>
    <label class="tb-ctl" title="Mark each trip / charge event's start &amp; end with a triangle, and show its metrics (dSOC / kWh / capacity / EP) on the SoC chart"><input type="checkbox" id="eventChk" checked> Event markers</label>
    <span class="tb-meta">v{ver_disp} &middot; {n_days} days &middot; built {generated}</span>
  </div>
</header>
<div class="detail">
  <aside class="chan-panel">
    <div class="chan-head">
      <span>Channels <span class="chan-count" id="chanCount"></span></span>
      <span class="chan-actions">
        <button type="button" id="selAll">All</button>
        <button type="button" id="selNone">None</button>
      </span>
    </div>
    <div class="chan-subhead" id="chanSub">Dimmed = no data on the selected day</div>
    <div class="chan-body" id="chanList"></div>
  </aside>
  <main class="chart-panel">
    <div class="band-legend" id="bandLegend"></div>
    <div class="chart-scroll" id="chartArea"></div>
  </main>
</div>
<script>
"""
    data_prelude = "const PAYLOAD = " + data_json + ";\n"
    js_lib = "\n// ── vendored uPlot (offline) ──\n" + uplot_js + "\n"
    tail = "\n</script>\n</body>\n</html>\n"
    return head + topbar + js_lib + data_prelude + _DETAIL_JS + tail


def write_detail_pages(
    db_root: Path,
    version: str,
    regs: list[str],
    *,
    out_dir: Path | None = None,
    legs_by_reg: dict[str, list[dict]] | None = None,
    cfg_by_reg: dict | None = None,
) -> dict[str, Path]:
    """Generate ``detail_<REG>.html`` for each requested vehicle.

    Pages are written into ``out_dir`` (default ``<db-root>/<version>/dashboard``,
    shared with ``data_dashboard.html`` so the inter-page links stay relative).
    ``legs_by_reg`` (already-read report legs, reused for segments) and
    ``cfg_by_reg`` (vehicles.json) may be supplied to avoid re-reading; otherwise
    they are loaded here. Returns ``{REG: detail_path}`` for the pages written.
    """
    from jolt_toolkit.report_generator.data_dashboard import (  # local: avoid cycle
        _collect_legs_by_reg,
        _load_plot_config,
        _load_vehicles_cfg,
        _operator_days_from_legs,
        build_operator_assignment,
    )

    # Raw data is scanned from <version>/<REG>/ (root), but the pages are written
    # into the shared <version>/dashboard/ folder alongside data_dashboard.html.
    root = db_root / version
    out_dir = out_dir or (root / "dashboard")
    out_dir.mkdir(parents=True, exist_ok=True)

    if cfg_by_reg is None:
        cfg_by_reg = _load_vehicles_cfg()
    if legs_by_reg is None:
        legs_by_reg = _collect_legs_by_reg(db_root, version)

    # Operator assignment (per-vehicle periods + fleet colour / name maps), shared
    # with the dashboard so the detail header resolves & colours operators per day.
    # Data-driven from each vehicle's reports' Operator column (plot_config is a
    # fallback only), so detail pages track operator handovers like the dashboard.
    op_days_by_reg = {
        reg: _operator_days_from_legs(legs) for reg, legs in legs_by_reg.items()
    }
    operator = build_operator_assignment(_load_plot_config(), op_days_by_reg)

    uplot_js, uplot_css = _load_uplot_assets()

    written: dict[str, Path] = {}
    for reg in regs:
        reg_dir = root / reg
        if not reg_dir.is_dir():
            LOG.warning("detail: %s has no report dir under %s — skipped", reg, root)
            continue
        legs = legs_by_reg.get(reg, [])
        cfg = cfg_by_reg.get(reg, {})
        op_veh = operator["vehicles"].get(reg)
        operator_meta = None
        if op_veh:
            operator_meta = {
                "trialType": op_veh.get("trial_type", "—"),
                "periods": op_veh.get("periods", []),
                "colors": operator["operatorColors"],
                "names": operator["operatorNames"],
                "neutral": operator["neutralColour"],
            }
        payload = build_vehicle_payload(
            reg, reg_dir, cfg, legs, version=version, operator_meta=operator_meta
        )
        if not payload["days"]:
            LOG.warning("detail: %s has no raw day data — skipped", reg)
            continue
        doc = render_detail_html(
            payload, version=version, uplot_js=uplot_js, uplot_css=uplot_css
        )
        out_path = out_dir / f"detail_{reg}.html"
        out_path.write_text(doc, encoding="utf-8")
        size_mb = out_path.stat().st_size / (1024 * 1024)
        LOG.info(
            "detail: %-9s -> %s (%.1f MB, %d days)",
            reg,
            out_path,
            size_mb,
            len(payload["days"]),
        )
        written[reg] = out_path
    return written


# ── Detail-page CSS ───────────────────────────────────────────────────────────
_DETAIL_CSS = """
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body {
  font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  color: #1f2937; background: #f3f4f6; font-size: 14px;
  display: flex; flex-direction: column; height: 100vh;
}
/* ── Top bar ── */
header.topbar {
  padding: 9px 18px; background: #111827; color: #f9fafb;
  display: flex; align-items: center; justify-content: space-between;
  gap: 14px 20px; flex-wrap: wrap; flex: 0 0 auto;
}
.topbar .tb-left { display: flex; align-items: center; gap: 12px; min-width: 0; }
.topbar .tb-reg { font-size: 18px; font-weight: 700; letter-spacing: .04em; }
.topbar .tb-model { font-size: 12.5px; color: #cbd5e1; }
.topbar .back { color: #93c5fd; text-decoration: none; font-size: 13px; white-space: nowrap; }
.topbar .back:hover { text-decoration: underline; }
.veh-badge {
  font-size: 10.5px; font-weight: 700; padding: 2px 8px; border-radius: 999px;
  letter-spacing: .02em; text-transform: uppercase;
}
.pill-ev { background: #064e3b; color: #6ee7b7; }
.pill-dz { background: #422006; color: #fdba74; }
.topbar .tb-mid { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.chip {
  font-size: 12px; padding: 3px 10px; border-radius: 999px;
  background: #1f2937; color: #e5e7eb; border: 1px solid #374151;
  font-variant-numeric: tabular-nums; white-space: nowrap;
}
.op-chip { font-weight: 600; }
.op-chip .op-dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block;
  margin-right: 6px; vertical-align: -1px; border: 1px solid rgba(255,255,255,.25); }
.mode-chip { color: #cbd5e1; }
.topbar .tb-right { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.tb-ctl { font-size: 12.5px; color: #cbd5e1; display: inline-flex; align-items: center; gap: 6px; }
.tb-ctl select {
  font: inherit; font-size: 12.5px; padding: 3px 6px; border-radius: 6px;
  border: 1px solid #374151; background: #1f2937; color: #f9fafb;
}
/* Prev/next day steppers — reuse the daySel select palette for consistency. */
.tb-ctl .day-nav {
  font: inherit; font-size: 12.5px; line-height: 1; cursor: pointer;
  padding: 3px 7px; border-radius: 6px;
  border: 1px solid #374151; background: #1f2937; color: #f9fafb;
}
.tb-ctl .day-nav:hover:not(:disabled) { background: #374151; }
.tb-ctl .day-nav:disabled { opacity: .4; cursor: default; }
.tb-meta { font-size: 11.5px; color: #9ca3af; }
.detail { flex: 1; display: flex; min-height: 0; }
/* ── Left channel panel ── */
.chan-panel {
  width: 250px; flex: 0 0 auto; background: #fff; border-right: 1px solid #e5e7eb;
  display: flex; flex-direction: column; min-height: 0;
}
.chan-head {
  padding: 11px 14px 7px; font-size: 12.5px; font-weight: 700; color: #374151;
  text-transform: uppercase; letter-spacing: .05em;
  display: flex; align-items: center; justify-content: space-between;
  background: #fafbfc; flex: 0 0 auto;
}
.chan-count { color: #9ca3af; font-weight: 600; }
.chan-actions { display: inline-flex; gap: 4px; }
.chan-actions button {
  font: inherit; font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .03em; padding: 2px 8px; border-radius: 6px; cursor: pointer;
  border: 1px solid #d1d5db; background: #fff; color: #374151;
}
.chan-actions button:hover { background: #f3f4f6; }
.chan-subhead {
  padding: 0 14px 8px; font-size: 10.5px; color: #9ca3af;
  border-bottom: 1px solid #eef2f7; background: #fafbfc; flex: 0 0 auto;
}
.chan-body { padding: 8px 10px; overflow: auto; flex: 1; min-height: 0; }
.chan-group { font-size: 10.5px; font-weight: 700; color: #9ca3af;
  text-transform: uppercase; letter-spacing: .05em; margin: 12px 4px 4px; }
.chan-group:first-child { margin-top: 2px; }
.chan-item {
  display: flex; align-items: center; gap: 8px; padding: 5px 6px;
  border-radius: 6px; cursor: pointer; font-size: 13px;
}
.chan-item:hover { background: #f3f4f6; }
.chan-item input { cursor: pointer; }
.chan-name { font-weight: 600; }
/* Concept with no data on the selected day: dimmed but still selectable. */
.chan-item.no-data { opacity: .42; }
.chan-item.no-data .chan-name { font-weight: 500; font-style: italic; }
.chan-src { display: inline-flex; gap: 3px; margin-left: auto; }
.src-chip {
  width: 9px; height: 9px; border-radius: 2px; display: inline-block;
  border: 1px solid rgba(0,0,0,.1);
}
/* ── Right chart panel ── */
.chart-panel { flex: 1; min-width: 0; display: flex; flex-direction: column; min-height: 0; }
.band-legend {
  flex: 0 0 auto; display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  padding: 7px 16px; background: #fff; border-bottom: 1px solid #e5e7eb;
  font-size: 11.5px; color: #4b5563;
}
.band-legend .bl-item { display: inline-flex; align-items: center; gap: 6px; }
.band-legend .bl-swatch { width: 18px; height: 12px; border-radius: 3px; display: inline-block; }
.band-legend .bl-line { width: 18px; height: 0; border-top-width: 3px; border-top-style: solid; display: inline-block; }
.band-legend .bl-tri { width: 0; height: 0; display: inline-block;
  border-left: 5px solid transparent; border-right: 5px solid transparent;
  border-bottom: 8px solid #6b7280; }
.band-legend .bl-note { color: #9ca3af; margin-left: auto; }
.band-legend.off { opacity: .5; }
/* ── Per-event metric labels (inspect.html-style overlay, SoC chart) ── */
/* Ghosted by default; solid + shadowed on hover. Absolutely positioned inside
   uPlot's .u-over and repositioned on zoom / pan / resize (see placeBoxes). */
.ev-box {
  position: absolute; z-index: 6; pointer-events: auto; cursor: default;
  font-size: 10px; line-height: 1.22; font-weight: 600;
  font-variant-numeric: tabular-nums; white-space: nowrap;
  padding: 2px 5px; border-radius: 5px; border: 1px solid;
  background: rgba(255, 255, 255, .9); opacity: .22;
  transition: opacity .12s ease, box-shadow .12s ease;
}
.ev-box:hover {
  opacity: 1; background: #fff; z-index: 30;
  box-shadow: 0 3px 10px rgba(15, 23, 42, .22);
}
.ev-box.trip { border-color: #dc2626; color: #991b1b; }
.ev-box.charge { border-color: #d97706; color: #92400e; }
.chart-scroll { flex: 1; min-width: 0; overflow: auto; padding: 12px 14px; }
.chart-card {
  background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
  padding: 8px 10px 4px; margin-bottom: 12px;
}
.chart-card.empty { padding: 0; }
.chart-title {
  font-size: 13px; font-weight: 700; color: #1f2937; margin: 0 0 2px 4px;
  display: flex; align-items: center; gap: 10px;
}
.chart-title .ct-axis { color: #9ca3af; font-weight: 600; font-size: 11px; }
.chart-title .ct-src { display: inline-flex; gap: 10px; margin-left: auto;
  font-size: 11px; font-weight: 600; }
.chart-title .ct-src span { display: inline-flex; align-items: center; gap: 4px; }
.chart-title .ct-src i { width: 16px; height: 3px; border-radius: 2px; display: inline-block; }
.chart-empty {
  display: flex; align-items: center; gap: 8px; padding: 16px 14px;
  color: #9ca3af; font-size: 12.5px;
}
.chart-empty .ce-name { font-weight: 700; color: #6b7280; }
.empty-note { color: #9ca3af; font-size: 14px; padding: 40px; text-align: center; }
.uplot { width: 100%; }
/* Legend ("time:" label + per-series name/value row) bumped to 18px (~1.6x the
   old 11.5px) so it reads against the chart whitespace; few series per chart, so
   the legend table still fits the chart width. */
.u-legend { font-size: 18px; }
.u-legend .u-marker { width: 10px; height: 10px; }
"""

# ── Detail-page client logic (literal JS; no f-string interpolation) ──────────
_DETAIL_JS = r"""
const SRC_ORDER = ["telematics", "logger", "charger"];
const COL = PAYLOAD.sourceColors;
const SRC_LABEL = PAYLOAD.sourceLabels;
// Segment-band fills. Charge is amber (not green) so it never collides with the
// green LOGGER line; trip is red. Neither colour is used by a chart series
// (telematics=blue, logger=green) so bands stay visually distinct from data.
const BAND = { trip: "#dc2626", charge: "#d97706" };
const BAND_LABEL = { trip: "Trip (driving)", charge: "Charging" };
// Full-day x-axis (00:00 .. 24:00 in seconds-from-midnight). FIXED on every chart.
const DAY_SEC = 86400;
// Allowed x-axis tick increments in seconds (1m,2m,5m,10m,15m,30m,1h,2h,3h,6h,
// 12h,24h). uPlot picks the smallest rung whose pixel spacing >= axis `space`, so
// zoomed ticks always land on clean clock values instead of odd auto steps.
const X_INCRS = [60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400];
// Fixed 1-hour grid for the default full-day view: 00:00,01:00,…,24:00 (25 ticks).
const X_FULLDAY_SPLITS = [0, 3600, 7200, 10800, 14400, 18000, 21600, 25200,
                          28800, 32400, 36000, 39600, 43200, 46800, 50400, 54000,
                          57600, 61200, 64800, 68400, 72000, 75600, 79200, 82800,
                          86400];
// X-axis tick-label font: 18px = 1.5x uPlot's 12px default, which read too small
// against the chart whitespace. uPlot auto-scales this CSS px value by the device
// pixel ratio (pxRatioFont), so it is given at logical size. X_AXIS_SIZE bumps the
// reserved space under each chart so the larger labels are not clipped (uPlot's
// auto-size for the 12px default is ~33px; 46px clears the 18px text + ticks/gap).
const X_AXIS_FONT = "18px -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";
const X_AXIS_SIZE = 46;

// ── Page state ───────────────────────────────────────────────────────────────
let CUR_DATE = null;
let RES = "lo";              // "lo" | "hi" (logger resolution)
let SHOW_SEG = true;        // segment bands visible?
let SHOW_EVENTS = true;     // event markers (triangles + info boxes) visible?
let MODE = "events";        // "events" | "raw" (from the dashboard link)
const SELECTED = new Set(); // checked concept ids
let CHARTS = [];            // live uPlot instances (for sync + teardown)
const SYNC = uPlot.sync("detail");
let _syncing = false;       // re-entrancy guard for mirrored x-zoom
let _renderToken = 0;       // guards against overlapping async renders

// Decode caches (lazy): lo per concept/source, hi shared time grid + values.
const _loCache = {};        // date|cid|src -> {t: Float64Array, v: Array}
const _hiTimeCache = {};    // date -> Float64Array (seconds)
const _hiValCache = {};     // date|cid|src -> Float32Array

// ── base64 / gzip decoding ───────────────────────────────────────────────────
function b64ToBytes(b64) {
  const bin = atob(b64);
  const n = bin.length;
  const out = new Uint8Array(n);
  for (let i = 0; i < n; i++) out[i] = bin.charCodeAt(i);
  return out;
}
// Inflate a gzip+base64 string using the browser's built-in DecompressionStream
// (offline, no dependency). Returns a Promise<Uint8Array> over a fresh, 4-byte
// aligned ArrayBuffer. Series buffers are also byte-shuffled (see _shuffle_bytes)
// so callers pass the result through unshuffle() before taking typed views.
async function gunzipB64(b64) {
  const bytes = b64ToBytes(b64);
  const ds = new DecompressionStream("gzip");
  const stream = new Blob([bytes]).stream().pipeThrough(ds);
  const buf = await new Response(stream).arrayBuffer();
  return new Uint8Array(buf);
}
// Reverse the byte-plane shuffle: [all b0][all b1][all b2][all b3] -> the
// original interleaved itemsize-byte words. Returns a fresh (aligned) Uint8Array.
function unshuffle(u8, itemsize) {
  const total = u8.length;
  const nitems = (total / itemsize) | 0;
  const out = new Uint8Array(total);
  for (let p = 0; p < itemsize; p++) {
    const base = p * nitems;
    for (let i = 0; i < nitems; i++) out[i * itemsize + p] = u8[base + i];
  }
  return out;
}

// Build a JS number array with NaN -> null (uPlot draws null as a gap).
function toPlot(typed) {
  const n = typed.length;
  const out = new Array(n);
  for (let i = 0; i < n; i++) { const x = typed[i]; out[i] = isNaN(x) ? null : x; }
  return out;
}

// ── Query parsing ────────────────────────────────────────────────────────────
function parseQuery() {
  const q = new URLSearchParams(location.search);
  return { date: q.get("date"), mode: q.get("mode") };
}

// ── Time-axis formatting (seconds from midnight -> HH:MM[:SS]) ────────────────
function fmtClock(sec, withSec) {
  sec = Math.max(0, Math.round(sec));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const pad = n => String(n).padStart(2, "0");
  return withSec ? pad(h) + ":" + pad(m) + ":" + pad(s) : pad(h) + ":" + pad(m);
}

// X-axis tick placement. uPlot calls this with the increment (`foundIncr`) it
// chose from X_INCRS for the current zoom + axis space. At the default full-day
// view (span ~ the whole day, i.e. reset / initial) we ignore foundIncr and
// return the fixed 1-hour grid so the unzoomed axis reads exactly 00:00,01:00,
// …,24:00 regardless of chart width; once zoomed in we step on foundIncr so the
// finer ticks still land on clean clock values from the ladder above.
function xSplits(u, axisIdx, scaleMin, scaleMax, foundIncr) {
  if (scaleMax - scaleMin >= 86000) return X_FULLDAY_SPLITS.slice();
  const out = [];
  const start = Math.ceil(scaleMin / foundIncr) * foundIncr;
  for (let v = start; v <= scaleMax + 1e-6; v += foundIncr) out.push(v);
  return out;
}
// X-axis labels: HH:MM at the 1-hour / minute scales; only drop to HH:MM:SS on a
// sub-minute zoom (foundIncr < 60 s — below the X_INCRS floor, so a safety net).
function xValues(u, splits, axisIdx, foundSpace, foundIncr) {
  const withSec = foundIncr < 60;
  return splits.map(s => fmtClock(s, withSec));
}

// ── Decoders for a concept/source on the current day ─────────────────────────
// lo series: one gzip blob = n Uint32 seconds ++ n Float32 values. Inflated on
// first view of a day, then cached. Returns {t: Float64Array, v: Array(num|null)}.
async function loSeries(dateKey, day, cid, src) {
  const ck = dateKey + "|" + cid + "|" + src;
  if (_loCache[ck]) return _loCache[ck];
  const e = day.concepts[cid][src];
  const u8 = unshuffle(await gunzipB64(e.lo.d), 4);
  const n = e.lo.n;
  const tu = new Uint32Array(u8.buffer, 0, n);
  const vf = new Float32Array(u8.buffer, n * 4, n);
  const tf = new Float64Array(n);
  for (let i = 0; i < n; i++) tf[i] = tu[i];
  const out = { t: tf, v: toPlot(vf) };
  _loCache[ck] = out;
  return out;
}
// Logger hi series: shared per-day 1 Hz time grid + lazily-inflated values.
async function hiSeries(dateKey, day, cid, src) {
  const e = day.concepts[cid][src];
  if (!e.vHi) return await loSeries(dateKey, day, cid, src);  // no finer data
  if (!_hiTimeCache[dateKey]) {
    const u8 = unshuffle(await gunzipB64(day.loggerTimeHi), 4);
    const u = new Uint32Array(u8.buffer, 0, u8.byteLength >> 2);
    const tf = new Float64Array(u.length);
    for (let i = 0; i < u.length; i++) tf[i] = u[i];
    _hiTimeCache[dateKey] = tf;
  }
  const vkey = dateKey + "|" + cid + "|" + src;
  if (!_hiValCache[vkey]) {
    const u8 = unshuffle(await gunzipB64(e.vHi), 4);
    _hiValCache[vkey] = new Float32Array(u8.buffer, 0, u8.byteLength >> 2);
  }
  return { t: _hiTimeCache[dateKey], v: toPlot(_hiValCache[vkey]) };
}

// Resolve the {t,v} series for one source of a concept on the current day,
// honouring the lo/hi toggle (only logger has a hi tier).
async function seriesFor(dateKey, day, cid, src) {
  if (src === "logger" && RES === "hi") return await hiSeries(dateKey, day, cid, src);
  return await loSeries(dateKey, day, cid, src);
}

// Merge per-source {t,v} into uPlot data [xs, ys_src1, ys_src2, ...] on the
// union of sorted-unique x. Each source becomes one series (null where missing).
function mergeSeries(perSource) {
  const srcs = perSource.map(p => p.src);
  // Union of x values. Inject 0 and 86400 (with null y everywhere) so every
  // chart's data x-extent spans the FULL day — uPlot then autoscales / resets x
  // to exactly [0, 86400] (see the zero-pad x range in makeChart).
  const xset = new Set();
  xset.add(0); xset.add(DAY_SEC);
  perSource.forEach(p => { for (let i = 0; i < p.t.length; i++) xset.add(p.t[i]); });
  const xs = Float64Array.from(xset).sort();
  const xindex = new Map();
  for (let i = 0; i < xs.length; i++) xindex.set(xs[i], i);
  const data = [Array.from(xs)];
  perSource.forEach(p => {
    const col = new Array(xs.length).fill(null);
    for (let i = 0; i < p.t.length; i++) {
      const j = xindex.get(p.t[i]);
      if (j !== undefined) col[j] = p.v[i];
    }
    data.push(col);
  });
  return { data, srcs };
}

// ── Per-event metric lines (inspect.html style; omit NaN fields) ─────────────
// Mirrors the segment_algorithms dSOC-box wording / signs exactly:
//   dSOC=+46%  (signed, 0dp) · +182.0 kWh (signed, 1dp) · C=396 kWh (0dp) ·
//   EP=1.496 kWh/km (3dp, trips only). seg.* is null/absent when the metric is NaN.
function eventLines(sg) {
  const out = [];
  const sgn = v => (v >= 0 ? "+" : "");
  if (sg.dsoc != null) out.push("dSOC=" + sgn(sg.dsoc) + sg.dsoc.toFixed(0) + "%");
  if (sg.dkwh != null) out.push(sgn(sg.dkwh) + sg.dkwh.toFixed(1) + " kWh");
  if (sg.cap != null) out.push("C=" + sg.cap.toFixed(0) + " kWh");
  if (sg.ep != null) out.push("EP=" + sg.ep.toFixed(3) + " kWh/km");
  return out;
}

// ── Segment overlay plugin: bands + event markers, per chart ─────────────────
// One plugin drives all segment visuals from the day's raw segments. Visibility
// is gated HERE (not by getSegments) so the two toolbar toggles stay independent:
//   • bands    — translucent trip/charge fills + dashed edges  (SHOW_SEG)
//   • markers  — start/end triangles on every chart            (SHOW_EVENTS)
//   • boxes    — per-event metric labels, inspect.html style, on the SoC chart
//                only (SHOW_EVENTS); ghosted, solid on hover; HTML divs inside
//                u.over so they get real hover + crisp text and pan/zoom along.
function segmentOverlayPlugin(getSegments, concept) {
  const isSoc = concept.id === "soc";
  const isMass = concept.id === "mass";   // mass chart: dashed mean line, no ▲
  let boxes = [];   // [{el, seg}] — populated only on the SoC chart

  // Bands behind the series (drawClear), so the data lines stay on top.
  function drawBands(u) {
    if (!SHOW_SEG) return;
    const segs = getSegments();
    if (!segs || !segs.length) return;
    const ctx = u.ctx;
    const top = u.bbox.top, hgt = u.bbox.height;
    ctx.save();
    segs.forEach(sg => {
      const x0 = u.valToPos(sg.s, "x", true);
      const x1 = u.valToPos(sg.e, "x", true);
      const col = BAND[sg.type] || "#888";
      ctx.fillStyle = col + "1f";   // ~12% alpha (hex 0x1f)
      ctx.fillRect(x0, top, Math.max(1, x1 - x0), hgt);
      ctx.strokeStyle = col;
      ctx.globalAlpha = 0.55;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(x0, top); ctx.lineTo(x0, top + hgt);
      ctx.moveTo(x1, top); ctx.lineTo(x1, top + hgt);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.setLineDash([]);
    });
    ctx.restore();
  }

  // Event triangles on top of the series (draw), so markers stay visible. A
  // triangle does NOT sit on the event's nominal band edge (s / e): that edge is
  // the SOC-based start/end instant, and a given channel (e.g. a sparse cumulative
  // counter) may carry NO sample exactly there. Instead, for every event AND every
  // plotted series (each source column, u.data[1..]) we anchor the triangle to
  // that series' nearest NON-NULL sample to the band edge — searching both inward
  // and outward and taking the closest in time — and draw an upward triangle (▲)
  // sitting ON the curve at that real boundary sample (apex at the data point).
  // This re-derives, per series in the browser, the same imperfect counter-vs-SOC
  // alignment the inspect.html / validation figures show (the segment algorithm's
  // internal _anchor_start_time / _anchor_end_time aren't in the payload). Because
  // each source has its own sample times, different series in one chart get
  // triangles at slightly different x — the per-source data boundaries. Coloured
  // by event type (trip red / charge amber).
  const ANCHOR_WINDOW_S = 1800;   // 30 min: if a series has no real sample within
                                  // this window of the band edge it has no data
                                  // near that boundary, so skip its triangle.
  function drawMarkers(u) {
    if (isMass) return;          // mass chart shows a dashed mean line instead
    if (!SHOW_EVENTS) return;
    const segs = getSegments();
    if (!segs || !segs.length) return;
    const xs = u.data[0];                 // sorted seconds-from-midnight (union x)
    if (!xs || !xs.length) return;
    const nSeries = u.data.length - 1;    // u.data[1..] = one column per source
    if (nSeries < 1) return;
    const ctx = u.ctx;
    const dpr = u.pxRatio || window.devicePixelRatio || 1;
    const h = 8 * dpr;             // triangle height in canvas px
    const half = h * 0.6;         // half base-width in canvas px
    // ▲ apex AT the data point (xc, yc), base hanging below — points up, sitting
    // on the curve at the real boundary sample.
    const upTri = (xc, yc) => {
      ctx.beginPath();
      ctx.moveTo(xc, yc);                  // apex = the data point (points up)
      ctx.lineTo(xc - half, yc + h);       // base-left
      ctx.lineTo(xc + half, yc + h);       // base-right
      ctx.closePath(); ctx.fill();
    };
    // First index i with xs[i] >= T (xs is sorted ascending).
    const bisect = T => {
      let lo = 0, hi = xs.length;
      while (lo < hi) { const mid = (lo + hi) >> 1; if (xs[mid] < T) lo = mid + 1; else hi = mid; }
      return lo;
    };
    // Index of column `col`'s nearest non-null sample to band edge T, searching
    // both directions; -1 if none within ANCHOR_WINDOW_S. xs sorted → the first
    // non-null hit on each side is that side's nearest; pick the smaller |dt|.
    const nearestIdx = (col, T) => {
      const p = bisect(T);
      let best = -1, bestDt = Infinity;
      for (let i = p; i < xs.length; i++) {            // scan outward to the right
        const dt = xs[i] - T;
        if (dt > ANCHOR_WINDOW_S) break;
        if (col[i] != null) { if (dt < bestDt) { bestDt = dt; best = i; } break; }
      }
      for (let i = p - 1; i >= 0; i--) {               // scan outward to the left
        const dt = T - xs[i];
        if (dt > ANCHOR_WINDOW_S) break;
        if (col[i] != null) { if (dt < bestDt) { bestDt = dt; best = i; } break; }
      }
      return best;
    };
    ctx.save();
    ctx.globalAlpha = 1;
    segs.forEach(sg => {
      ctx.fillStyle = BAND[sg.type] || "#888";
      for (let k = 1; k <= nSeries; k++) {
        const col = u.data[k];
        if (!col) continue;
        // start anchor, then end anchor — for THIS series.
        const iS = nearestIdx(col, sg.s);
        if (iS >= 0) upTri(u.valToPos(xs[iS], "x", true), u.valToPos(col[iS], "y", true));
        const iE = nearestIdx(col, sg.e);
        if (iE >= 0) upTri(u.valToPos(xs[iE], "x", true), u.valToPos(col[iE], "y", true));
      }
    });
    ctx.restore();
  }

  // Mass chart only: a dashed horizontal line per event at its robust mean mass
  // (seg.massMeanT, tonnes — precomputed in Python with the report's mass_agg so
  // it matches the validation figure's "Seg. Mean Mass"), spanning the event's
  // [s, e]. Mirrors the inspect.html / validation Panel-4 dashed line, coloured
  // by event type (trip red / charge amber) with a centred "NN.N t" label.
  // Gated by SHOW_EVENTS, so the "Event markers" toggle drives it like the
  // triangles it replaces on this chart. Bare-tractor / bobtail events
  // (seg.massTractorOnly — the ~10-11 t reads the Excel column excludes) are drawn
  // in a muted grey with a finer dash + a "(tractor)" label suffix so they read
  // distinctly from the loaded (report-tracked) mean-mass lines.
  function drawMassMeans(u) {
    if (!isMass || !SHOW_EVENTS) return;
    const segs = getSegments();
    if (!segs || !segs.length) return;
    const ctx = u.ctx;
    const dpr = u.pxRatio || window.devicePixelRatio || 1;
    ctx.save();
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    ctx.font = (10 * dpr) + "px -apple-system, 'Segoe UI', Roboto, sans-serif";
    segs.forEach(sg => {
      if (sg.massMeanT == null) return;
      const yp = u.valToPos(sg.massMeanT, "y", true);
      const x0 = u.valToPos(sg.s, "x", true);
      const x1 = u.valToPos(sg.e, "x", true);
      const tractor = !!sg.massTractorOnly;
      const col = tractor ? "#6b7280" : (BAND[sg.type] || "#888");  // grey = tractor
      ctx.lineWidth = tractor ? Math.max(1, 1.4 * dpr) : Math.max(1.5, 2 * dpr);
      ctx.strokeStyle = col;
      ctx.globalAlpha = tractor ? 0.8 : 0.95;
      ctx.setLineDash(tractor ? [3, 3] : [7, 4]);
      ctx.beginPath();
      ctx.moveTo(x0, yp); ctx.lineTo(x1, yp);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = col;
      const label = sg.massMeanT.toFixed(1) + " t" + (tractor ? " (tractor)" : "");
      ctx.fillText(label, (x0 + x1) / 2, yp - 2 * dpr);
    });
    ctx.globalAlpha = 1;
    ctx.restore();
  }

  // Create one info box per event that carries at least one metric (SoC chart).
  function buildBoxes(u) {
    boxes.forEach(b => b.el.remove());
    boxes = [];
    if (!isSoc) return;
    const segs = getSegments();
    if (!segs || !segs.length) return;
    segs.forEach(sg => {
      const lines = eventLines(sg);
      if (!lines.length) return;
      const el = document.createElement("div");
      el.className = "ev-box " + (sg.type === "charge" ? "charge" : "trip");
      el.innerHTML = lines.map(esc).join("<br>");
      u.over.appendChild(el);
      boxes.push({ el, seg: sg });
    });
  }

  // Position the info boxes over their events (CSS px relative to the plot area).
  // Centred over each band near the top, clamped inside the plot rect (u.over has
  // no overflow clip) and stagger-stacked in two rows so neighbours overlap less.
  function placeBoxes(u) {
    if (!boxes.length) return;
    const overW = u.over.clientWidth, overH = u.over.clientHeight;
    boxes.forEach((b, i) => {
      b.el.style.display = SHOW_EVENTS ? "" : "none";
      if (!SHOW_EVENTS) return;
      const xc = u.valToPos((b.seg.s + b.seg.e) / 2, "x");
      const bw = b.el.offsetWidth, bh = b.el.offsetHeight;
      let left = Math.max(0, Math.min(xc - bw / 2, overW - bw));
      let topPx = Math.max(0, Math.min(4 + (i % 2) * (bh + 3), overH - bh));
      b.el.style.left = left + "px";
      b.el.style.top = topPx + "px";
    });
  }

  return {
    hooks: {
      drawClear: drawBands,
      draw: u => { drawMarkers(u); drawMassMeans(u); placeBoxes(u); },
      ready: u => { buildBoxes(u); placeBoxes(u); },
      setSize: placeBoxes,
    },
  };
}

// ── Chart building ───────────────────────────────────────────────────────────
// Mirror an x-zoom/pan from one chart to all others (guarded re-entrancy).
function mirrorScale(u) {
  if (_syncing) return;
  _syncing = true;
  const { min, max } = u.scales.x;
  CHARTS.forEach(c => {
    if (c === u) return;
    if (c.scales.x.min !== min || c.scales.x.max !== max) {
      c.setScale("x", { min, max });
    }
  });
  _syncing = false;
}

// Per-chart canvas height in CSS px. Doubled (180 -> 360) for taller charts that
// read more clearly and give the SoC info boxes more vertical room. uPlot, its
// .u-over overlay and the resize handler all derive from this single constant.
const CHART_H = 360;

// y-axis spec → a short "y: …" hint for the chart title.
function yAxisHint(concept) {
  const y = concept.y;
  if (!y) return "y: auto";
  const fmt = n => (Math.abs(n) >= 1000 ? n.toLocaleString() : String(n));
  return "y: " + fmt(y[0]) + "–" + fmt(y[1]) + " " + concept.unit;
}

function makeChart(parent, concept, merged, getSegments) {
  const series = [{ label: "time", value: (u, v) => v == null ? "" : fmtClock(v, true) }];
  merged.srcs.forEach(src => {
    series.push({
      label: SRC_LABEL[src] || src,
      stroke: COL[src] || "#333",
      width: 1.4,
      points: { show: false },
      // Connect a source's own real samples across nulls. On multi-source charts
      // the union x-axis carries a null for this source at every timestamp that
      // belongs only to the OTHER source; spanGaps bridges those so each line
      // stays continuous through its real data. The 0/86400 x-sentinels (range
      // only, null y everywhere) are also bridged, which is fine.
      spanGaps: true,
      value: (u, v) => v == null ? "—" : v.toFixed(2),
    });
  });
  const card = document.createElement("div");
  card.className = "chart-card";
  const title = document.createElement("div");
  title.className = "chart-title";
  let srcTags = '<span class="ct-src">';
  merged.srcs.forEach(src => {
    srcTags += '<span><i style="background:' + (COL[src] || "#333") + '"></i>'
      + (SRC_LABEL[src] || src) + '</span>';
  });
  srcTags += '</span>';
  title.innerHTML = '<span>' + esc(concept.name) + ' (' + esc(concept.unit) + ')</span>'
    + '<span class="ct-axis">' + esc(yAxisHint(concept)) + '</span>' + srcTags;
  card.appendChild(title);
  const host = document.createElement("div");
  card.appendChild(host);
  parent.appendChild(card);

  // x: FIXED to the full day. Sentinels (mergeSeries) put 0 and 86400 in the
  // data, and zero x-padding makes autoscale / dblclick-reset land on exactly
  // [0, 86400]; drag-zoom still sets an explicit sub-range. y: per-concept fixed
  // [min,max] (bounded signal) or autoscale (cumulative / route-dependent).
  const yScale = concept.y ? { range: concept.y.slice() } : {};
  const opts = {
    width: host.clientWidth || (parent.clientWidth - 40),
    height: CHART_H,
    series: series,
    cursor: {
      // Share only the x crosshair (each chart keeps its own y scale). uPlot
      // auto-registers into the sync group from this key — do not sub() again.
      sync: { key: SYNC.key, scales: ["x", null] },
      drag: { x: true, y: false },
    },
    scales: {
      // x: the object range form { min:{pad:0}, max:{pad:0} } came out degenerate
      // (no x ticks, no data line). The function form returns the data extent as-is:
      // with the mergeSeries sentinels (0, 86400) this yields the zero-padded full-day
      // default, while still honouring an explicit sub-range from drag-zoom (so reset
      // lands on [0, 86400] and zoom keeps working).
      x: { time: false, range: (u, mn, mx) => [mn, mx] },
      y: yScale,
    },
    axes: [
      // x: clock axis. `incrs` constrains zoom ticks to the clean-clock ladder;
      // `splits` forces fixed 1-hour ticks at the full-day view (else steps on
      // foundIncr); `values` renders HH:MM. `space` is the min px between ticks
      // uPlot uses to pick the increment from the ladder.
      { incrs: X_INCRS, splits: xSplits, values: xValues,
        space: 60, font: X_AXIS_FONT, size: X_AXIS_SIZE,
        grid: { stroke: "#eef2f7" } },
      { size: 52, grid: { stroke: "#eef2f7" } },
    ],
    legend: { live: true },
    plugins: [segmentOverlayPlugin(getSegments, concept)],
    hooks: { setScale: [(u, key) => { if (key === "x") mirrorScale(u); }] },
  };
  const u = new uPlot(opts, merged.data, host);
  CHARTS.push(u);
  return u;
}

function destroyCharts() {
  CHARTS.forEach(u => { try { u.destroy(); } catch (e) {} });
  CHARTS = [];
}

function esc(s) {
  return (s == null ? "" : String(s)).replace(/&/g, "&amp;")
    .replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// Render an "empty" placeholder card for a checked concept that has no data on
// the current day — so a ticked channel never silently disappears.
function emptyCard(parent, concept) {
  const card = document.createElement("div");
  card.className = "chart-card empty";
  card.innerHTML = '<div class="chart-empty"><span class="ce-name">'
    + esc(concept.name) + '</span><span>no data on this day</span></div>';
  parent.appendChild(card);
}

// ── Render the right-hand chart column for the current selection ──────────────
async function renderCharts() {
  const token = ++_renderToken;          // stale-render guard across awaits
  const area = document.getElementById("chartArea");
  if (!CUR_DATE || !PAYLOAD.days[CUR_DATE]) {
    destroyCharts(); area.innerHTML = '<div class="empty-note">No raw data for this day.</div>';
    return;
  }
  const day = PAYLOAD.days[CUR_DATE];
  // Selected concepts, in registry (catalogue) order for a stable layout.
  const chosen = PAYLOAD.concepts.filter(c => SELECTED.has(c.id));
  if (!chosen.length) {
    destroyCharts();
    area.innerHTML = '<div class="empty-note">Select one or more channels on the left.</div>';
    return;
  }
  // Always hand the plugin the raw segments; SHOW_SEG / SHOW_EVENTS gate the
  // bands vs the markers/boxes independently inside segmentOverlayPlugin.
  const getSegments = () => (day.segments || []);

  // Build phase: inflate every series first (no DOM writes). A concept with no
  // data this day is marked empty so it still gets a placeholder card.
  const built = [];
  for (const concept of chosen) {
    if (!day.concepts[concept.id]) { built.push({ concept, empty: true }); continue; }
    const perSource = [];
    for (const src of SRC_ORDER) {
      if (!day.concepts[concept.id][src]) continue;
      const s = await seriesFor(CUR_DATE, day, concept.id, src);
      perSource.push({ src, t: s.t, v: s.v });
    }
    if (perSource.length) built.push({ concept, merged: mergeSeries(perSource) });
    else built.push({ concept, empty: true });
  }
  if (token !== _renderToken) return;    // a newer render superseded us

  // Commit phase: tear down old charts and lay out the new column.
  destroyCharts();
  area.innerHTML = "";
  built.forEach(b => {
    if (b.empty) emptyCard(area, b.concept);
    else makeChart(area, b.concept, b.merged, getSegments);
  });
}

// Does the current day carry any data for this concept?
function dayHasConcept(cid) {
  const day = CUR_DATE && PAYLOAD.days[CUR_DATE];
  return !!(day && day.concepts[cid]);
}

// ── Left channel checklist (grouped, source-coloured) ────────────────────────
function buildChannelList() {
  const el = document.getElementById("chanList");
  const groups = {};
  PAYLOAD.concepts.forEach(c => { (groups[c.group] = groups[c.group] || []).push(c); });
  let h = "";
  PAYLOAD.groupOrder.forEach(g => {
    const items = groups[g];
    if (!items || !items.length) return;
    h += '<div class="chan-group">' + esc(g) + '</div>';
    items.forEach(c => {
      const checked = SELECTED.has(c.id) ? " checked" : "";
      let chips = '<span class="chan-src">';
      c.sources.forEach(s => {
        chips += '<span class="src-chip" title="' + esc(SRC_LABEL[s] || s)
          + '" style="background:' + (COL[s] || "#333") + '"></span>';
      });
      chips += '</span>';
      // Single-source concept: colour the name by its source. Multi-source: keep
      // neutral text but show the per-source chips on the right.
      const nameCol = (c.sources.length === 1) ? (COL[c.sources[0]] || "#1f2937") : "#1f2937";
      h += '<label class="chan-item" data-cid="' + esc(c.id) + '">'
        + '<input type="checkbox" data-cid="' + esc(c.id) + '"' + checked + '>'
        + '<span class="chan-name" style="color:' + nameCol + '">' + esc(c.name)
        + '</span>' + chips + '</label>';
    });
  });
  el.innerHTML = h;
  el.querySelectorAll('input[type=checkbox]').forEach(cb => {
    cb.addEventListener("change", () => {
      const cid = cb.dataset.cid;
      if (cb.checked) SELECTED.add(cid); else SELECTED.delete(cid);
      updateSelCount();
      renderCharts();
    });
  });
  refreshAvailabilityMarks();
  updateSelCount();
}

// Dim concepts with no data on the selected day (still selectable → placeholder).
function refreshAvailabilityMarks() {
  document.querySelectorAll('.chan-item[data-cid]').forEach(it => {
    const has = dayHasConcept(it.dataset.cid);
    it.classList.toggle("no-data", !has);
    it.title = has ? "" : "No data on the selected day";
  });
}

function updateSelCount() {
  const el = document.getElementById("chanCount");
  if (el) el.textContent = SELECTED.size ? "(" + SELECTED.size + ")" : "";
}

// Select-all (only concepts with data this day) / select-none.
function setAllSelected(on) {
  SELECTED.clear();
  if (on) PAYLOAD.concepts.forEach(c => { if (dayHasConcept(c.id)) SELECTED.add(c.id); });
  document.querySelectorAll('#chanList input[type=checkbox]').forEach(cb => {
    cb.checked = SELECTED.has(cb.dataset.cid);
  });
  updateSelCount();
  renderCharts();
}

// ── Header (operator + day + mode) ───────────────────────────────────────────
// Resolve the operator for a date by scanning the vehicle's few periods (open
// bounds = whole axis). Returns {name, color} or null when none is assigned.
function operatorFor(dateIso) {
  const op = PAYLOAD.operator;
  if (!op || !op.periods || !op.periods.length || !dateIso) return null;
  for (const p of op.periods) {
    const after = (p.s == null) || (dateIso >= p.s);
    const before = (p.e == null) || (dateIso <= p.e);
    if (after && before) {
      const name = (op.names && op.names[p.c]) || p.c;
      const color = (op.colors && op.colors[p.c]) || op.neutral || "#6b7280";
      return { name, color };
    }
  }
  return null;
}
function updateHeaderForDay() {
  document.getElementById("dayLabel").textContent = CUR_DATE || "—";
  const chip = document.getElementById("opChip");
  const op = operatorFor(CUR_DATE);
  if (op) {
    chip.innerHTML = '<span class="op-dot" style="background:' + op.color + '"></span>' + esc(op.name);
    chip.hidden = false;
  } else {
    chip.hidden = true;
  }
}

// ── Band legend (trip / charge shading) ──────────────────────────────────────
function buildBandLegend() {
  const el = document.getElementById("bandLegend");
  let h = "";
  ["trip", "charge"].forEach(t => {
    h += '<span class="bl-item"><span class="bl-swatch" style="background:' + BAND[t]
      + '33;border:1px solid ' + BAND[t] + '"></span>' + esc(BAND_LABEL[t]) + '</span>';
  });
  // Event-marker key: start/end triangles (most charts) + metric box (SoC chart)
  // + dashed mean-mass line (mass chart, in place of the triangles).
  h += '<span class="bl-item"><span class="bl-tri"></span>Event start / end markers (on each line)</span>';
  h += '<span class="bl-item"><span class="bl-line" style="border-top-style:dashed;'
    + 'border-top-color:#d97706"></span>Mean mass per event (mass chart)</span>';
  h += '<span class="bl-item"><span class="bl-line" style="border-top-style:dashed;'
    + 'border-top-color:#6b7280"></span>Bare-tractor / bobtail (report-excluded)</span>';
  h += '<span class="bl-note">Event bands shade report events; triangles sit on each '
    + 'line at the real sample nearest each event’s start/end (per source), with '
    + 'metrics on the SoC chart (hover to read). The mass chart instead draws a '
    + 'dashed line at each event’s mean mass (matches the validation figure); '
    + 'bare-tractor / bobtail events the report excludes are shown as a muted grey '
    + 'dashed line labelled “(tractor)”. '
    + 'Drag to zoom · double-click to reset to 00:00–24:00.</span>';
  el.innerHTML = h;
  el.classList.toggle("off", !SHOW_SEG && !SHOW_EVENTS);
}

// ── Day switching ────────────────────────────────────────────────────────────
function buildDaySelect() {
  const sel = document.getElementById("daySel");
  const dates = Object.keys(PAYLOAD.days).sort();
  sel.innerHTML = dates.map(d => '<option value="' + d + '">' + d + '</option>').join("");
  sel.value = CUR_DATE;
  sel.addEventListener("change", () => { setDate(sel.value); });
  // Prev/next steppers walk the dropdown's OPTIONS (data-bearing days), then
  // route through setDate so the day switches exactly like a free dropdown pick.
  const prev = document.getElementById("dayPrev");
  const next = document.getElementById("dayNext");
  if (prev) prev.addEventListener("click", () => {
    if (sel.selectedIndex > 0) { sel.selectedIndex -= 1; setDate(sel.value); }
  });
  if (next) next.addEventListener("click", () => {
    if (sel.selectedIndex < sel.options.length - 1) { sel.selectedIndex += 1; setDate(sel.value); }
  });
  syncDayNav();
}
// Disable the prev arrow on the first option and next on the last (clamp ends).
function syncDayNav() {
  const sel = document.getElementById("daySel");
  const prev = document.getElementById("dayPrev");
  const next = document.getElementById("dayNext");
  if (!sel || !prev || !next) return;
  prev.disabled = (sel.selectedIndex <= 0);
  next.disabled = (sel.selectedIndex >= sel.options.length - 1);
}
function setDate(d) {
  CUR_DATE = d;
  const sel = document.getElementById("daySel");
  if (sel && sel.value !== d) sel.value = d;
  syncDayNav();
  updateHeaderForDay();
  refreshAvailabilityMarks();
  renderCharts();
}

// ── Init ─────────────────────────────────────────────────────────────────────
function init() {
  const q = parseQuery();
  const dates = Object.keys(PAYLOAD.days).sort();
  // Default-checked concepts (registry default flag).
  PAYLOAD.concepts.forEach(c => { if (c.default) SELECTED.add(c.id); });
  // View mode + segments default (segments ON in events mode, OFF in raw mode).
  MODE = (q.mode === "raw") ? "raw" : "events";
  SHOW_SEG = (MODE !== "raw");
  document.getElementById("segChk").checked = SHOW_SEG;
  // Event markers default ON in both modes (independent of the bands toggle).
  SHOW_EVENTS = true;
  document.getElementById("eventChk").checked = SHOW_EVENTS;
  document.getElementById("modeChip").textContent =
    (MODE === "raw") ? "Raw-data view" : "Events view";

  // Resolve the requested date (fall back to the first available day).
  CUR_DATE = (q.date && PAYLOAD.days[q.date]) ? q.date
    : (dates.length ? dates[0] : null);

  buildBandLegend();
  buildChannelList();
  buildDaySelect();
  updateHeaderForDay();

  document.getElementById("selAll").addEventListener("click", () => setAllSelected(true));
  document.getElementById("selNone").addEventListener("click", () => setAllSelected(false));
  document.getElementById("resSel").addEventListener("change", e => {
    RES = e.target.value; renderCharts();
  });
  document.getElementById("segChk").addEventListener("change", e => {
    SHOW_SEG = e.target.checked;
    document.getElementById("bandLegend").classList.toggle("off", !SHOW_SEG && !SHOW_EVENTS);
    CHARTS.forEach(u => u.redraw());
  });
  // Event markers (triangles + info boxes) — independent of the bands toggle.
  // A redraw re-runs drawMarkers + placeBoxes, which honour SHOW_EVENTS.
  document.getElementById("eventChk").addEventListener("change", e => {
    SHOW_EVENTS = e.target.checked;
    document.getElementById("bandLegend").classList.toggle("off", !SHOW_SEG && !SHOW_EVENTS);
    CHARTS.forEach(u => u.redraw());
  });
  let _rsz;
  window.addEventListener("resize", () => {
    clearTimeout(_rsz);
    _rsz = setTimeout(() => {
      const area = document.getElementById("chartArea");
      const w = area.clientWidth - 28;
      CHARTS.forEach(u => u.setSize({ width: w, height: CHART_H }));
    }, 120);
  });

  renderCharts();
}
document.addEventListener("DOMContentLoaded", init);
"""
