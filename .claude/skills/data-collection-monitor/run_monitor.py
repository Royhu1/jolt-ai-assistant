"""JOLT fleet data-collection monitor — one loop iteration.

What it does (per run, for every watched vehicle):
  1. Looks at the canonical report database ``excel_report_database/<version>/<REG>/``
     and finds the latest period already covered.
  2. EXTENDS the database forward in time with the latest jolt_toolkit — it generates
     reports ONLY for the gap *after* the latest existing coverage, and SKIPS any period
     whose .xlsx already exists. It never regenerates / overwrites an existing report or
     its raw-data files (append-only). This is the "check SRF for newly-collected data"
     step.
  3. Refreshes the data-availability dashboard from the same database.
  4. Emits a fixed-template PDF "data collection digest" — a single fleet
     data-collection overview table for the most-recent window — into
     ``data_collection_reports/`` and updates ``MONITOR_STATUS.md`` (which records the
     loop cadence / last run / next due — the place the loop period is displayed).

Run from the repo root (needs ``.env`` with ``SRF_API_KEY`` and the canonical
``excel_report_database/``):

    python .claude/skills/data-collection-monitor/run_monitor.py
    python .claude/skills/data-collection-monitor/run_monitor.py --cadence weekly --window-days 7
    python .claude/skills/data-collection-monitor/run_monitor.py --veh YK73WFN,AV24LXJ
    python .claude/skills/data-collection-monitor/run_monitor.py --dry-run   # no SRF/dashboard; PDF from existing data

The toolkit version is read from the installed ``jolt_toolkit`` (shared across the conda
env) unless ``--version`` is given — so the monitor always uses the current latest version.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

SKILL_DIR = Path(__file__).resolve().parent
_FNAME_RE = re.compile(r"^jolt_report_(?P<reg>[A-Z0-9]+)_(?P<ds>\d{8})_(?P<de>\d{8})(?P<ft>_finetuned)?\.xlsx$")

# Cadence -> default lookback window (days). Used when --window-days is not given.
CADENCE_DAYS = {"daily": 1, "weekly": 7, "fortnightly": 14, "monthly": 30}

MAX_CHUNK_DAYS = 90  # split a long forward-extension gap into <=quarter pieces

log = logging.getLogger("data-collection-monitor")


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _d8(d: date) -> str:
    return d.strftime("%Y%m%d")


def _iso(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _parse_d8(s: str) -> date:
    return datetime.strptime(s, "%Y%m%d").date()


def _chunk(start: date, end: date, max_days: int = MAX_CHUNK_DAYS) -> list[tuple[date, date]]:
    """Split [start, end] (inclusive) into consecutive <= max_days pieces."""
    out: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        stop = min(cur + timedelta(days=max_days - 1), end)
        out.append((cur, stop))
        cur = stop + timedelta(days=1)
    return out


def _classify(leg_type: str) -> str:
    low = str(leg_type or "").lower()
    if "stop" in low:
        return "stop"
    if re.search(r"\b(ac|dc)\b", low) or "charg" in low:
        return "charge"
    return "trip"


def _fmt_dt(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "—"
    try:
        return pd.Timestamp(x).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(x)


def _pretty_op(s: str) -> str:
    """Display an operator code: underscores -> spaces, keep case (abbreviations intact)."""
    return str(s or "").replace("_", " ").strip() or "—"


def _latest_cell(ts, win_start: date) -> dict:
    """Classify a per-source latest timestamp: fresh (in window) / stale (older) / none."""
    if ts is None or (isinstance(ts, float) and pd.isna(ts)):
        return {"text": "—", "cls": "none"}
    t = pd.Timestamp(ts)
    if pd.isna(t):
        return {"text": "—", "cls": "none"}
    return {"text": t.strftime("%Y-%m-%d %H:%M"), "cls": "fresh" if t.date() >= win_start else "stale"}


# --------------------------------------------------------------------------- #
# per-vehicle result container
# --------------------------------------------------------------------------- #
@dataclass
class VehicleResult:
    reg: str
    model: str = ""
    operator: str = "—"
    energy_type: str = "EV"
    status: str = "up_to_date"  # up_to_date | extended | no_new_data | no_baseline | error
    error: str = ""
    last_covered: date | None = None
    generated: list[tuple[date, date]] = field(default_factory=list)
    skipped: list[tuple[date, date]] = field(default_factory=list)
    empty: list[tuple[date, date]] = field(default_factory=list)  # attempted but toolkit wrote nothing
    n_trips: int = 0
    n_charges: int = 0
    n_stops: int = 0
    n_telematics: int = 0  # window legs backed by SRF FPS telematics
    n_logger: int = 0      # window legs backed by SRF logger
    active_days: int = 0
    distance_km: float = 0.0
    energy_kwh: float = 0.0
    charged_kwh: float = 0.0
    latest_tel: datetime | None = None  # most recent telematics data ever (may predate window)
    latest_log: datetime | None = None  # most recent SRF logger data ever (may predate window)
    n_charger: int = 0                  # charger transactions (charge-point records) in the window
    latest_charger: datetime | None = None  # most recent charger transaction ever

    @property
    def new_data(self) -> bool:
        return self.n_trips + self.n_charges > 0 or len(self.generated) > 0


# --------------------------------------------------------------------------- #
# read existing reports + window slice
# --------------------------------------------------------------------------- #
def _existing_periods(vdir: Path, reg: str) -> dict[tuple[str, str], Path]:
    """Map (ds8, de8) -> best xlsx path (prefer *_finetuned) for this vehicle."""
    out: dict[tuple[str, str], Path] = {}
    if not vdir.is_dir():
        return out
    for p in vdir.glob("jolt_report_*.xlsx"):
        m = _FNAME_RE.match(p.name)
        if not m or m.group("reg") != reg:
            continue
        key = (m.group("ds"), m.group("de"))
        if m.group("ft") or key not in out:
            out[key] = p  # finetuned wins; otherwise first seen
    return out


def _read_window(periods: dict[tuple[str, str], Path], win_start: date, win_end: date) -> pd.DataFrame:
    """Concatenate Report sheets of periods overlapping the window, slice to window."""
    win_lo = pd.Timestamp(win_start)
    win_hi = pd.Timestamp(win_end) + pd.Timedelta(days=1)  # exclusive upper bound
    frames: list[pd.DataFrame] = []
    for (ds8, de8), path in periods.items():
        # cheap pre-filter: skip periods that cannot overlap the window
        if _parse_d8(de8) < win_start or _parse_d8(ds8) > win_end:
            continue
        try:
            df = pd.read_excel(path, sheet_name="Report")
        except Exception as exc:  # locked / unreadable workbook
            log.warning("could not read %s: %s", path.name, exc)
            continue
        if "Start Time (UTC)" not in df.columns:
            continue
        df["Start Time (UTC)"] = pd.to_datetime(df["Start Time (UTC)"], errors="coerce")
        df = df[(df["Start Time (UTC)"] >= win_lo) & (df["Start Time (UTC)"] < win_hi)]
        if len(df):
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("Start Time (UTC)")


def _latest_by_source(periods: dict[tuple[str, str], Path]):
    """Most-recent telematics / SRF-logger leg start time across ALL of this vehicle's
    reports (newest file first, stop once both found). Returns (tel_ts, log_ts), each
    None if that source never produced data — so the digest can show the last time a
    source was seen even if it predates the window, or a dash if never."""
    items = sorted(periods.items(), key=lambda kv: kv[0][1], reverse=True)  # by end-date desc
    tel = log = None
    for _key, path in items:
        if tel is not None and log is not None:
            break
        try:
            df = pd.read_excel(path, sheet_name="Report")
        except Exception as exc:  # noqa: BLE001
            log.warning("could not read %s for latest-source: %s", path.name, exc)
            continue
        if "Start Time (UTC)" not in df.columns:
            continue
        st = pd.to_datetime(df["Start Time (UTC)"], errors="coerce")
        if tel is None and "Telematics Link" in df.columns:
            m = st[df["Telematics Link"].notna()].dropna()
            if len(m):
                tel = m.max()
        if log is None and "SRF Logger Link" in df.columns:
            m = st[df["SRF Logger Link"].notna()].dropna()
            if len(m):
                log = m.max()
    return tel, log


def _charger_stats(vdir: Path, win_start: date, win_end: date):
    """Charger-transaction collection for one vehicle, from
    ``raw_charger/charger_transactions.csv`` (a distinct SRF data source from the
    telematics / logger leg data). Returns (n_in_window, latest_ts): n_in_window counts
    charge-point transactions whose ``start_time`` falls in [win_start, win_end];
    latest_ts is the most recent transaction start ever (None if the file is absent /
    empty / unreadable)."""
    csv = vdir / "raw_charger" / "charger_transactions.csv"
    if not csv.is_file():
        return 0, None
    try:
        df = pd.read_csv(csv, usecols=["start_time"])
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read %s: %s", csv, exc)
        return 0, None
    st = pd.to_datetime(df["start_time"], errors="coerce", utc=True).dropna()
    if st.empty:
        return 0, None
    d = st.dt.tz_convert(None)  # naive UTC for date comparison / display
    in_win = int(((d.dt.date >= win_start) & (d.dt.date <= win_end)).sum())
    return in_win, d.max()


# --------------------------------------------------------------------------- #
# report generation (append-only, skip-existing)
# --------------------------------------------------------------------------- #
def _generate(out_dir: Path, reg: str, ds: date, de: date, raw: bool, fast: bool) -> None:
    """Generate one report via the toolkit. Imported lazily so --dry-run needs no SRF."""
    from jolt_toolkit.report_generator._generator import JOLTReportGenerator

    gen = JOLTReportGenerator(
        report_output_folder=str(out_dir),
        overwrite_existing_report=True,  # the skip-existing gate lives in the caller
        debug_mode=raw,                  # raw=True -> save raw telematics CSV + inspect HTML
        fast_mode=fast,
        save_figures=False,              # the monitor never needs baked validation figures
    )
    gen.generate_report(vehicle_registration=reg, date_start=_iso(ds), date_end=_iso(de))


# --------------------------------------------------------------------------- #
# main per-vehicle pipeline
# --------------------------------------------------------------------------- #
def _process_vehicle(
    reg: str,
    model: str,
    operator: str,
    energy_type: str,
    db_root: Path,
    win_start: date,
    win_end: date,
    end_date: date,
    raw: bool,
    fast: bool,
    force: bool,
    dry_run: bool,
    max_backfill_days: int = 0,
) -> VehicleResult:
    res = VehicleResult(reg=reg, model=model, operator=operator, energy_type=energy_type)
    vdir = db_root / reg

    existing = _existing_periods(vdir, reg)
    if existing:
        res.last_covered = max(_parse_d8(de) for _, de in existing)

    # --- forward extension (append-only, skip-existing) ---
    if not dry_run:
        if res.last_covered:
            gen_start = res.last_covered + timedelta(days=1)
        else:
            gen_start = win_start  # no baseline -> only fetch the lookback window
            res.status = "no_baseline"
        gen_end = end_date
        # optionally cap how far back a stale/dormant vehicle is re-fetched each run
        if max_backfill_days and (gen_end - gen_start).days + 1 > max_backfill_days:
            gen_start = gen_end - timedelta(days=max_backfill_days - 1)

        if gen_start <= gen_end:
            for cs, ce in _chunk(gen_start, gen_end):
                target = vdir / f"jolt_report_{reg}_{_d8(cs)}_{_d8(ce)}.xlsx"
                if target.exists() and not force:
                    res.skipped.append((cs, ce))
                    continue
                try:
                    log.info("[%s] generating %s -> %s", reg, _iso(cs), _iso(ce))
                    _generate(db_root, reg, cs, ce, raw=raw, fast=fast)
                    # the toolkit skips writing when there are no valid segments, so a
                    # written file (not merely a clean call) is what proves new data.
                    (res.generated if target.exists() else res.empty).append((cs, ce))
                except Exception as exc:  # noqa: BLE001 - keep the fleet run going
                    res.status = "error"
                    res.error = f"{type(exc).__name__}: {exc}"
                    log.warning("[%s] generation failed: %s", reg, res.error)
        # refresh the period map so the window read sees freshly-written files
        existing = _existing_periods(vdir, reg)

    # --- window slice for the digest ---
    df = _read_window(existing, win_start, win_end)
    if len(df) and "Leg Type" in df.columns:
        df = df.assign(_kind=df["Leg Type"].map(_classify))
        trips = df[df["_kind"] == "trip"]
        charges = df[df["_kind"] == "charge"]
        stops = df[df["_kind"] == "stop"]

        res.n_trips = int(len(trips))
        res.n_charges = int(len(charges))
        res.n_stops = int(len(stops))
        # data-source coverage in the window: count legs carrying each SRF source link.
        if "Telematics Link" in df:
            res.n_telematics = int(df["Telematics Link"].notna().sum())
        if "SRF Logger Link" in df:
            res.n_logger = int(df["SRF Logger Link"].notna().sum())
        if "Distance (km)" in trips:
            res.distance_km = float(pd.to_numeric(trips["Distance (km)"], errors="coerce").sum())
        if "Energy Change (kWh)" in trips:
            res.energy_kwh = float(pd.to_numeric(trips["Energy Change (kWh)"], errors="coerce").abs().sum())
        for col in ("Energy Charged AC (kWh)", "Energy Charged DC (kWh)"):
            if col in charges:
                res.charged_kwh += float(pd.to_numeric(charges[col], errors="coerce").abs().sum())
        active = pd.concat([trips["Start Time (UTC)"], charges["Start Time (UTC)"]])
        res.active_days = int(active.dt.date.nunique()) if len(active) else 0

    # most-recent telematics / logger ever (may predate the window; None = never)
    res.latest_tel, res.latest_log = _latest_by_source(existing)
    # charger-transaction collection (count in window + latest ever)
    res.n_charger, res.latest_charger = _charger_stats(vdir, win_start, win_end)

    # --- final status ---
    if res.status not in ("error", "no_baseline"):
        if res.new_data:
            res.status = "extended"
        elif res.empty:
            res.status = "no_new_data"  # attempted, but SRF returned no usable segments
        else:
            res.status = "up_to_date"
    return res


# --------------------------------------------------------------------------- #
# operator resolution (from plot_config.json company_assignment)
# --------------------------------------------------------------------------- #
def _make_operator_resolver(repo_root: Path, end_date: date):
    ca: dict = {}
    try:
        pc = json.loads((repo_root / "src/jolt_toolkit/configs/plot_config.json").read_text(encoding="utf-8"))
        ca = pc.get("company_assignment", {}) or {}
    except Exception:  # noqa: BLE001
        pass
    simple = ca.get("simple", {})
    rr = ca.get("round_robin", {})
    we = _d8(end_date)

    def resolve(reg: str) -> str:
        if reg in simple:
            return _pretty_op(simple[reg])
        spans = rr.get(reg)
        if spans:
            for e in spans:
                if str(e.get("date_start", "")) <= we <= str(e.get("date_end", "99999999")):
                    return _pretty_op(e.get("company", ""))
            return _pretty_op(max(spans, key=lambda e: str(e.get("date_end", ""))).get("company", ""))
        return "—"

    return resolve


# --------------------------------------------------------------------------- #
# charger backfill sweep
# --------------------------------------------------------------------------- #
def _charger_backfill_sweep(repo_root: Path, version: str) -> str:
    """Re-patch Charger Links across ALL existing reports of the watched version.

    SRF charge-point transactions can arrive days/weeks after the vehicle
    telematics (and are only fused at generation time), so each monitor run
    sweeps the whole version dir with the charger_patcher CLI (v2.2.8+):
    idempotent — only empty Charger Link cells are filled — and ``--persist-raw``
    merge-accumulates ``raw_charger/charger_transactions.csv`` per vehicle,
    which is exactly the file this monitor's digest and the dashboard read.
    Runs BEFORE the per-vehicle processing so the digest counts the refreshed CSVs.
    """
    cmd = [sys.executable, "-m", "jolt_toolkit.report_generator.charger_patcher",
           str(repo_root / "excel_report_database" / version), "--persist-raw"]
    log.info("charger backfill sweep: %s", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
    if proc.returncode != 0:
        log.warning("charger sweep exit=%s: %s", proc.returncode, (proc.stderr or "").strip()[-400:])
        return f"charger sweep FAILED (exit {proc.returncode})"
    combined = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
    return "\n".join(line for line in combined[-3:])


# --------------------------------------------------------------------------- #
# dashboard + PDF + status
# --------------------------------------------------------------------------- #
def _refresh_dashboard(repo_root: Path, version: str) -> str:
    cmd = [sys.executable, "-m", "jolt_toolkit.report_generator.data_dashboard", "--version", version]
    log.info("refreshing dashboard: %s", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
    if proc.returncode != 0:
        log.warning("dashboard refresh exit=%s: %s", proc.returncode, (proc.stderr or "").strip()[-400:])
        return f"dashboard refresh FAILED (exit {proc.returncode})"
    # the dashboard CLI logs its per-vehicle / fleet summary to stderr; surface the tail.
    combined = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
    return "\n".join(line for line in combined[-4:])


def _build_pdf(skill_dir: Path, out_dir: Path, ctx: dict, win_start: date, win_end: date) -> Path:
    import jinja2

    from build_digest_pdf import html_to_pdf

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(skill_dir / "templates")),
        autoescape=jinja2.select_autoescape(["html"]),
    )
    html = env.get_template("digest_template.html.j2").render(**ctx)
    stem = f"data_collection_digest_{_d8(win_start)}_{_d8(win_end)}"
    html_path = out_dir / f"{stem}.html"
    pdf_path = out_dir / f"{stem}.pdf"
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")
    return html_to_pdf(html_path, pdf_path)


def _write_status(
    out_dir: Path, cadence: str, lookback: int, version: str, win_start: date, win_end: date,
    generated_utc: str, next_due: str, results: list[VehicleResult], pdf_name: str,
) -> None:
    lines = [
        "# JOLT Data-Collection Monitor — Status",
        "",
        "> This file records the active monitoring loop. It is rewritten on every run.",
        "",
        f"- **Cadence (loop period):** {cadence}",
        f"- **Lookback window:** {lookback} days",
        f"- **Watched vehicles:** {len(results)}",
        f"- **Report DB version:** {version}",
        f"- **Last run (UTC):** {generated_utc}",
        f"- **Window covered:** {_iso(win_start)} → {_iso(win_end)}",
        f"- **Next run (UTC):** {next_due}",
        f"- **Latest digest:** {pdf_name}",
        "",
        "## Per-vehicle (last run)",
        "",
        "| Vehicle | Energy | Operator | Telematics | SRF logger | Charger | Trips | Charges | "
        "Active days | Distance (km) | Latest telematics | Latest SRF logger | Latest charger | Status |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.reg} | {r.energy_type} | {r.operator} | {r.n_telematics or '—'} | "
            f"{r.n_logger or '—'} | {r.n_charger or '—'} | {r.n_trips} | {r.n_charges} | {r.active_days} | "
            f"{r.distance_km:,.0f} | {_fmt_dt(r.latest_tel)} | {_fmt_dt(r.latest_log)} | {_fmt_dt(r.latest_charger)} | {r.status} |"
        )
    errs = [r for r in results if r.status == "error"]
    if errs:
        lines += ["", "### Errors", ""]
        lines += [f"- **{r.reg}**: {r.error}" for r in errs]
    lines += ["", "---", "_Maintained by `.claude/skills/data-collection-monitor/run_monitor.py`._", ""]
    (out_dir / "MONITOR_STATUS.md").write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- #
# context builder for the PDF
# --------------------------------------------------------------------------- #
def _build_context(
    results: list[VehicleResult], version: str, cadence: str, lookback: int,
    win_start: date, win_end: date, generated_utc: str, next_due: str,
) -> dict:
    fleet = [{
        "reg": r.reg,
        "operator": r.operator,
        "model": r.model,
        "energy_type": r.energy_type,
        "telematics": str(r.n_telematics) if r.n_telematics else "—",
        "logger": str(r.n_logger) if r.n_logger else "—",
        "charger": str(r.n_charger) if r.n_charger else "—",
        "n_trips": r.n_trips,
        "n_charges": r.n_charges,
        "active_days": r.active_days,
        "distance": f"{r.distance_km:,.0f}",
        "latest_tel": _latest_cell(r.latest_tel, win_start),
        "latest_log": _latest_cell(r.latest_log, win_start),
        "latest_chg": _latest_cell(r.latest_charger, win_start),
    } for r in results]

    meta = {
        "title": "JOLT Fleet — Data Collection Digest",
        "window_start": _iso(win_start), "window_end": _iso(win_end),
        "generated_utc": generated_utc, "version": version,
        "cadence": cadence, "lookback_days": lookback, "next_due": next_due,
        "n_vehicles": len(results),
    }
    return {"meta": meta, "fleet": fleet}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="JOLT fleet data-collection monitor (one loop iteration).")
    ap.add_argument("--repo-root", type=Path, default=Path.cwd(),
                    help="Repo root holding .env + excel_report_database/ (default: cwd).")
    ap.add_argument("--veh", type=str, default=None,
                    help="Comma-separated subset of registrations (default: watched_vehicles.json).")
    ap.add_argument("--cadence", type=str, default=None,
                    help="Loop cadence label: daily|weekly|fortnightly|monthly (default: from config).")
    ap.add_argument("--window-days", type=int, default=None,
                    help="Lookback window in days (default: derived from cadence).")
    ap.add_argument("--version", type=str, default=None,
                    help="Report DB version (default: installed jolt_toolkit.__version__).")
    ap.add_argument("--end-date", type=str, default=None,
                    help="Window end date YYYY-MM-DD (default: today UTC).")
    ap.add_argument("--out-folder", type=str, default="data_collection_reports",
                    help="Folder (under repo root) for PDF digests + MONITOR_STATUS.md.")
    ap.add_argument("--no-raw", action="store_true", help="Skip raw-telematics CSV (faster).")
    ap.add_argument("--fast", action="store_true", help="Pass fast_mode (skip SRF Logger/Charger fetch).")
    ap.add_argument("--force", action="store_true", help="Regenerate even if a window report file exists.")
    ap.add_argument("--max-backfill-days", type=int, default=0,
                    help="Cap how far back a stale/dormant vehicle is re-fetched each run "
                         "(0 = uncapped; e.g. 90 avoids re-querying months of empty gaps weekly).")
    ap.add_argument("--dry-run", action="store_true",
                    help="No SRF generation, no dashboard — build the PDF/status from existing data only.")
    ap.add_argument("--no-dashboard", action="store_true", help="Skip the dashboard refresh.")
    ap.add_argument("--no-pdf", action="store_true", help="Skip building the PDF digest.")
    ap.add_argument("--no-charger-sweep", action="store_true",
                    help="Skip the fleet-wide Charger Link backfill sweep (v2.2.8+).")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", force=True)
    repo_root = args.repo_root.resolve()
    load_dotenv(repo_root / ".env")

    # config defaults
    cfg = json.loads((SKILL_DIR / "watched_vehicles.json").read_text(encoding="utf-8"))
    cadence = (args.cadence or cfg.get("cadence", "weekly")).lower()
    lookback = args.window_days or CADENCE_DAYS.get(cadence, cfg.get("lookback_days", 7))
    vehicles = [v.strip().upper() for v in args.veh.split(",")] if args.veh else list(cfg["vehicles"])

    # version (lazy import keeps --help working without the package)
    if args.version:
        version = args.version
    else:
        from jolt_toolkit import __version__ as version

    # vehicle make/model + energy type (best-effort, from configs)
    models: dict[str, str] = {}
    fuels: dict[str, str] = {}
    try:
        vj = json.loads((repo_root / "src/jolt_toolkit/configs/vehicles.json").read_text(encoding="utf-8"))
        models = {k: f"{v.get('make', '')} {v.get('model', '')}".strip() for k, v in vj.items()}
        fuels = {k: ("Diesel" if str(v.get("fuel_type", "")).upper() == "DIESEL" else "EV")
                 for k, v in vj.items()}
    except Exception:  # noqa: BLE001
        pass
    # surface watched vehicles missing from vehicles.json — their energy type would
    # otherwise silently default to "EV" (this is what mislabelled diesel YT21EFD when
    # its config was not yet present on the branch a run used).
    missing_cfg = [r for r in vehicles if r not in fuels]
    if missing_cfg:
        log.warning("watched vehicles absent from vehicles.json (energy type defaults to EV — verify): %s",
                    ", ".join(missing_cfg))

    now_dt = datetime.now(timezone.utc)
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date() if args.end_date else now_dt.date()
    win_start = end_date - timedelta(days=lookback - 1)
    db_root = repo_root / "excel_report_database" / version
    out_dir = repo_root / args.out_folder
    generated_utc = now_dt.strftime("%Y-%m-%d %H:%M")
    # exact next run = this run's wall-clock + one cadence interval (no "approximately")
    next_due = (now_dt + timedelta(days=CADENCE_DAYS.get(cadence, lookback))).strftime("%Y-%m-%d %H:%M")
    operator_for = _make_operator_resolver(repo_root, end_date)

    log.info("Monitor v%s | %d vehicles | window %s→%s | cadence=%s | dry_run=%s",
             version, len(vehicles), _iso(win_start), _iso(end_date), cadence, args.dry_run)
    if not db_root.is_dir():
        log.error("report database not found: %s", db_root)
        return 2

    # charger backfill sweep — BEFORE per-vehicle processing, so the digest's
    # charger counts read the freshly merge-accumulated raw_charger CSVs.
    # New reports created below still get generation-time fusion; transactions
    # arriving later are caught by next run's sweep.
    charger_sweep_summary = ""
    if not args.dry_run and not args.no_charger_sweep:
        charger_sweep_summary = _charger_backfill_sweep(repo_root, version)

    results: list[VehicleResult] = []
    for reg in vehicles:
        log.info("=== %s ===", reg)
        results.append(_process_vehicle(
            reg, models.get(reg, ""), operator_for(reg), fuels.get(reg, "EV"), db_root, win_start,
            win_end=end_date, end_date=end_date,
            raw=not args.no_raw, fast=args.fast, force=args.force, dry_run=args.dry_run,
            max_backfill_days=args.max_backfill_days,
        ))

    # dashboard
    dash_summary = ""
    if not args.dry_run and not args.no_dashboard:
        dash_summary = _refresh_dashboard(repo_root, version)

    # PDF + status
    ctx = _build_context(results, version, cadence, lookback, win_start, end_date, generated_utc, next_due)
    pdf_name = "(skipped)"
    if not args.no_pdf:
        try:
            pdf = _build_pdf(SKILL_DIR, out_dir, ctx, win_start, end_date)
            pdf_name = pdf.name
        except Exception as exc:  # noqa: BLE001
            log.warning("PDF build failed: %s", exc)
            pdf_name = f"(PDF FAILED: {type(exc).__name__})"
    _write_status(out_dir, cadence, lookback, version, win_start, end_date,
                  generated_utc, next_due, results, pdf_name)

    # console summary
    n_new = sum(1 for r in results if r.new_data)
    n_err = sum(1 for r in results if r.status == "error")
    print("\n" + "=" * 78)
    print(f"DATA-COLLECTION MONITOR — {generated_utc} UTC | v{version}")
    print(f"window {_iso(win_start)} → {_iso(end_date)} | cadence {cadence} | next run {next_due} UTC")
    print("-" * 78)
    print(f"{'Vehicle':<9} {'type':<7} {'operator':<14} {'telem':>5} {'logr':>5} {'chgr':>5} "
          f"{'trips':>5} {'charg':>5} {'days':>4} {'dist km':>8}  status")
    for r in results:
        print(f"{r.reg:<9} {r.energy_type:<7} {r.operator[:14]:<14} {r.n_telematics:>5} {r.n_logger:>5} {r.n_charger:>5} "
              f"{r.n_trips:>5} {r.n_charges:>5} {r.active_days:>4} {r.distance_km:>8,.0f}  {r.status}")
    print("-" * 78)
    print(f"{n_new}/{len(results)} vehicles with new data | {n_err} error(s) | digest: {pdf_name}")
    if charger_sweep_summary:
        print("charger sweep:\n" + charger_sweep_summary)
    if dash_summary:
        print("dashboard:\n" + dash_summary)
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
