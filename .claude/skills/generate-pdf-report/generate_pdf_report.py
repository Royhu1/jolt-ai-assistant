"""从 JOLT 报告管线产物（excel_report_database/<ver>/<REG>/*.xlsx）生成工业界 PDF 简报。

流程：xlsx → 计算真实 KPI + 生成 JOLT 风格 matplotlib 图 → 渲染 Jinja2 模板
→ headless Chrome 出 PDF，并打印「字段适用性审计」（哪些是真实数据 / 哪些 N/A）。

用法（从仓库根运行）：
    python .claude/skills/generate-pdf-report/generate_pdf_report.py --reg YK73WFN --period 20250301_20250601
    python .claude/skills/generate-pdf-report/generate_pdf_report.py --reg YK73WFN --period 20250301_20250601 --base  # 用非 finetuned

产物写到 pdf_report_workspace/output/<REG>_<period>/（gitignored）。

图表风格刻意对齐 analysis/ 下的图：白底 + 浅网格 + 散点 + 线性拟合 + ±1σ 阴影带 + 图例。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from jinja2 import Template
from scipy.optimize import curve_fit
from scipy.signal import find_peaks
from scipy.stats import gaussian_kde

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from build_pdf import html_to_pdf  # noqa: E402

PROJECT = Path(__file__).resolve().parents[3]  # repo root (script lives at .claude/skills/generate-pdf-report/)
WORKSPACE = PROJECT / "pdf_report_workspace"  # artefact store: output/ + HERE-tile cache/
TEMPLATE = ROOT / "templates" / "report_template.html.j2"

DRIVE = {"Outbound", "Return", "In Transit", "Round Trip", "In House"}
CHARGE = {"DC Home", "AC Home", "Charge Home"}

# JOLT 配置（plot_config.json 子集 + vehicles.json 取电池容量）
PLOT_CFG = json.loads((PROJECT / "src/jolt_toolkit/configs/plot_config.json").read_text(encoding="utf-8"))
VEHICLES = json.loads((PROJECT / "src/jolt_toolkit/configs/vehicles.json").read_text(encoding="utf-8"))
# Skill-local per-vehicle briefing specs (unladen mass overrides + provenance). Kept inside the
# skill (not vehicles.json) to preserve the skill's self-containment; absent REG -> auto fallback.
_SPECS_PATH = ROOT / "briefing_vehicle_specs.json"
BRIEFING_SPECS = json.loads(_SPECS_PATH.read_text(encoding="utf-8")) if _SPECS_PATH.exists() else {}
OEM_BLUE = "#1f77b4"  # Volvo / matplotlib 默认蓝，贴合 analysis 图风格

# EP 合理范围：超出即视为不合理数据，直接剔除
EP_MIN, EP_MAX = 0.0, 3.0  # EP 图 y 轴范围（恒 0–3，与清洗界限分开）
# EP 清洗界限：EP ∉ [EP_CLEAN_MIN, EP_CLEAN_MAX] 视为不合理数据并剔除。下限 0.3 排除
# 极低 EP（极短/残段，如续航投影被 600/0.08 拉到上千 km 的伪值）；上限 3 排除异常高值。
EP_CLEAN_MIN, EP_CLEAN_MAX = 0.3, 3.0

# 有效 trip 的最小里程（km）：里程 < MIN_TRIP_KM（或里程缺失）的行驶段视为无效（极短/残段，
# EP 不可靠），从一切分析中剔除——OPERATING PERIOD、活跃天数、KPI、散点/拟合/点评统计均只基于
# 有效 trip（故运营周期 = 有效 event 决定的真实跨度）。
MIN_TRIP_KM = 3.0

# 轻/重载分组方式按车辆区分：此集合内的车保留**固定 1/3 三分位**的旧表述
# （"Lightest/Heaviest 1/3 of trips"，合作方风格基准，如 YK73WFN）；其余车用
# GVM 密度谷聚类（_gvm_cluster_split）。见 SKILL.md §5。
LEGACY_TERTILE_REGS = {"YK73WFN"}

# 单组分析（不分轻/重簇）：这些车主要满载运行、GVM 分簇无意义——改为只给
# **GVM > 阈值(t) 的离群剔除（IQR 1.5×）平均**（EP 与续航各一条 bullet）。值 = GVM 阈值(t)。
# 优先级高于 LEGACY_TERTILE_REGS / KDE 聚类。见 SKILL.md §5。
SINGLE_GROUP_REGS = {"YN25RSY": 17.0}

# 统一坐标轴范围与刻度（参数化，所有报告跨车辆/周期可比）
GVM_XLIM = (0, 45)               # gross vehicle mass 轴，t
GVM_XTICKS = range(0, 41, 10)    # 0/10/20/30/40
TEMP_XLIM = (-5, 30)           # ambient temperature 轴，°C
TEMP_XTICKS = range(0, 31, 10)  # 0/10/20/30（-5 起点不设刻度，避免拥挤）

# Reference full-laden gross mass (t) for the EP/Range conclusion + dashed fit extension.
# UK artic max ≈ 44 t; the briefing projects to 42 t. The dashed tail flags it as an
# extrapolation when a vehicle's observed GVM never reaches it (e.g. a rigid).
FULL_LADEN_T = 42.0

# 路线图底图请求像素尺寸 = 第 1 页地图卡显示窗口（约 370×530，竖版）的 2x。
# 必须与卡片纵横比一致：卡片用 object-fit:cover，比例不符会裁掉两侧（连带左上角图例）。
MAP_PX_W, MAP_PX_H = 740, 1060

# 三张散点图（EP-vs-GVM / Range-vs-GVM / EP-vs-temp）统一坐标区位置（figure 分数）。
# 钉死后绘图框像素跨图一致；边距按缩小后的轴字号 + y 刻度自适应（见 _finish_scatter）取定，
# 既容纳 Range 的 "Range (km)" 轴标题 + 三位 y 刻度、又让标签完整不被图边裁切。
# Square figures (1:1) for the 2x2 page-2 grid. No legend strip any more (legends removed),
# so the plot box reaches near the top; left/bottom leave room for the larger axis labels.
SCATTER_AXBOX = dict(left=0.160, right=0.945, top=0.945, bottom=0.135)

# ---- matplotlib 全局风格：对齐 analysis/ 图；字号约为原版 2x（标题/图例受图宽限制取 ~1.5x）----
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    # Axis labels deliberately smaller than the HTML chart titles (.chart-cell__title).
    "font.size": 16, "axes.titlesize": 18, "axes.labelsize": 16,
    "xtick.labelsize": 15, "ytick.labelsize": 15, "legend.fontsize": 13,
    "axes.grid": True, "grid.color": "#cfd3e0", "grid.linewidth": 0.7,
    "axes.edgecolor": "#9aa0b4", "axes.linewidth": 0.8, "axes.axisbelow": True,
    "figure.dpi": 200, "savefig.dpi": 200,
})

# 时间线 SVG 图标
ICON_TRUCK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M1 3h13v10H1z"/><path d="M14 6h4l3 3v4h-7z"/><circle cx="6" cy="17" r="2"/><circle cx="17" cy="17" r="2"/></svg>'
ICON_CLOCK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>'


def num(s):
    return pd.to_numeric(s, errors="coerce")


def _sum_or_na(s):
    """求和，但当整列没有任何有效值（数据不可用）时返回 NaN —— 渲染处的 f() 会显示
    '—' 而非误导性的 0（如本车未上报充电 AC/DC kWh 或再生能量）。"""
    return s.sum() if s.notna().any() else float("nan")


def _counter_recup(tr, reg, version):
    """周期内再生能量总量（kWh），取自 raw_telematics 的**累积再生计数器**（全覆盖、口径正确）。

    替代 xlsx 稀疏的 `Recuperation Energy` 列（覆盖常 <50%、低估）。对每个有效行驶段在
    [Start, End] 端点插值差分（与 data_analysis_workspace/energy_breakdown 同口径，复用版本化的
    `jolt_toolkit.analysis` 计数器机器）。返回 (total_kwh, n_covered, n_total)；无 raw_telematics、
    无该计数器（如 Scania/Mercedes/柴油）、或导入失败时返回 None → 调用方回退 xlsx 列。
    """
    raw_dir = PROJECT / "excel_report_database" / version / reg / "raw_telematics"
    if not raw_dir.is_dir():
        return None
    try:
        from jolt_toolkit.analysis import COL_RECUP, build_interp, delta, to_utc
    except Exception:
        return None
    st = tr["st"].dropna()
    et = tr["et"].dropna()
    if st.empty or et.empty:
        return None
    # 只读周期跨度内（±1 天缓冲）的 raw 文件，避免读全历史（某些车有数百个日文件）
    lo = (st.min() - pd.Timedelta(days=1)).normalize()
    hi = (et.max() + pd.Timedelta(days=1)).normalize()
    raws = []
    for p in sorted(raw_dir.glob("raw_*.csv")):
        m = re.search(r"raw_(\d{4}-\d{2}-\d{2})", p.name)
        if m and lo <= pd.Timestamp(m.group(1)) <= hi:
            raws.append(p)
    if not raws:
        return None
    need = {"eventDatetime", COL_RECUP}
    try:
        tel = pd.concat([pd.read_csv(p, dtype=str, usecols=lambda c: c in need) for p in raws],
                        ignore_index=True)
        interp = build_interp(tel, COL_RECUP)
    except Exception:
        return None
    if interp is None:  # 该车无再生计数器
        return None
    tot, ncov, ntot = 0.0, 0, 0
    for s, e in zip(tr["st"], tr["et"]):
        if pd.isna(s) or pd.isna(e):
            continue
        ntot += 1
        d = delta(interp, to_utc(s), to_utc(e))
        if pd.notna(d) and d >= 0:  # 跳过越界(NaN)与计数器复位(负)
            tot += d
            ncov += 1
    return (tot, ncov, ntot) if ntot else None


def _outlier_trimmed_mean(s):
    """IQR(1.5×) 剔除离群后的均值；返回 (mean, n_kept, n_total)。有效值 < 4 个则不剔除。"""
    x = pd.to_numeric(s, errors="coerce").dropna()
    n = len(x)
    if n < 4:
        return (float(x.mean()) if n else float("nan")), n, n
    q1, q3 = x.quantile(0.25), x.quantile(0.75)
    iqr = q3 - q1
    kept = x[(x >= q1 - 1.5 * iqr) & (x <= q3 + 1.5 * iqr)]
    return float(kept.mean()), len(kept), n


def _gvm_cluster_split(mass_t):
    """轻/重载分界阈值：取逐段 GVM(t) 概率密度（高斯 KDE）在**两个最高密度峰之间的谷**。

    重卡毛重常呈空载/满载多峰；密度谷比 2-means 的方差均衡中点更贴合「视觉上的簇边界」
    —— 当一簇样本远多于另一簇时（如多数行程满载、少数空载），2-means 会把界线拉向大簇、
    把大簇边缘点错划进小簇，故弃用。样本过少 / 无展度 / 单峰时退回中位数二分。
    返回单一阈值：GVM ≤ 阈值为轻簇、> 为重簇。
    """
    x = np.sort(np.asarray(mass_t, dtype=float))
    x = x[np.isfinite(x)]
    if len(x) < 8 or np.ptp(x) == 0:
        return float(np.median(x)) if len(x) else float("nan")
    try:
        grid = np.linspace(x.min(), x.max(), 400)
        y = gaussian_kde(x)(grid)
        peaks, _ = find_peaks(y)
        if len(peaks) >= 2:
            # 取密度最高的两个峰，谷 = 两峰之间密度最低点
            p_lo, p_hi = sorted(sorted(peaks, key=lambda i: y[i])[-2:])
            valley = p_lo + int(np.argmin(y[p_lo:p_hi + 1]))
            return float(grid[valley])
    except Exception:
        pass
    return float(np.median(x))  # 单峰 / KDE 失败：中位数二分


def _compute_load_points(reg, tr):
    """Resolve the unladen / laden / full-laden reference masses + the unladen and laden ("dense")
    operating masks used by the page-2 conclusion and the temperature plot.

    This combines **data + judgement** (not pure clustering). Modes, by priority:

    - **Band mode** (``briefing_vehicle_specs.json`` ``unladen_band_t`` = [lo, hi], optional
      ``laden_min_t``): for an artic whose lightest GVM cluster is the *bobtail* tractor (e.g.
      ~12 t), not the real unladen mass. Set by AI judgement of the vehicle configuration and
      grounded in the observed distribution: unladen = the data points in [lo, hi) (tractor +
      empty trailer); laden = GVM ≥ laden_min (default hi); bobtail (< lo) is excluded.
    - **Single-group** (``SINGLE_GROUP_REGS``): laden = GVM > threshold; no unladen point.
    - **Legacy tertile** (``LEGACY_TERTILE_REGS``): unladen = lightest tertile, laden = heaviest.
    - **Default**: KDE density-valley split; laden = denser cluster, unladen = lighter cluster.

    Masses are the **median GVM of the data points** in each mask (so they track the data);
    ``unladen_mass_t`` may still pin the unladen marker explicitly. Returns the masks (tr-indexed)
    and the band thresholds (or None) for the verification workbook.
    """
    gvw_t = tr["mass"] / 1000.0
    spec = BRIEFING_SPECS.get(reg, {})
    band = spec.get("unladen_band_t")
    sg_thr = SINGLE_GROUP_REGS.get(reg)
    band_lo = band_hi = laden_min = None
    if band:                                     # judgement band (artic: bobtail vs unladen)
        band_lo, band_hi = float(band[0]), float(band[1])
        laden_min = float(spec.get("laden_min_t", band_hi))
        unladen_mask = (gvw_t >= band_lo) & (gvw_t < band_hi)
        dense_mask = gvw_t >= laden_min
    elif sg_thr is not None:                     # single-group: laden only
        dense_mask = gvw_t > sg_thr
        unladen_mask = pd.Series(False, index=gvw_t.index)
    elif reg in LEGACY_TERTILE_REGS:             # fixed tertiles
        loq, hiq = gvw_t.quantile(0.33), gvw_t.quantile(0.67)
        dense_mask, unladen_mask = gvw_t > hiq, gvw_t < loq
    else:                                        # default: KDE density-valley split
        split = _gvm_cluster_split(gvw_t.values)
        heavy_mask, light_mask = gvw_t > split, gvw_t <= split
        if int(heavy_mask.sum()) >= int(light_mask.sum()):
            dense_mask, unladen_mask = heavy_mask, light_mask
        else:
            dense_mask, unladen_mask = light_mask, heavy_mask
    m_la = float(gvw_t[dense_mask].median()) if dense_mask.any() else float("nan")
    ov = spec.get("unladen_mass_t")
    if ov is not None:
        m_un = float(ov)
    else:
        m_un = float(gvw_t[unladen_mask].median()) if unladen_mask.any() else float("nan")
    return dict(unladen=m_un, laden=m_la, full=FULL_LADEN_T,
                unladen_mask=unladen_mask, dense_mask=dense_mask,
                band_lo=band_lo, band_hi=band_hi, laden_min=laden_min)


def _add_load_markers(ax, lp, predict, x_data_max):
    """Add unladen / laden / full-laden vertical dashed lines + labels and a dashed extension
    of the fitted curve from the observed data max out to the full-laden mass.

    ``predict(mass) -> y`` evaluates the fitted model (linear for EP, reciprocal for Range).
    """
    lo, hi = ax.get_ylim()
    rng = hi - lo
    # Stagger the labels vertically so adjacent markers never overlap regardless of spacing:
    # sort by mass and alternate a high/low level. Lowest mass (Unladen) lands on the high level
    # ("above"); the labels sit in the lower, emptier band (EP/Range rise with mass).
    marks = [(mt, lab, col) for mt, lab, col in
             [(lp["unladen"], "Unladen", "#3a3f55"),
              (lp["laden"], "Laden", "#3a3f55"),
              (lp["full"], "Full", "#c0392b")]
             if mt is not None and np.isfinite(mt)]
    marks.sort(key=lambda m: m[0])
    levels = [0.17, 0.045]
    for i, (mt, lab, col) in enumerate(marks):
        ax.axvline(mt, ls=(0, (4, 3)), color=col, lw=1.4, alpha=0.85, zorder=3)
        ax.text(mt, lo + rng * levels[i % 2], f"{lab}\n{mt:.0f} t", ha="center", va="bottom",
                fontsize=14, color=col, linespacing=0.95, zorder=6,
                bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.78))
    if np.isfinite(x_data_max) and lp["full"] > x_data_max:
        xe = np.linspace(x_data_max, lp["full"], 40)
        ax.plot(xe, predict(xe), ls="--", color=OEM_BLUE, lw=1.6, alpha=0.9, zorder=4)


def _resolve_operator(reg, period):
    """运营方：先查 company_assignment.simple；轮换车（round_robin）则按报告期匹配日期段
    —— 优先取**报告期末日**所在段，其次取与报告期**有重叠**的段，皆无则回退车牌。"""
    ca = PLOT_CFG.get("company_assignment", {})
    if ca.get("simple", {}).get(reg):
        return ca["simple"][reg]
    segs = ca.get("round_robin", {}).get(reg, [])
    d0, d1 = period.split("_")
    for seg in segs:  # 期末日落在该段内（轮换车通常整期属同一家）
        if seg.get("date_start", "0") <= d1 <= seg.get("date_end", "99999999"):
            return seg["company"]
    for seg in segs:  # 退而求其次：报告期与该段有重叠
        if seg.get("date_start", "0") <= d1 and d0 <= seg.get("date_end", "99999999"):
            return seg["company"]
    return reg


def _coords(series):
    """从 '(lat, lon)' 字符串解析坐标，返回 (lat[], lon[])。"""
    lats, lons = [], []
    for v in series.dropna():
        m = re.findall(r"-?\d+\.?\d*", str(v))
        if len(m) >= 2:
            lats.append(float(m[0])); lons.append(float(m[1]))
    return np.array(lats), np.array(lons)


# ---- HERE 真实底图（Web Mercator 像素配准）----

def _load_here_key():
    """从仓库根 .env 读取 HERE_API_KEY（其次取环境变量）；没有则返回 None。"""
    env = PROJECT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("HERE_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"") or None
    return os.environ.get("HERE_API_KEY")


def _merc_x(lon):
    """Longitude -> Web Mercator world fraction [0,1]."""
    return (np.asarray(lon, dtype=float) + 180.0) / 360.0


def _merc_y(lat):
    """Latitude -> Web Mercator world fraction [0,1] (y grows southwards)."""
    s = np.sin(np.radians(np.asarray(lat, dtype=float)))
    return 0.5 - np.log((1.0 + s) / (1.0 - s)) / (4.0 * np.pi)


def _ll_to_px(lat, lon, clat, clon, zoom, w, h):
    """(lat, lon) -> pixel coords on a w*h HERE map centred at (clat, clon)/zoom."""
    world = 256.0 * (2.0 ** zoom)
    x = (_merc_x(lon) - _merc_x(clon)) * world + w / 2.0
    y = (_merc_y(lat) - _merc_y(clat)) * world + h / 2.0
    return x, y


def _fit_center_zoom(lats, lons, w, h, pad=0.15):
    """Centre + Web-Mercator zoom so all points (plus *pad* margin) fit in w*h px."""
    xf, yf = _merc_x(lons), _merc_y(lats)
    x0, x1 = float(xf.min()), float(xf.max())
    y0, y1 = float(yf.min()), float(yf.max())
    dx = max(x1 - x0, 1e-7); dy = max(y1 - y0, 1e-7)
    x0 -= dx * pad; x1 += dx * pad; y0 -= dy * pad; y1 += dy * pad
    zoom = min(math.log2(w / (256.0 * (x1 - x0))), math.log2(h / (256.0 * (y1 - y0))))
    zoom = max(3.0, min(zoom, 17.0))
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    clon = cx * 360.0 - 180.0
    clat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * cy))))
    return clat, clon, zoom, cx, cy


def _fetch_here_basemap(lats, lons, w, h, key):
    """拉取一张盖住所有点（含 15% 边距）的 HERE 静态底图（lite.day，带地名）。

    Returns (png_path, center_lat, center_lon, zoom); raises on network/API failure.
    Images are cached under cache/ keyed by (center, zoom, size) so re-runs are offline.
    """
    clat, clon, zoom, _, _ = _fit_center_zoom(lats, lons, w, h)
    zoom = round(zoom, 2)
    cache = WORKSPACE / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    tag = hashlib.md5(f"{clat:.5f},{clon:.5f},{zoom},{w}x{h}".encode()).hexdigest()[:10]
    out = cache / f"here_{tag}.png"
    if not out.exists():
        url = (f"https://image.maps.hereapi.com/mia/v3/base/mc/"
               f"center:{clat:.5f},{clon:.5f};zoom={zoom}/{w}x{h}/png8"
               f"?apiKey={key}&style=lite.day")
        with urllib.request.urlopen(url, timeout=25) as resp:
            data = resp.read()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError("HERE Map Image API returned a non-PNG response")
        out.write_bytes(data)
    return out, clat, clon, zoom


CARTO_TILE = "https://basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}@2x.png"


def _fetch_carto_basemap(lats, lons, w, h):
    """匿名版底图：CARTO light_nolabels（OSM 数据，**无地名标注**），瓦片拼接后裁切。

    与 HERE 版同一坐标约定（centre/zoom 的 Web Mercator 像素配准，_ll_to_px 通用）。
    @2x 瓦片（512 px/瓦片）在 tile-zoom z_t 下等效 zoom = z_t + 1。
    Returns (png_path, center_lat, center_lon, zoom_eff); cached under cache/.
    """
    import io

    from PIL import Image

    clat, clon, z_star, cx, cy = _fit_center_zoom(lats, lons, w, h)
    z_t = max(2, int(math.floor(z_star)) - 1)  # 保证 zoom_eff = z_t+1 <= z_star，bbox 必能装下
    zoom_eff = z_t + 1
    world = 256.0 * (2 ** zoom_eff)
    x0, y0 = cx * world - w / 2.0, cy * world - h / 2.0

    cache = WORKSPACE / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    tag = hashlib.md5(f"carto,{clat:.5f},{clon:.5f},{zoom_eff},{w}x{h}".encode()).hexdigest()[:10]
    out = cache / f"carto_{tag}.png"
    if not out.exists():
        ts = 512  # @2x tile size in zoom_eff pixel space
        xt0, xt1 = int(x0 // ts), int((x0 + w - 1) // ts)
        yt0, yt1 = int(y0 // ts), int((y0 + h - 1) // ts)
        mosaic = Image.new("RGB", ((xt1 - xt0 + 1) * ts, (yt1 - yt0 + 1) * ts), "#eef2f6")
        n_side = 2 ** z_t
        for xt in range(xt0, xt1 + 1):
            for yt in range(yt0, yt1 + 1):
                if not 0 <= yt < n_side:
                    continue  # beyond the poles: keep background fill
                url = CARTO_TILE.format(z=z_t, x=xt % n_side, y=yt)
                req = urllib.request.Request(url, headers={"User-Agent": "JOLT-briefing/1.0"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    tile = Image.open(io.BytesIO(resp.read())).convert("RGB")
                mosaic.paste(tile, ((xt - xt0) * ts, (yt - yt0) * ts))
        ox, oy = int(round(x0 - xt0 * ts)), int(round(y0 - yt0 * ts))
        mosaic.crop((ox, oy, ox + w, oy + h)).save(out)
    return out, clat, clon, zoom_eff


def _scatter_fit(ax, x, y, color=OEM_BLUE, unit=""):
    """JOLT 风格：散点 + 线性趋势线（无图例 / 无 ±1σ 阴影带）。

    拟合的斜率 / R² / σ 仍返回给调用方用于结论文字，但**不画进图里**（合作方要求图面只
    保留散点与趋势线）。``unit`` 参数保留以兼容调用方签名（现已不在图例中使用）。
    """
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    ax.scatter(x, y, s=9, color=color, alpha=0.35, edgecolors="none")
    # 需 ≥3 点且 x/y 各有方差才能拟合：否则（如某列数据缺失/全为占位 0）polyfit 的
    # Vandermonde 矩阵退化会抛 LinAlgError —— 此时只画散点、跳过拟合，不让整张图崩。
    if len(x) >= 3 and np.ptp(x) > 0 and np.ptp(y) > 0:
        m, b = np.polyfit(x, y, 1)
        xs = np.linspace(x.min(), x.max(), 100)
        ys = m * xs + b
        resid = y - (m * x + b)
        sigma = float(resid.std())
        ss_res = float((resid ** 2).sum()); ss_tot = float(((y - y.mean()) ** 2).sum())
        r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
        ax.plot(xs, ys, color=color, lw=1.7)
        return m, b, sigma, r2, len(x)
    return None


def recip_model(x, k, a, c):
    """Reciprocal model for range vs GVM: range = c / (k*x + a).

    Physically: EP rises ~linearly with mass (k*x + a), and range = capacity / EP,
    so range follows the reciprocal of a linear function of GVM.
    """
    return c / (k * x + a)


def _save(fig, path, top=None, box=None):
    # 不用 bbox_inches="tight"：保持 PNG 纵横比 == figsize，便于精确贴合槽位、消除留白。
    # box：固定坐标区位置（三张散点图共用 SCATTER_AXBOX）→ 不论 y 轴刻度位数多少，
    #      绘图框像素始终一致，避免 Range 图（"250/500" 三位刻度）被 tight_layout 挤小、
    #      固定磅值字号相对显大而与 EP-vs-GVM / EP-vs-temp 视觉不一致。
    # top：tight_layout 后再压低坐标区顶边，给锚定在坐标区上方的图例留出专用空间
    # （图表标题不画在 PNG 里，由 HTML 模板的 .chart-panel__title 渲染，避免大字号被图宽截断）。
    if box is not None:
        fig.subplots_adjust(**box)
    else:
        fig.tight_layout(pad=0.5)
        if top is not None:
            fig.subplots_adjust(top=top)
    fig.savefig(path, facecolor="white")
    plt.close(fig)


def _finish_scatter(ax):
    """散点图收尾：y 刻度按**有效位数自适应**——位数越多字号越小（≥3 位缩一档，
    如 Range 的 250/500），极宽刻度（≥4 位）再竖排旋转——使各散点图都能落进同一
    左边距、绘图框对齐又不裁切。EP（一位刻度）保持基准字号。"""
    lo, hi = ax.get_ylim()
    yt = [t for t in ax.get_yticks() if lo - 1e-9 <= t <= hi + 1e-9]
    digits = max((len(f"{t:.0f}") for t in yt), default=1)
    if digits >= 3:
        ax.tick_params(axis="y", labelsize=plt.rcParams["ytick.labelsize"] - 3)
    if digits >= 4:
        ax.tick_params(axis="y", labelrotation=90)


def build_charts(tr, ch, outdir, reg, cb, here_key=None, cap_kwh=None, anon=False,
                 rel="figures", load_pts=None):
    # 文件名带 run token 即可破坏 Chrome 缓存；旧图 best-effort 清理
    # （不用 rmtree —— OneDrive 目录可能被占用导致 WinError 5）
    outdir.mkdir(parents=True, exist_ok=True)
    for old in outdir.glob("*.png"):
        try:
            old.unlink()
        except OSError:
            pass
    charts, stats = {}, {}
    SQ = 4.6  # square figures (1:1) for the 2x2 page-2 grid — easier to read trends
    lp = load_pts or {}
    def name(stem):
        return f"{stem}_{cb}.png"

    # 1) EP vs GVM (EP axis fixed 0–3, GVM axis GVM_XLIM). Adds unladen/laden vertical markers
    #    and a dashed extension of the linear fit out to FULL_LADEN_T.
    gvw_t = tr["mass"].values / 1000.0
    fig, ax = plt.subplots(figsize=(SQ, SQ))
    r = _scatter_fit(ax, gvw_t, tr["ep"].values, unit=" /t")
    ax.set_xlabel("Gross Vehicle Mass (t)"); ax.set_ylabel("EP (kWh/km)")
    ax.set_ylim(EP_MIN, EP_MAX); ax.set_yticks([0, 1, 2, 3])
    ax.set_xlim(*GVM_XLIM); ax.set_xticks(GVM_XTICKS)
    if r:
        m, b, sigma, r2, _ = r
        stats["gvm_slope"], stats["gvm_intercept"], stats["gvm_sigma"], stats["gvm_r2"] = m, b, sigma, r2
        if lp:
            _add_load_markers(ax, lp, lambda xx: m * xx + b, float(np.nanmax(gvw_t)))
    _finish_scatter(ax)
    _save(fig, outdir / name("ep_gvm"), box=SCATTER_AXBOX); charts["gvm"] = f"{rel}/{name('ep_gvm')}"

    # 1b) Range vs GVM: projected full-charge range = effective capacity / per-trip EP
    #     (needs vehicles.json capacity). Reciprocal-model fit; same unladen/laden markers +
    #     dashed extension of the reciprocal curve to FULL_LADEN_T.
    if cap_kwh:
        rng = cap_kwh / tr["ep"].values
        fig, ax = plt.subplots(figsize=(SQ, SQ))
        mask = np.isfinite(gvw_t) & np.isfinite(rng)
        x, y = gvw_t[mask], rng[mask]
        ax.scatter(x, y, s=9, color=OEM_BLUE, alpha=0.35, edgecolors="none")
        fitted = False
        if len(x) >= 3 and np.ptp(x) > 0 and np.ptp(y) > 0:
            try:
                (rk, ra, rc), _ = curve_fit(recip_model, x, y,
                                            p0=[0.03, 0.3, float(cap_kwh)], maxfev=20000)
                fitted = True
            except (RuntimeError, ValueError):
                fitted = False
        if fitted:
            # 模型对 (k,a,c) 同乘缩放不变（尺度自由度）：归一化钉 c = 电池容量，
            # 此时 k·x+a 即 EP(kWh/km) 的线性拟合，方程对读者有物理含义
            scale = float(cap_kwh) / rc
            rk, ra, rc = rk * scale, ra * scale, rc * scale
            xs = np.linspace(x.min(), x.max(), 200)
            ys = recip_model(xs, rk, ra, rc)
            resid = y - recip_model(x, rk, ra, rc)
            sigma = float(resid.std())
            ss_res = float((resid ** 2).sum()); ss_tot = float(((y - y.mean()) ** 2).sum())
            r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
            ax.plot(xs, ys, color=OEM_BLUE, lw=1.7)
            stats["range_fit"] = (rk, ra, rc, r2); stats["range_sigma"] = sigma
        ax.set_xlabel("Gross Vehicle Mass (t)"); ax.set_ylabel("Range (km)")
        ax.set_ylim(0, np.nanmax(rng) * 1.05)
        ax.set_xlim(*GVM_XLIM); ax.set_xticks(GVM_XTICKS)
        if fitted and lp:
            _add_load_markers(ax, lp, lambda xx: recip_model(xx, rk, ra, rc), float(x.max()))
        _finish_scatter(ax)
        _save(fig, outdir / name("range_gvm"), box=SCATTER_AXBOX)
        charts["range"] = f"{rel}/{name('range_gvm')}"

    # 2) EP vs ambient temperature — restricted to the dense (laden) cluster so mass is held
    #    roughly constant: a control-variable view of the temperature effect.
    dmask = lp.get("dense_mask")
    td = tr[dmask] if dmask is not None else tr
    fig, ax = plt.subplots(figsize=(SQ, SQ))
    r = _scatter_fit(ax, td["temp"].values, td["ep"].values, unit=" /°C")
    ax.set_xlabel("Ambient Temperature (°C)"); ax.set_ylabel("EP (kWh/km)")
    ax.set_ylim(EP_MIN, EP_MAX); ax.set_yticks([0, 1, 2, 3])
    ax.set_xlim(*TEMP_XLIM); ax.set_xticks(TEMP_XTICKS)
    _finish_scatter(ax)
    _save(fig, outdir / name("ep_temp"), box=SCATTER_AXBOX); charts["temp"] = f"{rel}/{name('ep_temp')}"
    if r:
        (stats["temp_slope"], stats["temp_intercept"], stats["temp_sigma"],
         stats["temp_r2"], stats["temp_n"]) = r

    # 3) Charging start SoC histogram (square)
    fig, ax = plt.subplots(figsize=(SQ, SQ))
    ssoc = ch["ssoc"].dropna().values
    ax.hist(ssoc, bins=range(0, 101, 10), color=OEM_BLUE, alpha=0.85, edgecolor="white")
    ax.set_xlabel("Charging Start SoC (%)"); ax.set_ylabel("Sessions")
    ax.set_xlim(0, 100); ax.set_ylim(bottom=0); ax.set_xticks(range(0, 101, 20))
    _save(fig, outdir / name("soc_hist"), box=SCATTER_AXBOX); charts["soc"] = f"{rel}/{name('soc_hist')}"

    # 路线图：命名版用 HERE 真实底图（lite.day，带地名）；匿名版用 CARTO light_nolabels
    # （保留线和点、无地名——SteerCo 匿名化要求）；失败/无 key 退回无底图示意。
    olat, olon = _coords(tr["Origin (Lat, Lon)"]); dlat, dlon = _coords(tr["Destination (Lat, Lon)"])
    n = min(len(olat), len(dlat))
    basemap, attrib = None, None
    if n:
        try:
            all_lat = np.concatenate([olat[:n], dlat[:n]])
            all_lon = np.concatenate([olon[:n], dlon[:n]])
            if anon:
                basemap = _fetch_carto_basemap(all_lat, all_lon, MAP_PX_W, MAP_PX_H)
                attrib = "© OpenStreetMap © CARTO"
            elif here_key:
                basemap = _fetch_here_basemap(all_lat, all_lon, MAP_PX_W, MAP_PX_H, here_key)
                attrib = "map © HERE"
        except Exception as exc:
            print(f"  [map] 底图获取失败（{exc}），退回无底图示意")
            basemap, attrib = None, None
    if basemap:
        map_png, clat, clon, zoom = basemap
        fig = plt.figure(figsize=(MAP_PX_W / 200.0, MAP_PX_H / 200.0))
        ax = fig.add_axes([0, 0, 1, 1])  # full-bleed: 底图铺满整张 PNG
        ax.imshow(plt.imread(map_png), extent=[0, MAP_PX_W, MAP_PX_H, 0])
        # 起讫点不作区分：统一样式、无图例
        ox, oy = _ll_to_px(olat[:n], olon[:n], clat, clon, zoom, MAP_PX_W, MAP_PX_H)
        dx, dy = _ll_to_px(dlat[:n], dlon[:n], clat, clon, zoom, MAP_PX_W, MAP_PX_H)
        for i in range(n):
            ax.plot([ox[i], dx[i]], [oy[i], dy[i]], color=OEM_BLUE, lw=1.0, alpha=0.3)
        ax.scatter(np.concatenate([ox, dx]), np.concatenate([oy, dy]), s=24,
                   color="#e74c3c", alpha=0.9, edgecolors="white", linewidths=0.5, zorder=5)
        ax.set_xlim(0, MAP_PX_W); ax.set_ylim(MAP_PX_H, 0)
        ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
        for sp in ax.spines.values():
            sp.set_edgecolor("#c7ccda")
        fig.savefig(outdir / name("route_map"), dpi=200)
        plt.close(fig)
    else:
        fig, ax = plt.subplots(figsize=(3.7, 2.66))
        fig.patch.set_facecolor("#eef2f6"); ax.set_facecolor("#eef2f6")
        for i in range(n):
            ax.plot([olon[i], dlon[i]], [olat[i], dlat[i]], color=OEM_BLUE, lw=0.7, alpha=0.18)
        # 起讫点不作区分：统一样式、无图例
        ax.scatter(np.concatenate([olon, dlon]), np.concatenate([olat, dlat]), s=14,
                   color="#e74c3c", alpha=0.55, edgecolors="none")
        ax.set_xticks([]); ax.set_yticks([]); ax.margins(0.18)
        for sp in ax.spines.values():
            sp.set_edgecolor("#c7ccda")
        _save(fig, outdir / name("route_map"))
    charts["map"] = f"{rel}/{name('route_map')}"
    charts["map_attrib"] = attrib  # None => 无底图示意（caption 显示 "indicative"）

    return charts, stats


def _parse_period(period):
    """'YYYYMMDD_YYYYMMDD' -> (start_ts, end_ts) at midnight (end = last *included* day)."""
    a, b = period.split("_")
    return pd.Timestamp(a), pd.Timestamp(b)


def _resolve_xlsx(rdir, reg, period, finetuned):
    """Locate the source xlsx for a briefing period (precondition relaxed).

    Either an xlsx for the *exact* period exists, OR an xlsx whose ``[start, end]``
    range *covers* the requested window exists. Exact match wins (no subsetting);
    otherwise the **tightest** covering report is used and its legs are later subset
    to the window in :func:`compute`.

    Returns ``(path, subset_to_window)``. Raises ``FileNotFoundError`` if neither
    an exact-period report nor a covering one is present.
    """
    # 1) exact period — finetuned preferred (when requested), then base
    suffix = "_finetuned" if finetuned else ""
    for cand in (rdir / f"jolt_report_{reg}_{period}{suffix}.xlsx",
                 rdir / f"jolt_report_{reg}_{period}.xlsx"):
        if cand.exists():
            return cand, False
    # 2) covering fallback — tightest [start,end] that contains the window
    tgt_s, tgt_e = _parse_period(period)
    pat = re.compile(rf"^jolt_report_{re.escape(reg)}_(\d{{8}})_(\d{{8}})(_finetuned)?\.xlsx$")
    covering = []  # (span_days, kind_rank, path)
    for p in rdir.glob(f"jolt_report_{reg}_*.xlsx"):
        m = pat.match(p.name)
        if not m:
            continue
        cs, ce = _parse_period(f"{m.group(1)}_{m.group(2)}")
        if cs <= tgt_s and ce >= tgt_e:
            is_ft = bool(m.group(3))
            kind_rank = 0 if is_ft == finetuned else 1  # honour finetuned preference
            covering.append(((ce - cs).days, kind_rank, p))
    if covering:
        covering.sort(key=lambda t: (t[0], t[1]))  # tightest span, then preferred kind
        return covering[0][2], True
    raise FileNotFoundError(
        f"No xlsx for {reg} {period} under {rdir} — neither an exact-period report "
        f"nor one whose [start,end] covers the window. Run /generate-excel-report first.")


def compute(reg, period, version, finetuned):
    rdir = PROJECT / "excel_report_database" / version / reg
    xlsx, subset = _resolve_xlsx(rdir, reg, period, finetuned)
    df = pd.read_excel(xlsx)
    tr = df[df["Leg Type"].isin(DRIVE)].copy()
    ch = df[df["Leg Type"].isin(CHARGE)].copy()
    for c, col in [("d", "Distance (km)"), ("ep", "Energy Performance (kWh/km)"),
                   ("ec", "Energy Change (kWh)"), ("temp", "Average Temperature (C)"),
                   ("mass", "Vehicle Mass (kg)"), ("recup", "Recuperation Energy (kWh)")]:
        tr[c] = num(tr[col])
    # 有效 trip 过滤：里程 < MIN_TRIP_KM（或里程缺失）的行驶段不计入任何分析与运营周期
    # （极短/残段，EP 不可靠）。须在统计前剔除：OPERATING PERIOD、活跃天数、KPI、散点均基于有效 trip。
    n_before = len(tr)
    tr = tr[tr["d"] >= MIN_TRIP_KM].copy()
    if len(tr) < n_before:
        print(f"  [Trip 过滤] 剔除 {n_before - len(tr)} 个里程 < {MIN_TRIP_KM} km（或缺失）的行驶段")
    # EP 超出 [EP_CLEAN_MIN, EP_CLEAN_MAX] 视为不合理数据，剔除（散点/拟合/点评统计均不计）
    bad = (tr["ep"] < EP_CLEAN_MIN) | (tr["ep"] > EP_CLEAN_MAX)
    tr.loc[bad, "ep"] = np.nan
    if bad.sum():
        print(f"  [EP 清洗] 剔除 {int(bad.sum())} 个超出 [{EP_CLEAN_MIN}, {EP_CLEAN_MAX}] 的 EP 值")
    tr["st"] = pd.to_datetime(tr["Start Time (UTC)"], errors="coerce")
    tr["et"] = pd.to_datetime(tr["End Time (UTC)"], errors="coerce")
    tr["date"] = tr["st"].dt.date
    ch["ssoc"] = num(ch["Start SOC (%)"]); ch["esoc"] = num(ch["End SOC (%)"])
    ch["ac"] = num(ch["Energy Charged AC (kWh)"]); ch["dc"] = num(ch["Energy Charged DC (kWh)"])
    ch["st"] = pd.to_datetime(ch["Start Time (UTC)"], errors="coerce")
    if subset:
        # 选用覆盖周期的更宽报告时，按 Start Time 把行程/充电裁剪到目标窗口（含止日整天）。
        tgt_s, tgt_e = _parse_period(period)
        win_lo = tgt_s
        win_hi = tgt_e + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        n_tr0, n_ch0 = len(tr), len(ch)
        tr = tr[(tr["st"] >= win_lo) & (tr["st"] <= win_hi)].copy()
        ch = ch[(ch["st"] >= win_lo) & (ch["st"] <= win_hi)].copy()
        print(f"  [covering] 选用覆盖周期报告 {xlsx.name}，裁剪到窗口 {period}："
              f"trips {n_tr0}->{len(tr)}, charges {n_ch0}->{len(ch)}")
    return df, tr, ch, xlsx, subset


def median_time(times):
    mins = times.dropna().dt.hour * 60 + times.dropna().dt.minute
    if mins.empty:
        return "—"
    m = int(mins.median())
    return f"{m // 60:02d}:{m % 60:02d}"


# ---- 人工核实（human-in-the-loop verification）----

def _cell(x):
    """pandas value -> openpyxl-writable cell value (NaN/NaT -> None, tz stripped)."""
    if x is None or (isinstance(x, float) and math.isnan(x)) or pd.isna(x):
        return None
    if isinstance(x, pd.Timestamp):
        return x.tz_localize(None).to_pydatetime() if x.tzinfo else x.to_pydatetime()
    return x


def build_verification_workbook(path, tr, ch, v):
    """Write the human-verification workbook (verification_<REG>_<period>.xlsx).

    Two INDEPENDENT computation paths: this script (pandas) produced the briefing
    values; the workbook recomputes each of them with native Excel formulas over
    the raw legs copied into the Trips/Charges/Daily sheets. Any discrepancy shows
    up as FAIL. The reviewer checks FAILs, spot-checks PASSes and the MANUAL rows,
    and records the outcome in the Verified by / Date / Notes columns.
    """
    from openpyxl import Workbook
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    bold = Font(bold=True)
    head_fill = PatternFill("solid", start_color="E8EAF6")

    # ---- Trips sheet (valid driving legs: distance ≥ MIN_TRIP_KM, EP cleaned to [EP_CLEAN_MIN, EP_CLEAN_MAX]) ----
    ws = wb.active
    ws.title = "Trips"
    ws.append(["Date", "Start", "End", "Distance_km", "EnergyChange_kWh",
               "EP_kWhkm_cleaned", "GVM_t", "Temp_C", "Recup_kWh", "Range_km",
               "", "EffCap_kWh"])
    cap = v.get("cap_kwh")
    for _, r in tr.iterrows():
        ws.append([_cell(r["date"]), _cell(r["st"]), _cell(r["et"]), _cell(r["d"]),
                   _cell(r["ec"]), _cell(r["ep"]),
                   _cell(r["mass"] / 1000.0 if pd.notna(r["mass"]) else None),
                   _cell(r["temp"]), _cell(r["recup"]), None])
    tn = len(tr) + 1  # last data row
    ws["L2"] = cap if cap else None
    if cap:
        for i in range(2, tn + 1):
            ws.cell(row=i, column=10).value = f'=IF($F{i}="","",$L$2/$F{i})'
    for c in ws[1]:
        c.font = bold; c.fill = head_fill
    ws.freeze_panes = "A2"

    # ---- Charges sheet ----
    wc = wb.create_sheet("Charges")
    wc.append(["Start", "StartSOC_pct", "EndSOC_pct", "AC_kWh", "DC_kWh"])
    ch_st = pd.to_datetime(ch["Start Time (UTC)"], errors="coerce")
    for (_, r), st_val in zip(ch.iterrows(), ch_st):
        wc.append([_cell(st_val), _cell(r["ssoc"]), _cell(r["esoc"]),
                   _cell(r["ac"]), _cell(r["dc"])])
    cn = len(ch) + 1
    for c in wc[1]:
        c.font = bold; c.fill = head_fill
    wc.freeze_panes = "A2"

    # ---- Daily sheet (unique dates as values; per-day sums as Excel formulas) ----
    wd = wb.create_sheet("Daily")
    wd.append(["Date", "Distance_km", "TractionEnergy_kWh"])
    dates = sorted(d for d in tr["date"].dropna().unique())
    for i, d in enumerate(dates, start=2):
        wd.cell(row=i, column=1).value = d
        wd.cell(row=i, column=2).value = f"=SUMIF(Trips!$A$2:$A${tn},A{i},Trips!$D$2:$D${tn})"
        wd.cell(row=i, column=3).value = f"=SUMPRODUCT((Trips!$A$2:$A${tn}=A{i})*ABS(Trips!$E$2:$E${tn}))"
    dn = len(dates) + 1
    for c in wd[1]:
        c.font = bold; c.fill = head_fill

    # ---- Audit sheet ----
    wa = wb.create_sheet("Audit", 0)
    wa["A1"] = f"Verification — {v['reg']} {v['period']} (pipeline {v['version']}, source: {v['fname']})"
    wa["A1"].font = Font(bold=True, size=13)
    wa["A2"] = ("Each briefing number below is recomputed with native Excel formulas over the raw legs "
                "(Trips/Charges/Daily sheets) — an independent path from the generator. Review every FAIL, "
                "spot-check PASS and MANUAL rows, fill in the sign-off columns, then regenerate with "
                '--final --verified-by "<name>".')
    wa["A2"].alignment = Alignment(wrap_text=True)
    wa.merge_cells("A2:K2")

    tr_f, tr_g, tr_h = f"Trips!$F$2:$F${tn}", f"Trips!$G$2:$G${tn}", f"Trips!$H$2:$H${tn}"
    rows = [
        ("Page 1 · Summary", "Active days", v["ndays"],
         f"=COUNTA(Daily!$A$2:$A${dn})", 0.5,
         "Distinct dates with ≥1 driving leg", "Start Time (UTC) → date"),
        ("Page 1 · Summary", "Driving legs", v["n_tr"],
         f'=COUNTIFS({tr_f},"<>",{tr_g},"<>")', 0.5,
         "Analysed driving legs = legs with valid EP & GVM (matches the chart n; "
         "excludes EP-cleaned outliers)", "Leg Type / EP / GVM"),
        ("Page 1 · Summary", "Charging sessions", v["n_ch"],
         f"=ROWS(Charges!$A$2:$A${cn})", 0.5, "Count of charging legs (Leg Type ∈ CHARGE)", "Leg Type"),
        ("Page 1 · Summary", "Mean GVM (t) — computed as MEDIAN", v["gvw_med"],
         f"=MEDIAN(Trips!$G$2:$G${tn})", 0.05,
         "⚠ Labelled 'Mean GVM' on page 1 but computed as the MEDIAN of per-leg GVM", "Vehicle Mass (kg)/1000"),
        ("Page 1 · Timeline", "Trips per day", v["trips_per_day"],
         f'=COUNTIFS({tr_f},"<>",{tr_g},"<>")/COUNTA(Daily!$A$2:$A${dn})', 0.05,
         "Analysed driving legs (EP & GVM present) ÷ active days", "—"),
        ("Page 1 · Timeline", "Daily average distance (km)", v["daily_avg_km"],
         f"=AVERAGE(Daily!$B$2:$B${dn})", 0.5, "Mean of per-day distance sums", "Distance (km)"),
        ("Page 1 · Timeline", "Median first departure (hh:mm)", None, "manual", None,
         f"Briefing shows ≈ {v['med_dep']} — spot-check per-day minima of Trips!B", "Start Time (UTC)"),
        ("Page 1 · Timeline", "Median last arrival (hh:mm)", None, "manual", None,
         f"Briefing shows ≈ {v['med_arr']} — spot-check per-day maxima of Trips!C", "End Time (UTC)"),
        ("Page 1 · Performance", "Total distance (km)", v["tot_km"],
         f"=SUM(Trips!$D$2:$D${tn})", 0.5, "Sum over driving legs", "Distance (km)"),
        ("Page 1 · Performance", "Max daily distance (km)", v["daily_max_km"],
         f"=MAX(Daily!$B$2:$B${dn})", 0.5, "Max of per-day distance sums", "Distance (km)"),
        ("Page 1 · Performance", "Total energy used (kWh)", v["tot_e"],
         f"=SUMPRODUCT(ABS(Trips!$E$2:$E${tn}))", 0.5, "Σ|energy change| over driving legs", "Energy Change (kWh)"),
        ("Page 1 · Performance", "Mean energy performance (kWh/km)", v["mean_ep"],
         f"=SUMPRODUCT(ABS(Trips!$E$2:$E${tn}))/SUM(Trips!$D$2:$D${tn})", 0.005,
         "Total energy ÷ total distance (NOT mean of per-leg EP)", "—"),
        ("Page 1 · Performance", "Energy recuperated (kWh)", v["recup"],
         ("manual" if v["recup_src"] == "counter" else f"=SUM(Trips!$I$2:$I${tn})"),
         (None if v["recup_src"] == "counter" else 0.5),
         (f"Counter-based: Σ raw_telematics recuperation counter over {v['recup_cov']}/{v['recup_tot']} "
          f"legs (full coverage; NOT the sparse xlsx column). Sparse xlsx-column SUM for comparison: "
          f"=SUM(Trips!$I$2:$I${tn})"
          if v["recup_src"] == "counter"
          else f"Σ recuperation; only {v['recup_cov']}/{v['recup_tot']} legs have a value (known undercount)"),
         "raw_telematics recuperation counter" if v["recup_src"] == "counter" else "Recuperation Energy (kWh)"),
        ("Page 1 · Performance", "Regen recovery (% of energy used)", v.get("recup_pct"),
         ("manual" if v["recup_src"] == "counter"
          else f"=SUM(Trips!$I$2:$I${tn})/SUMPRODUCT(ABS(Trips!$E$2:$E${tn}))*100"),
         (None if v["recup_src"] == "counter" else 0.5),
         ("Energy recuperated ÷ total energy used × 100 (recup is counter-based, audited above; "
          "ratio = that kWh ÷ Σ|energy change|)"
          if v["recup_src"] == "counter"
          else "Σ recuperation ÷ Σ|energy change| × 100"),
         "—"),
        ("Page 1 · Charging", "Total energy charged (kWh)", v["tot_ch"],
         f"=SUM(Charges!$D$2:$D${cn})+SUM(Charges!$E$2:$E${cn})", 0.5, "AC + DC", "Energy Charged AC/DC (kWh)"),
        ("Page 1 · Charging", "AC charged (kWh)", v["ac"],
         f"=SUM(Charges!$D$2:$D${cn})", 0.5, "", "Energy Charged AC (kWh)"),
        ("Page 1 · Charging", "DC charged (kWh)", v["dc"],
         f"=SUM(Charges!$E$2:$E${cn})", 0.5, "", "Energy Charged DC (kWh)"),
        ("Page 1 · Charging", "Mean start SoC (%)", v["mean_ssoc"],
         f"=AVERAGE(Charges!$B$2:$B${cn})", 0.5, "", "Start SOC (%)"),
        ("Page 1 · Charging", "Mean end SoC (%)", v["mean_esoc"],
         f"=AVERAGE(Charges!$C$2:$C${cn})", 0.5, "", "End SOC (%)"),
        ("Page 2 · EP vs GVM", "GVM min (t)", v["gvm_min"],
         f"=MIN(Trips!$G$2:$G${tn})", 0.05, "", "Vehicle Mass (kg)/1000"),
        ("Page 2 · EP vs GVM", "GVM max (t)", v["gvm_max"],
         f"=MAX(Trips!$G$2:$G${tn})", 0.05, "", ""),
        ("Page 2 · EP vs GVM", "n trips (EP & GVM present)", v["n_pairs"],
         f'=COUNTIFS({tr_f},"<>",{tr_g},"<>")', 0.5, "Legs with both cleaned EP and GVM", ""),
        ("Page 2 · EP vs GVM", "Fit slope (kWh/km per t)", v["gvm_slope"],
         f"=SLOPE({tr_f},{tr_g})", 0.0005, "Least-squares linear fit (blank EP rows excluded)", ""),
        ("Page 2 · EP vs GVM", "Fit R²", v["gvm_r2"],
         f"=RSQ({tr_f},{tr_g})", 0.005, "", ""),
    ]
    # 轻/重载分组（按车辆区分，三选一）：SINGLE_GROUP_REGS 只给 GVM>阈值的离群剔除均值（单组）；
    # LEGACY_TERTILE_REGS 用 33%/67% 三分位（Excel PERCENTILE 独立复算，AVERAGEIFS 引用 D 列）；
    # 其余用 GVM 密度谷聚类阈值（KDE 无 Excel 单公式 → manual 行，AVERAGEIFS 引用 C 列）。
    # 各分支同时备好 range_rows（续航对照行），供下方 if cap 段拼接。
    if v.get("band_lo") is not None:
        lo, hi, lm, mu = v["band_lo"], v["band_hi"], v["laden_min"], v["mass_unladen"]
        rows += [
            ("Page 2 · Conclusion", f"Unladen EP @ {mu:g} t (kWh/km)", v["ep_unladen"],
             f"=SLOPE({tr_f},{tr_g})*{mu:g}+INTERCEPT({tr_f},{tr_g})", 0.02,
             f"EP-vs-GVM trend at the unladen mass — the unladen band ({lo:g}-{hi:g} t = tractor + "
             f"empty trailer) is sparse, so the trend is used; bobtail (< {lo:g} t) excluded", ""),
            ("Page 2 · Conclusion", f"Laden EP, GVM >= {lm:g} t (kWh/km)", v["ep_laden_pt"],
             f'=AVERAGEIFS({tr_f},{tr_g},">={lm:g}")', 0.01, "Mean EP of laden operation", ""),
        ]
        range_rows = ([("Page 2 · Conclusion", f"Unladen range @ {mu:g} t (km)", v["rng_unladen"],
                        f"={cap:g}/(SLOPE({tr_f},{tr_g})*{mu:g}+INTERCEPT({tr_f},{tr_g}))", 6.0,
                        "capacity / unladen trend EP", ""),
                       ("Page 2 · Conclusion", f"Laden range, GVM >= {lm:g} t (km)", v["rng_laden_pt"],
                        f'={cap:g}/AVERAGEIFS({tr_f},{tr_g},">={lm:g}")', 3.0,
                        "capacity / laden mean EP", "")] if cap else [])
    elif v["reg"] in SINGLE_GROUP_REGS:
        thr = SINGLE_GROUP_REGS[v["reg"]]
        rows += [
            ("Page 2 · EP vs GVM", f"n trips GVM > {thr:g} t (EP present)", v["n_laden_tot"],
             f'=COUNTIFS({tr_g},">{thr:g}",{tr_f},"<>")', 0.5, "Laden trips with cleaned EP (before IQR trim)", ""),
            ("Page 2 · EP vs GVM", f"Avg EP, laden GVM>{thr:g}t (IQR-trimmed)", v["ep_laden"],
             "manual", None,
             f"IQR(1.5x)-trimmed mean of EP for GVM > {thr:g} t (n={v['n_laden']} of {v['n_laden_tot']}); "
             f'untrimmed cross-check =AVERAGEIFS({tr_f},{tr_g},">{thr:g}")', ""),
        ]
        ep_laden_row = 6 + len(rows)
        range_rows = ([("Page 2 · Range vs GVM", f"Avg range, laden GVM>{thr:g}t (km)", v["rng_laden"],
                        f'={cap:g}/$C${ep_laden_row}', 1.0, "capacity / trimmed laden mean EP", "")]
                      if cap else [])
    elif v["reg"] in LEGACY_TERTILE_REGS:
        rows += [
            ("Page 2 · EP vs GVM", "GVM 33% quantile (t)", v["gvw_lo"],
             f"=PERCENTILE({tr_g},0.33)", 0.05, "Same interpolation as pandas quantile()", ""),
            ("Page 2 · EP vs GVM", "GVM 67% quantile (t)", v["gvw_hi"],
             f"=PERCENTILE({tr_g},0.67)", 0.05, "", ""),
        ]
        q67_row = 6 + len(rows); q33_row = q67_row - 1
        lo_crit, hi_crit = f'"<"&$D${q33_row}', f'">"&$D${q67_row}'
        rows += [
            ("Page 2 · EP vs GVM", "Average EP, lightest 1/3 (kWh/km)", v["ep_light"],
             f'=AVERAGEIFS({tr_f},{tr_g},{lo_crit})', 0.005, "Mean EP where GVM < 33% quantile", ""),
            ("Page 2 · EP vs GVM", "Average EP, heaviest 1/3 (kWh/km)", v["ep_heavy"],
             f'=AVERAGEIFS({tr_f},{tr_g},{hi_crit})', 0.005, "Mean EP where GVM > 67% quantile", ""),
        ]
        range_rows = ([("Page 2 · Range vs GVM", "Average range, lighter group (km)", v["rng_light"],
                        f'={cap:g}/AVERAGEIFS({tr_f},{tr_g},{lo_crit})', 1.0,
                        "capacity / cluster mean EP (monotonic with EP, never inverts)", ""),
                       ("Page 2 · Range vs GVM", "Average range, heavier group (km)", v["rng_heavy"],
                        f'={cap:g}/AVERAGEIFS({tr_f},{tr_g},{hi_crit})', 1.0, "", "")] if cap else [])
    else:
        rows += [
            ("Page 2 · EP vs GVM", "GVM light/heavy cluster split (t)", v["gvw_split"],
             "manual", None,
             "Data-driven KDE density-valley split of per-trip GVM (not a fixed quantile); "
             "compare with the visible gap / bimodality in the EP-vs-GVM scatter", ""),
        ]
        split_row = 6 + len(rows)
        lo_crit, hi_crit = f'"<="&$C${split_row}', f'">"&$C${split_row}'
        rows += [
            ("Page 2 · EP vs GVM", "Average EP, lighter cluster (kWh/km)", v["ep_light"],
             f'=AVERAGEIFS({tr_f},{tr_g},{lo_crit})', 0.005, "Mean EP where GVM <= cluster split", ""),
            ("Page 2 · EP vs GVM", "Average EP, heavier cluster (kWh/km)", v["ep_heavy"],
             f'=AVERAGEIFS({tr_f},{tr_g},{hi_crit})', 0.005, "Mean EP where GVM > cluster split", ""),
        ]
        range_rows = ([("Page 2 · Range vs GVM", "Average range, lighter group (km)", v["rng_light"],
                        f'={cap:g}/AVERAGEIFS({tr_f},{tr_g},{lo_crit})', 1.0,
                        "capacity / cluster mean EP (monotonic with EP, never inverts)", ""),
                       ("Page 2 · Range vs GVM", "Average range, heavier group (km)", v["rng_heavy"],
                        f'={cap:g}/AVERAGEIFS({tr_f},{tr_g},{hi_crit})', 1.0, "", "")] if cap else [])
    if cap:
        rows += [
            ("Page 2 · Range vs GVM", "Effective battery capacity (kWh)", None, "manual", None,
             f"Briefing uses {cap:g} kWh — confirm against src/jolt_toolkit/configs/vehicles.json "
             "(effective_capacity_kwh) / SRF", "vehicles.json"),
            ("Page 2 · Range vs GVM", "Reciprocal fit k (≈, kWh/km per t)", v["rng_k"],
             f"=SLOPE({tr_f},{tr_g})", max(abs(v["rng_k"]) * 0.15, 0.003),
             "APPROX check: reciprocal fit minimises range-space error; linearised equivalent "
             "is the EP slope (expect agreement within ~15%)", ""),
            ("Page 2 · Range vs GVM", "Reciprocal fit a (≈, kWh/km)", v["rng_a"],
             f"=INTERCEPT({tr_f},{tr_g})", max(abs(v["rng_a"]) * 0.15, 0.05), "APPROX (see above)", ""),
            ("Page 2 · Range vs GVM", "Reciprocal fit R²", None, "manual", None,
             f"Briefing shows {v['rng_r2']:.2f} — nonlinear fit, no native Excel equivalent; "
             "compare with the chart legend", ""),
        ] + range_rows
    rows += [
        ("Page 2 · Conclusion", "Fully-laden EP @42 t (kWh/km)", v["ep_full"],
         f"=SLOPE({tr_f},{tr_g})*{FULL_LADEN_T:g}+INTERCEPT({tr_f},{tr_g})", 0.02,
         "EP-vs-GVM linear fit extrapolated to the full-laden reference mass", "—"),
    ] + ([("Page 2 · Conclusion", "Fully-laden range @42 t (km)", v["rng_full"],
           f"={cap:g}/(SLOPE({tr_f},{tr_g})*{FULL_LADEN_T:g}+INTERCEPT({tr_f},{tr_g}))", 5.0,
           "capacity / (EP fit @42 t)", "")] if cap else []) + [
        ("Page 2 · Conclusion", "Unladen reference mass (t)", v["mass_unladen"],
         "manual", None,
         "Lighter-cluster median GVM (or briefing_vehicle_specs.json override) — cross-check "
         "against the model kerb mass", "Vehicle Mass (kg)/1000"),
        ("Page 2 · Conclusion", "Laden reference mass (t)", v["mass_laden"],
         "manual", None, "Median GVM of the denser (laden) cluster", "Vehicle Mass (kg)/1000"),
        ("Page 2 · EP vs temperature (laden)", "Fit slope (kWh/km per °C)", v["temp_slope"],
         "manual", None,
         f"Laden-cluster subset (mass controlled), n={v['temp_n']}, "
         f"{v['temp_min']:.0f}–{v['temp_max']:.0f} °C — compare with the chart legend "
         "(KDE subset, no native Excel filter)", "Average Temperature (C)"),
        ("Page 2 · EP vs temperature (laden)", "Fit R²", v["temp_r2"],
         "manual", None, "Laden-cluster subset — compare with the chart legend", ""),
        ("Page 2 · Charging SoC", "Sessions starting <40% SoC (%)", v["pct_low"],
         f'=COUNTIF(Charges!$B$2:$B${cn},"<40")/ROWS(Charges!$B$2:$B${cn})*100', 0.5,
         "Denominator = all sessions (matches generator: blank SoC counts as not-<40)", "Start SOC (%)"),
        ("Page 2 · Charging SoC", "Median start SoC (%)", v["med_start"],
         f"=MEDIAN(Charges!$B$2:$B${cn})", 0.5, "", ""),
        ("Page 2 · Charging SoC", "DC share of charged energy (%)", v["dc_share"],
         f"=SUM(Charges!$E$2:$E${cn})/(SUM(Charges!$D$2:$D${cn})+SUM(Charges!$E$2:$E${cn}))*100",
         0.5, "", ""),
    ]

    header = ["Section", "Item", "Briefing value", "Recomputed (Excel)", "Tolerance",
              "Status", "Definition / filter", "Source column(s)", "Verified by", "Date", "Notes"]
    wa.append([])  # row 3 spacer
    wa.append([])  # row 4
    wa.append([])  # row 5
    wa.append(header)  # row 6
    hr = 6
    for c in wa[hr]:
        c.font = bold; c.fill = head_fill
    for i, (sec, item, val, formula, tol, defn, src) in enumerate(rows, start=hr + 1):
        wa.cell(row=i, column=1).value = sec
        wa.cell(row=i, column=2).value = item
        wa.cell(row=i, column=3).value = None if val is None or pd.isna(val) else float(val)
        wa.cell(row=i, column=4).value = formula
        wa.cell(row=i, column=5).value = tol
        if formula == "manual":
            wa.cell(row=i, column=6).value = "CHECK MANUALLY"
        else:
            wa.cell(row=i, column=6).value = (
                f'=IF(ABS($C{i}-$D{i})<=$E{i},"PASS","FAIL")')
        wa.cell(row=i, column=7).value = defn
        wa.cell(row=i, column=8).value = src
    last = hr + len(rows)
    wa.conditional_formatting.add(
        f"F{hr + 1}:F{last}",
        CellIsRule(operator="equal", formula=['"FAIL"'],
                   fill=PatternFill("solid", start_color="FFC7CE"), font=Font(color="9C0006", bold=True)))
    wa.conditional_formatting.add(
        f"F{hr + 1}:F{last}",
        CellIsRule(operator="equal", formula=['"PASS"'], font=Font(color="1E7B33", bold=True)))
    wa.conditional_formatting.add(
        f"F{hr + 1}:F{last}",
        CellIsRule(operator="equal", formula=['"CHECK MANUALLY"'],
                   fill=PatternFill("solid", start_color="FFF2CC")))
    widths = {"A": 24, "B": 36, "C": 15, "D": 22, "E": 10, "F": 17, "G": 58, "H": 26,
              "I": 14, "J": 12, "K": 28}
    for col, w in widths.items():
        wa.column_dimensions[col].width = w
    wa.freeze_panes = f"A{hr + 1}"

    wb.save(path)
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reg", default="YK73WFN")
    ap.add_argument("--period", default="20250301_20250601")
    ap.add_argument("--version", default="2.2.3")
    ap.add_argument("--base", action="store_true", help="用非 finetuned 的 base xlsx")
    ap.add_argument("--anon", action="store_true",
                    help="匿名化展示版：隐去运营方与车牌、底图换无地名 CARTO，"
                         "产物为 report_anon_<period>.*（与命名版共存）")
    args = ap.parse_args()

    df, tr, ch, xlsx_path, covering_src = compute(args.reg, args.period, args.version,
                                                  finetuned=not args.base)
    fname = xlsx_path.name
    spec = PLOT_CFG["vehicle_specs"].get(args.reg, {})
    operator = _resolve_operator(args.reg, args.period)
    make = spec.get("make", "")
    model = VEHICLES.get(args.reg, {}).get("model", "")
    vehicle_model = (f"{make} {model}".strip() or make)  # 真实型号取自 vehicles.json

    # 运营周期 = 有效 trip 的真实跨度（首发车 → 末到达）；**输出（文件夹/PDF/xlsx/标签）一律按此命名**，
    # 与页头 OPERATING PERIOD 对齐，而非名义报告周期 args.period（后者仅用于 compute 定位 xlsx）。
    # 无有效 trip 时回退 args.period。
    d0, d1 = tr["st"].min(), tr["et"].max()
    op_period = (f"{d0:%Y%m%d}_{d1:%Y%m%d}" if pd.notna(d0) and pd.notna(d1) else args.period)

    outdir = WORKSPACE / "output" / f"{args.reg}_{op_period}"
    fig_rel = "figures_anon" if args.anon else "figures"  # 匿名版独立图目录，与命名版产物共存
    fig_dir = outdir / fig_rel
    cb = int(time.time())  # run token：图片文件名缓存破坏
    cap_kwh = VEHICLES.get(args.reg, {}).get("effective_capacity_kwh")
    load_pts = _compute_load_points(args.reg, tr)
    charts, st = build_charts(tr, ch, fig_dir, args.reg, cb,
                              here_key=_load_here_key(), cap_kwh=cap_kwh,
                              anon=args.anon, rel=fig_rel, load_pts=load_pts)

    # ---- 真实 KPI ----
    daily_km = tr.dropna(subset=["date"]).groupby("date")["d"].sum()
    tot_km = tr["d"].sum(); ndays = tr["date"].nunique()
    # 分析用的有效行驶段数 = 图表 n（EP & GVM 齐全）。头部 "Driving Legs"、trips/day 一律用它，
    # 与第 2 页散点/拟合的 n 保持一致（len(tr) 还含 EP 被清洗的离群段，距离/能耗总量仍按全部段）。
    n_legs = int((tr["ep"].notna() & tr["mass"].notna()).sum())
    tot_e = tr["ec"].abs().sum(); mean_ep = tot_e / tot_km if tot_km else float("nan")
    # 再生能量：优先用 raw_telematics 累积计数器（全覆盖、口径正确，约占能耗 ~20%）；无 raw /
    # 无该计数器的车（Scania/Mercedes/柴油）回退 xlsx 列（其值本就稀疏/缺 → 显示 '—'）。
    _cr = _counter_recup(tr, args.reg, args.version)
    if _cr is not None:
        recup, recup_cov, recup_tot, recup_src = _cr[0], _cr[1], _cr[2], "counter"
    else:
        recup = _sum_or_na(tr["recup"]); recup_cov = int(tr["recup"].notna().sum())
        recup_tot = len(tr); recup_src = "xlsx"
    # 制动能量回收比例 = 周期内再生回收能量 ÷ 总用电量(净放电)×100；与项目既有口径一致
    # (≈20% for the counter-based Volvos)。无再生数据(recup NaN)或零能耗 → NaN(summary 略过该条)。
    recup_pct = recup / tot_e * 100 if (pd.notna(recup) and tot_e) else float("nan")
    ac, dc = _sum_or_na(ch["ac"]), _sum_or_na(ch["dc"])
    tot_ch = np.nansum([ac, dc]) if (pd.notna(ac) or pd.notna(dc)) else float("nan")
    med_start = ch["ssoc"].median(); mean_end = ch["esoc"].mean()
    pct_low = (ch["ssoc"] < 40).mean() * 100
    dc_share = dc / tot_ch * 100 if (pd.notna(tot_ch) and tot_ch) else float("nan")
    gvw_med = tr["mass"].median() / 1000.0
    period_label = (f"{d0.day} {d0:%b} – {d1.day} {d1:%b %Y}" if pd.notna(d0) else args.period)
    # 轻/重载对照：默认 GVM 密度谷聚类自适应分界；LEGACY_TERTILE_REGS 内的车保留固定 1/3 三分位
    # 旧表述（合作方风格基准）。冷/暖对照；满电续航投影（容量/EP）。
    gvw_t = tr["mass"] / 1000.0
    legacy_tertile = args.reg in LEGACY_TERTILE_REGS
    if legacy_tertile:
        gvw_lo, gvw_hi = gvw_t.quantile(0.33), gvw_t.quantile(0.67)
        gvw_split = float("nan")
        light_m = gvw_t < gvw_lo; heavy_m = gvw_t > gvw_hi  # 旧法剔除中间 1/3
        light_label, heavy_label = "Lightest 1/3 of trips", "Heaviest 1/3 of trips"
        light_cond = f"For GVM < {gvw_lo:.0f} t"; heavy_cond = f"For GVM > {gvw_hi:.0f} t"
    else:
        gvw_lo = gvw_hi = float("nan")
        gvw_split = _gvm_cluster_split(gvw_t.values)
        light_m = gvw_t <= gvw_split; heavy_m = gvw_t > gvw_split
        light_label, heavy_label = "Lighter GVM cluster", "Heavier GVM cluster"
        light_cond = f"For GVM < {gvw_split:.0f} t"; heavy_cond = f"For GVM ≥ {gvw_split:.0f} t"
    ep_light = tr.loc[light_m, "ep"].mean(); ep_heavy = tr.loc[heavy_m, "ep"].mean()
    ep_cold = tr.loc[tr["temp"] < 5, "ep"].mean(); ep_warm = tr.loc[tr["temp"] > 15, "ep"].mean()
    if cap_kwh:
        # 簇续航 = 容量 ÷ **簇平均 EP**（不是「逐段续航 cap/EP 的均值」）。后者被低 EP 段（高续航）
        # 主导、且与上方 EP 点评不自洽 → 会出现「重簇续航 > 轻簇」的反直觉反转；前者随簇 EP 单调，
        # 必与 EP 点评一致（EP 低 → 续航高）。
        rng_light = cap_kwh / ep_light if pd.notna(ep_light) else float("nan")
        rng_heavy = cap_kwh / ep_heavy if pd.notna(ep_heavy) else float("nan")

    # 单组模式（SINGLE_GROUP_REGS，如 YN25RSY）：不分轻/重簇，只给 GVM > 阈值的离群剔除均值
    sg_thr = SINGLE_GROUP_REGS.get(args.reg)
    single_group = sg_thr is not None
    ep_laden = rng_laden = float("nan"); n_laden = n_laden_tot = 0
    if single_group:
        ep_laden, n_laden, n_laden_tot = _outlier_trimmed_mean(tr.loc[gvw_t > sg_thr, "ep"])
        rng_laden = (cap_kwh / ep_laden) if (cap_kwh and pd.notna(ep_laden)) else float("nan")

    # ---- Load-point conclusion values: unladen / laden / fully-laden EP & range (±1σ) ----
    # Unladen / laden EP = mean of the ACTUAL data points in each operating mask (chosen by
    # judgement band or clustering — see _compute_load_points); ± = within-mask std. Fully-laden
    # (42 t) has no data → EP-vs-GVM linear fit extrapolated; ± = fit residual σ.
    dense_mask = load_pts["dense_mask"]; unladen_mask = load_pts["unladen_mask"]
    m_un, m_la, m_full = load_pts["unladen"], load_pts["laden"], load_pts["full"]
    gvm_slope = st.get("gvm_slope", float("nan")); gvm_icpt = st.get("gvm_intercept", float("nan"))
    gvm_sig = st.get("gvm_sigma", float("nan"))
    is_band = load_pts.get("band_lo") is not None

    def _ep_fit(mt):
        return (gvm_slope * mt + gvm_icpt) if (pd.notna(gvm_slope) and pd.notna(mt)) else float("nan")

    # Laden EP = mean EP of the actual laden data points (ample data); ± = within-cluster std.
    if single_group:
        ep_la = ep_laden; ep_la_sd = float(tr.loc[gvw_t > sg_thr, "ep"].std()); n_la = int(n_laden)
    else:
        ep_la = float(tr.loc[dense_mask, "ep"].mean()); ep_la_sd = float(tr.loc[dense_mask, "ep"].std())
        n_la = int((dense_mask & tr["ep"].notna()).sum())
    # Unladen EP: in band mode the tractor+empty-trailer band is sparse (a handful of trips,
    # easily skewed) → read the EP-vs-GVM trend at the unladen mass instead; otherwise use the
    # lighter-cluster mean. Fully-laden (42 t) is always the trend extrapolated.
    # ± = fit residual σ for trend values, within-cluster std for means.
    has_un = (not single_group) and bool(unladen_mask.any())
    n_un = int((unladen_mask & tr["ep"].notna()).sum()) if has_un else 0
    if not has_un:
        ep_un = float("nan"); ep_un_sd = float("nan")
    elif is_band:
        ep_un = _ep_fit(m_un); ep_un_sd = gvm_sig
    else:
        ep_un = float(tr.loc[unladen_mask, "ep"].mean()); ep_un_sd = float(tr.loc[unladen_mask, "ep"].std())
    ep_fl = _ep_fit(m_full); ep_fl_sd = gvm_sig

    def _rng_pair(ep, ep_sd):
        if not cap_kwh or pd.isna(ep) or ep <= 0:
            return float("nan"), float("nan")
        r = cap_kwh / ep
        return r, (r * ep_sd / ep if pd.notna(ep_sd) else float("nan"))
    rng_un, rng_un_sd = _rng_pair(ep_un, ep_un_sd)
    rng_la, rng_la_sd = _rng_pair(ep_la, ep_la_sd)
    rng_fl, rng_fl_sd = _rng_pair(ep_fl, ep_fl_sd)

    dt = tr[dense_mask]
    td_min, td_max = dt["temp"].min(), dt["temp"].max()
    laden_gvm = dt["mass"] / 1000.0
    laden_gmin, laden_gmax = laden_gvm.min(), laden_gvm.max()
    t_slope = st.get("temp_slope", float("nan")); t_r2 = st.get("temp_r2", float("nan"))
    t_n = int(st.get("temp_n", 0)); t_per10 = t_slope * 10 if pd.notna(t_slope) else float("nan")
    temp_sens = ("largely temperature-insensitive over this range"
                 if (pd.notna(t_per10) and abs(t_per10) < 0.10) else
                 "moderately temperature-sensitive"
                 if (pd.notna(t_per10) and abs(t_per10) < 0.25) else
                 "noticeably temperature-sensitive" if pd.notna(t_per10) else
                 "of undetermined temperature sensitivity")

    # plain-English number formatters (NaN -> "—"; ± omitted when unknown)
    _pep = lambda v: "—" if pd.isna(v) else f"{v:.2f}"
    _psd = lambda v: "" if pd.isna(v) else f" (±{v:.2f})"
    _prn = lambda v: "—" if pd.isna(v) else f"{v:,.0f}"
    _prsd = lambda v: "" if pd.isna(v) else f" (±{v:,.0f})"
    conclusion_points = []
    if has_un and pd.notna(m_un):
        conclusion_points.append(
            f"Unladen (~{m_un:.0f} t): energy performance {_pep(ep_un)}{_psd(ep_un_sd)} kWh/km, "
            f"range {_prn(rng_un)}{_prsd(rng_un_sd)} km.")
    conclusion_points.append(
        f"Laden (~{m_la:.0f} t): energy performance {_pep(ep_la)}{_psd(ep_la_sd)} kWh/km, "
        f"range {_prn(rng_la)}{_prsd(rng_la_sd)} km.")
    conclusion_points.append(
        f"Fully laden ({m_full:.0f} t, projected to rated GVW): energy performance "
        f"{_pep(ep_fl)}{_psd(ep_fl_sd)} kWh/km, range {_prn(rng_fl)}{_prsd(rng_fl_sd)} km.")
    if pd.notna(gvm_slope):
        conclusion_points.append(
            f"Each extra tonne of load adds ~{gvm_slope:.2f} kWh/km.")
    conclusion_points.append(
        f"Temperature (laden trips, {laden_gmin:.0f}–{laden_gmax:.0f} t): energy performance changes "
        f"~{abs(t_per10):.2f} kWh/km per 10 °C colder — {temp_sens}.")

    # page-1 summary: concise plain-English takeaways for partners. Kept to a high-level overview
    # + charging behaviour + a data-availability note; the load/range/temperature detail lives on
    # page 2 (not duplicated here).
    summary_points = [
        f"Over {ndays} active days the vehicle covered {tot_km:,.0f} km "
        f"(~{daily_km.mean():.0f} km/day) using {tot_e:,.0f} kWh — averaging {mean_ep:.2f} kWh/km.",
        f"Charging: {len(ch)} sessions over the period, typically plugged in from a median "
        f"{med_start:.0f}% start SoC and charged to a mean {mean_end:.0f}%.",
    ]
    # Regenerative-braking recovery ratio (only when the vehicle reports recuperation, e.g. the
    # Volvo/Renault telematics counter); skipped where there is no regen channel (shown as "—" below).
    if pd.notna(recup_pct):
        summary_points.append(
            f"Regenerative braking recovered ~{recup:,.0f} kWh over the period — "
            f"about {recup_pct:.0f}% of the energy used.")
    _missing = []
    if pd.isna(tot_ch):
        _missing.append("charged energy (AC/DC)")
    if pd.isna(recup):
        _missing.append("energy recuperated")
    if _missing:
        summary_points.append(
            f"Data channels: {' and '.join(_missing)} are not reported by this vehicle telematics "
            f"(shown as “—”).")

    # ---- 人工核实：把简报中出现的每个数字汇成清单，写核实工作簿（Excel 公式独立复算）----
    vals = dict(
        reg=args.reg, period=op_period, version=args.version, fname=fname,
        cap_kwh=cap_kwh, ndays=ndays, n_tr=n_legs, n_ch=len(ch),
        gvw_med=gvw_med, trips_per_day=n_legs / ndays if ndays else float("nan"),
        daily_avg_km=daily_km.mean(), daily_max_km=daily_km.max(),
        med_dep=median_time(tr.groupby("date")["st"].min()),
        med_arr=median_time(tr.groupby("date")["et"].max()),
        tot_km=tot_km, tot_e=tot_e, mean_ep=mean_ep, recup=recup, recup_cov=int(recup_cov),
        recup_tot=int(recup_tot), recup_src=recup_src, recup_pct=recup_pct,
        tot_ch=tot_ch, ac=ac, dc=dc, mean_ssoc=ch["ssoc"].mean(), mean_esoc=mean_end,
        med_start=med_start, pct_low=pct_low, dc_share=dc_share,
        gvm_min=gvw_t.min(), gvm_max=gvw_t.max(),
        n_pairs=int((tr["ep"].notna() & tr["mass"].notna()).sum()),
        n_ep=int(tr["ep"].notna().sum()),
        gvm_slope=st.get("gvm_slope", float("nan")), gvm_r2=st.get("gvm_r2", float("nan")),
        gvw_split=gvw_split, gvw_lo=gvw_lo, gvw_hi=gvw_hi, ep_light=ep_light, ep_heavy=ep_heavy,
        sg_thr=sg_thr, ep_laden=ep_laden, n_laden=n_laden, n_laden_tot=n_laden_tot, rng_laden=rng_laden,
        temp_min=td_min, temp_max=td_max, temp_n=t_n,
        temp_slope=st.get("temp_slope", float("nan")), temp_r2=st.get("temp_r2", float("nan")),
        gvm_intercept=gvm_icpt, gvm_sigma=gvm_sig,
        mass_unladen=m_un, mass_laden=m_la, mass_full=m_full,
        ep_unladen=ep_un, ep_laden_pt=ep_la, ep_full=ep_fl,
        rng_unladen=rng_un, rng_laden_pt=rng_la, rng_full=rng_fl,
        band_lo=load_pts.get("band_lo"), band_hi=load_pts.get("band_hi"),
        laden_min=load_pts.get("laden_min"), n_un=n_un, n_la=n_la,
    )
    if cap_kwh and "range_fit" in st:
        vals.update(rng_k=st["range_fit"][0], rng_a=st["range_fit"][1],
                    rng_r2=st["range_fit"][3], rng_light=rng_light, rng_heavy=rng_heavy)

    verif_path, n_audit = None, 0
    if not args.anon:  # 匿名版数字与命名版一致，核实在命名版工作簿上完成
        verif_path = outdir / f"verification_{args.reg}_{op_period}.xlsx"
        try:
            n_audit = build_verification_workbook(verif_path, tr, ch, vals)
        except PermissionError:
            verif_path = verif_path.with_name(f"{verif_path.stem}_{int(time.time())}.xlsx")
            n_audit = build_verification_workbook(verif_path, tr, ch, vals)
            print(f"[verify] 原核实工作簿被占用，改写到：{verif_path.name}")

    # ---- 匿名化展示版（SteerCo）：隐去运营方与车牌；型号/数据/图保持不变 ----
    if args.anon:
        operator_disp, reg_disp = "JOLT MEMBER", ""
        analysis_sub = f"JOLT Member · {vehicle_model}"
        source_ops = source_analysis = ""  # 匿名版不显示数据来源页脚
    else:
        operator_disp, reg_disp = operator, args.reg
        analysis_sub = f"{operator} · {args.reg} · {vehicle_model}"
        source_ops = source_analysis = ""  # source footers removed per user request (2026-06-22)

    def f(v, d=0, suf=""):
        return "—" if pd.isna(v) else f"{v:,.{d}f}{suf}"

    # Page-2 2x2 chart grid (titles rendered by HTML; the daily-energy figure was removed).
    # Laden mass threshold (lower bound of the laden mask) for the temperature-chart title.
    laden_thr = (load_pts.get("laden_min") if load_pts.get("laden_min") is not None
                 else (sg_thr if single_group
                       else (gvw_hi if legacy_tertile else gvw_split)))
    laden_lbl = (f"laden, ≥ {laden_thr:.0f} t" if pd.notna(laden_thr) else "laden")
    charts_grid = [dict(title="Energy Performance vs Gross Vehicle Mass", img=charts["gvm"])]
    if charts.get("range"):
        charts_grid.append(dict(title="Projected Range vs Gross Vehicle Mass", img=charts["range"]))
    charts_grid += [
        dict(title=f"Energy Performance vs Ambient Temperature ({laden_lbl})", img=charts["temp"]),
        dict(title="Charging Start State of Charge", img=charts["soc"]),
    ]

    ctx = dict(
        reg=reg_disp, operator=operator_disp, vehicle_model=vehicle_model.upper(),
        period_label=period_label, operator_logo=operator_disp.replace("_", " "), oem_logo=make.upper(),
        timeline=[
            dict(tag="DAY START", icon=ICON_TRUCK, time=f"≈ {median_time(tr.groupby('date')['st'].min())}",
                 label="Median first departure"),
            dict(tag="", icon=ICON_CLOCK, time=f"≈ {n_legs/ndays:.1f} trips/day",
                 label=f"{daily_km.mean():.0f} km / day average"),
            dict(tag="DAY END", icon=ICON_TRUCK, time=f"≈ {median_time(tr.groupby('date')['et'].max())}",
                 label="Median last arrival"),
        ],
        operating_days=f"OPERATING PERIOD · {period_label.upper()} · {ndays} ACTIVE DAYS",
        summary=[
            dict(k="Active Days", v=f(ndays)),
            dict(k="Driving Legs", v=f(n_legs)),
            dict(k="Charging Sessions", v=f(len(ch))),
            dict(k="Mean GVM", v=f(gvw_med, 1, " t")),
        ],
        perf_title="VEHICLE PERFORMANCE",
        perf_rows=[
            dict(k="Total Distance", v=f(tot_km, 0, " km"), cls="num"),
            dict(k="Daily Avg Distance", v=f(daily_km.mean(), 0, " km"), cls="num"),
            dict(k="Max Daily Distance", v=f(daily_km.max(), 0, " km"), cls="num"),
            dict(k="Total Energy Used", v=f(tot_e, 0, " kWh"), cls="num"),
            dict(k="Mean Energy Performance", v=f(mean_ep, 2, " kWh/km"), cls="num"),
            dict(k="Energy Recuperated", v=f(recup, 0, " kWh"), cls="num pos"),
        ],
        charge_title="CHARGING SESSIONS",
        charge_rows=[
            dict(k="No. of Charging Sessions", v=f(len(ch)), cls="num"),
            dict(k="Total Energy Charged", v=f(tot_ch, 0, " kWh"), cls="num"),
            dict(k="— AC Charged", v=f(ac, 0, " kWh"), cls="num"),
            dict(k="— DC Charged", v=f(dc, 0, " kWh"), cls="num"),
            dict(k="Mean Start SoC", v=f(ch["ssoc"].mean(), 0, " %"), cls="num"),
            dict(k="Mean End SoC", v=f(mean_end, 0, " %"), cls="num"),
        ],
        map_img=charts["map"],
        map_caption=charts.get("map_attrib") or "indicative",
        source_ops=source_ops,
        summary_title="Summary",
        summary_points=summary_points,
        analysis_title="Performance Analysis",
        analysis_sub=analysis_sub,
        charts_grid=charts_grid,
        conclusion_title="Conclusions",
        conclusion_points=conclusion_points,
        source_analysis=source_analysis,
    )

    html = Template(TEMPLATE.read_text(encoding="utf-8")).render(**ctx)
    # 匿名版文件名不含车牌（便于直接转发），与命名版产物在同一目录共存
    stem = f"report_anon_{op_period}" if args.anon else f"report_{args.reg}_{op_period}"
    out_html = outdir / f"{stem}.html"
    out_html.write_text(html, encoding="utf-8")
    out_pdf = outdir / f"{stem}.pdf"
    out_pdf = html_to_pdf(out_html, out_pdf)  # 若原名被占用会返回带时间戳的新名

    # 保持输出目录清洁：自动清理生成器自己产生的历史时间戳副本（`_<unix时间戳>` 后缀，
    # 来自规范名被占用时的回退写入），使 PDF 只剩命名版与匿名版各一份最新。
    # 只匹配 10 位时间戳后缀 —— 不碰用户手动命名的其它文件。
    keep = {out_pdf.name} | ({verif_path.name} if verif_path is not None else set())
    stale = re.compile(r"_(?:\d{10})\.(?:pdf|xlsx)$")
    for p in list(outdir.glob("report*.pdf")) + list(outdir.glob("verification_*.xlsx")):
        if p.name not in keep and stale.search(p.name):
            try:
                p.unlink()
                print(f"  [clean] 删除旧时间戳副本: {p.name}")
            except OSError:
                print(f"  [clean] 旧副本被占用、暂留: {p.name}")

    # ---- 适用性审计 ----
    print("\n" + "=" * 64)
    print(f"  字段适用性审计 — {args.reg} {op_period}")
    print("=" * 64)
    print("  [真实管线数据]")
    _na = lambda v: "—" if pd.isna(v) else v  # 数据不可用打印 '—'，与简报一致
    for k, v in [("Active days", ndays), ("Driving legs", n_legs), ("Charging sessions", len(ch)),
                 ("Total distance km", round(tot_km)), ("Mean EP kWh/km", round(mean_ep, 3)),
                 ("Total energy kWh", round(tot_e)), ("Charged kWh", _na(round(tot_ch, 0) if pd.notna(tot_ch) else tot_ch)),
                 ("Recup kWh (cov %d/%d)" % (recup_cov, len(tr)), _na(round(recup, 0) if pd.notna(recup) else recup)),
                 ("Mean GVM t", round(gvw_med, 1))]:
        print(f"    ✓ {k:32s} {_na(v)}")
    print("  [N/A — 需运营方 / 商业数据，JOLT 管线不产出]")
    for k in ["Customers served", "Cargo tonnage (仅有 GVW)", "Types of goods",
              "Charging cost / rebates (£)", "CO₂ & fuel saved vs diesel (需柴油基线)",
              "Fixed daily schedule (Session 1/break/2)"]:
        print(f"    ✗ {k}")
    print(f"\n  HTML: {out_html}\n  PDF : {out_pdf}")
    if args.anon:
        print("  匿名版：运营方/车牌已隐去，底图为 CARTO 无地名版；数字与命名版一致，"
              "核实请用命名版的核实工作簿。")
    else:
        print(f"  核实工作簿: {verif_path}（{n_audit} 项审计）")
        print("  人工核实：打开核实工作簿，复核 FAIL 项、抽查 PASS 项、完成 CHECK MANUALLY 项，"
              "并填写 Verified by / Date / Notes 列存档。")


if __name__ == "__main__":
    main()
