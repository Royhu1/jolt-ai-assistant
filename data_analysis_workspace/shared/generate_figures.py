"""
generate_figures.py
===================
从已生成的 xlsx 报告中读取数据，批量绘制分析图。

独立脚本，替代原 ``jolt_toolkit.excel_plotter`` 子包。
不依赖 excel_plotter 包——直接读取 ``plot_config.json`` 并内联所有绘图逻辑。

用法：
    cd <project_root>
    PYTHONPATH=src python data_analysis_workspace/shared/generate_figures.py --out-dir <dir> [--version 2.2.8] [--anon]

输出（under the REQUIRED --out-dir; the old top-level figures/{version}/ layout is deprecated）：
    <out-dir>/named/        实名版
    <out-dir>/anon/         匿名版（需 --anon）

图表类型：
    1. per_operation    — 每个 Operation 单独的散点 + 拟合线图
    2. all_operations   — 所有 Operation 合并展示（plain / errorbar / shaded）
    3. per_oem          — 按 OEM 分组聚合（plain / errorbar / shaded）
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression
from scipy.optimize import curve_fit

# ── 项目根目录与路径设置 ──────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from jolt_toolkit.configs import get_config_path  # noqa: E402
from jolt_toolkit import __version__ as _TOOLKIT_VERSION  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# ── Style constants (mirrored in .claude/skills/plot-figure/static/core/style-contract.md) ──
FIG_W, FIG_H = 10, 6
FIG_H_SM = 3.5
DPI = 300
FS_LABEL = 14
FS_TITLE = 14
FS_TICK = 12
FS_LEGEND = 9
ALPHA_SC = 0.25       # 散点透明度
MARKER_SIZE = 10      # 散点大小
FIT_LW = 2            # 拟合线宽
FIT_ALPHA = 0.9
DASH_ALPHA = 0.55     # 延伸虚线透明度
SHADE_ALPHA = 0.15    # ±1σ 着色透明度
GRID_ALPHA = 0.3

PERF_YLIM = (0, 3)
RANGE_YLIM = (0, 900)
MASS_XLIM = (0, 45000)
PT_XLIM = (0, 35000)
MASS_CUTOFF = 42000          # dashed fit-extension target (kg): solid fit ends at the observed
                             # data max, dashed extends to here; also the 42 t mass-filter upper bound

# ── xlsx 列名 ──────────────────────────────────────────────────────────────
COL_MASS = "Vehicle Mass (kg)"
COL_PERF = "Energy Performance (kWh/km)"
COL_CAP = "Battery Capacity (kWh)"
COL_DIST = "Distance (km)"
COL_LEG_TYPE = "Leg Type"
COL_START_TIME = "Start Time (UTC)"
COL_LEG_NUM = "Leg Number"


# ── 配置加载 ──────────────────────────────────────────────────────────────
def _load_cfg(path: Path | str | None = None) -> dict:
    p = Path(path) if path else get_config_path("plot_config.json")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


# ── 拟合工具 ──────────────────────────────────────────────────────────────

def _linear_fit(x: np.ndarray, y: np.ndarray):
    """线性回归。返回 (slope, intercept, r2)。"""
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < 3:
        return None
    model = LinearRegression().fit(x.reshape(-1, 1), y)
    k = model.coef_[0]
    b = model.intercept_
    r2 = model.score(x.reshape(-1, 1), y)
    return k, b, r2


def _recip_model(x, k, a, c):
    """倒数模型：y = c / (k*x + a)"""
    return c / (k * x + a)


def _recip_fit(x: np.ndarray, y: np.ndarray):
    """倒数拟合。返回 (popt, r2) 或 None。"""
    mask = np.isfinite(x) & np.isfinite(y) & (y > 0)
    x, y = x[mask], y[mask]
    if len(x) < 5:
        return None
    try:
        inv_y = 1.0 / y
        lr = LinearRegression().fit(x.reshape(-1, 1), inv_y)
        k0 = lr.coef_[0]
        a0 = lr.intercept_
        c0 = 1.0
        popt, _ = curve_fit(_recip_model, x, y, p0=[k0, a0, c0], maxfev=10000)
        y_pred = _recip_model(x, *popt)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        return popt, r2
    except Exception:
        return None


def _binned_stats(x, y, n_bins=10):
    """对 x 分箱，返回 (bin_centers, bin_means, bin_stds)。"""
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < 5:
        return None, None, None
    bins = np.linspace(x.min(), x.max(), n_bins + 1)
    centers, means, stds = [], [], []
    for i in range(n_bins):
        m = (x >= bins[i]) & (x < bins[i + 1])
        if m.sum() >= 2:
            centers.append((bins[i] + bins[i + 1]) / 2)
            means.append(y[m].mean())
            stds.append(y[m].std())
    return np.array(centers), np.array(means), np.array(stds)


# ── 格式化工具 ──────────────────────────────────────────────────────────────

def _linear_label(name, k, b, r2, n=None):
    n_str = f" (n={n})" if n else ""
    return f"{name}{n_str}  y={k:.2e}x+{b:.2e}  (R²={r2:.3f})"


def _recip_label(name, popt, r2, n=None):
    k, a, c = popt
    n_str = f" (n={n})" if n else ""
    return f"{name}{n_str}  1/({k:.2e}x+{a:.4f})·{c:.1f}  (R²={r2:.3f})"


def _parse_report_filename(path: Path):
    """解析 jolt_report_{REG}_{YYYYMMDD}_{YYYYMMDD}.xlsx"""
    m = re.match(r"jolt_report_(\w+)_(\d{8})_(\d{8})\.xlsx$", path.name)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)


def _apply_style(ax):
    """统一坐标轴样式。"""
    ax.tick_params(labelsize=FS_TICK)
    ax.xaxis.label.set_size(FS_LABEL)
    ax.yaxis.label.set_size(FS_LABEL)
    ax.grid(True, alpha=GRID_ALPHA)
    ax.legend(fontsize=FS_LEGEND, loc="best")


# ── 主类 ─────────────────────────────────────────────────────────────────

class XlsxReportPlotter:
    """
    从 xlsx 报告数据绘制分析图。

    Args:
        config_path: plot_config.json 路径（默认 configs/plot_config.json）
    """

    def __init__(self, config_path: str | Path | None = None):
        self._cfg = _load_cfg(config_path)
        self._company_simple = self._cfg["company_assignment"]["simple"]
        self._company_rr = self._cfg["company_assignment"].get("round_robin", {})
        self._veh_specs = self._cfg["vehicle_specs"]
        self._trailer_w = self._cfg["trailer_weights_kg"]
        self._colors = self._cfg["colors"]
        self._anon_map = self._cfg["oem_anonymization"]
        self._driving_types = set(self._cfg.get("driving_leg_types", []))

    # ── 数据加载 ──────────────────────────────────────────────────────────

    def load_data(self, report_paths: list[str | Path]) -> pd.DataFrame:
        """
        从多个 xlsx 报告或文件夹加载数据并合并。

        report_paths 可以是：
        - xlsx 文件路径列表
        - 文件夹路径列表（自动扫描 jolt_report_*.xlsx）
        - 混合列表

        返回合并的 DataFrame，包含派生列 Vehicle, Make, Company, Color,
        Max Range (km), Payload+Trailer (kg)。
        """
        frames = []
        for p in report_paths:
            p = Path(p)
            if p.is_dir():
                files = sorted(p.rglob("jolt_report_*.xlsx"))
            elif p.is_file():
                files = [p]
            else:
                logger.warning("路径无效: %s", p)
                continue
            for f in files:
                df = self._read_single(f)
                if df is not None and not df.empty:
                    frames.append(df)

        if not frames:
            logger.error("未加载到任何数据")
            return pd.DataFrame()

        df = pd.concat(frames, ignore_index=True)
        logger.info("共加载 %d 行数据", len(df))
        return df

    def _read_single(self, xlsx_path: Path) -> pd.DataFrame | None:
        """读取单个 xlsx 的 Report 工作表，添加元数据列。"""
        parsed = _parse_report_filename(xlsx_path)
        if parsed is None:
            return None
        reg, ds, de = parsed

        try:
            df = pd.read_excel(xlsx_path, sheet_name="Report")
        except Exception as exc:
            logger.warning("读取失败 %s: %s", xlsx_path.name, exc)
            return None

        if COL_PERF not in df.columns or COL_MASS not in df.columns:
            return None

        df["Vehicle"] = reg
        df["Make"] = self._veh_specs.get(reg, {}).get("make", "Unknown")
        df["Company"] = self._resolve_company(reg, df)
        df["OEM"] = df["Make"].map(self._anon_map).fillna("Unknown")

        # 派生列
        eff_cap = self._veh_specs.get(reg, {}).get("effective_capacity_kwh")
        tractor_w = self._veh_specs.get(reg, {}).get("tractor_weight_kg", 0)
        trailer_w_map = {c: w for c, w in self._trailer_w.items()}

        if eff_cap and eff_cap > 0:
            perf = pd.to_numeric(df[COL_PERF], errors="coerce")
            df["Max Range (km)"] = np.where(perf > 0, eff_cap / perf, np.nan)
        else:
            df["Max Range (km)"] = np.nan

        df["Payload+Trailer (kg)"] = (
            pd.to_numeric(df[COL_MASS], errors="coerce") - tractor_w
            + df["Company"].map(trailer_w_map).fillna(0)
        )

        # 颜色
        veh_override = self._colors.get("vehicle_override", {})
        company_colors = self._colors.get("company", {})
        df["Color"] = df.apply(
            lambda r: veh_override.get(r["Vehicle"],
                      company_colors.get(r["Company"], "gray")), axis=1)
        df["OEM_Color"] = df["Make"].map(
            self._colors.get("oem_by_make", {})).fillna("gray")

        return df

    def _resolve_company(self, reg: str, df: pd.DataFrame) -> pd.Series:
        """根据简单映射或 round_robin 日期范围分配 Company。"""
        if reg in self._company_simple:
            return pd.Series(self._company_simple[reg], index=df.index)

        if reg in self._company_rr:
            rr = self._company_rr[reg]
            companies = pd.Series("Unknown", index=df.index)
            if COL_START_TIME in df.columns:
                ts = pd.to_datetime(df[COL_START_TIME], errors="coerce")
                for entry in rr:
                    ds = pd.Timestamp(entry["date_start"])
                    de = pd.Timestamp(entry["date_end"])
                    mask = (ts >= ds) & (ts <= de)
                    companies[mask] = entry["company"]
            return companies

        return pd.Series("Unknown", index=df.index)

    # ── 数据过滤 ──────────────────────────────────────────────────────────

    def _filter_driving(self, df: pd.DataFrame) -> pd.DataFrame:
        """只保留放电（行驶）段，过滤异常值。"""
        mask = df[COL_LEG_TYPE].isin(self._driving_types)
        d = df[mask].copy()
        d[COL_MASS] = pd.to_numeric(d[COL_MASS], errors="coerce")
        d[COL_PERF] = pd.to_numeric(d[COL_PERF], errors="coerce")
        d = d[(d[COL_PERF] > 0.1) & (d[COL_PERF] <= 3.0)
              & (d[COL_MASS] > 0) & (d[COL_MASS] <= 42000)]
        return d

    # ── 绘图主入口 ────────────────────────────────────────────────────────

    def plot_all(self, report_paths: list[str | Path],
                 output_dir: str | Path, *, anonymous: bool = False):
        """生成所有类型的图表。"""
        df = self.load_data(report_paths)
        if df.empty:
            return
        df = self._filter_driving(df)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        self.plot_per_operation(df, out, anonymous=anonymous)
        self.plot_all_operations(df, out, anonymous=anonymous)
        self.plot_per_oem(df, out, anonymous=anonymous)
        logger.info("全部图表已生成到 %s", out)

    # ── 1. 每个 Operation 单独图 ──────────────────────────────────────────

    def plot_per_operation(self, df: pd.DataFrame, output_dir: Path, *,
                           anonymous: bool = False):
        """为每个 Vehicle+Company 组合生成散点 + 拟合线图。"""
        sub = output_dir / "fitline_with_scatter"
        sub.mkdir(exist_ok=True)
        df["_op"] = df["Vehicle"] + "_" + df["Make"] + "_" + df["Company"]
        for op, grp in df.groupby("_op", sort=True):
            if len(grp) < 5:
                continue
            parts = op.split("_", 2)
            reg, make = parts[0], parts[1]
            company = parts[2] if len(parts) > 2 else "Unknown"
            color = grp["Color"].iloc[0]

            if anonymous:
                oem = self._anon_map.get(make, make)
                title_name = f"{oem} Vehicle"
                fname_base = f"{oem}_{company}"
                color = self._colors.get("oem_by_label", {}).get(oem, color)
            else:
                title_name = f"{reg}({make}, {company})"
                fname_base = f"{reg}_{make}_{company}"

            x_m = grp[COL_MASS].values.astype(float)
            y_p = grp[COL_PERF].values.astype(float)
            y_r = grp["Max Range (km)"].values.astype(float)
            x_pt = grp["Payload+Trailer (kg)"].values.astype(float)

            # kWhkm vs GVW
            self._plot_scatter_linear(
                x_m, y_p, color, title_name, "kWh/km vs Vehicle Total Mass",
                "Vehicle Total Mass (kg)", "Energy Performance (kWh/km)",
                MASS_XLIM, PERF_YLIM, sub / f"{fname_base}_kWhkm_vs_GVW.png",
                figsize=(FIG_W, FIG_H_SM), dash_extend_to=MASS_CUTOFF)

            # kWhkm vs Payload+Trailer
            self._plot_scatter_linear(
                x_pt, y_p, color, title_name, "kWh/km vs Payload+Trailer",
                "Payload+Trailer (kg)", "Energy Performance (kWh/km)",
                PT_XLIM, PERF_YLIM, sub / f"{fname_base}_kWhkm_vs_PayloadTrailer.png",
                figsize=(FIG_W, FIG_H_SM))

            # Range vs GVW (linear)
            self._plot_scatter_linear(
                x_m, y_r, color, title_name, "Range vs Vehicle Total Mass",
                "Vehicle Total Mass (kg)", "Max Range (km)",
                MASS_XLIM, RANGE_YLIM, sub / f"{fname_base}_Range_vs_GVW.png",
                figsize=(FIG_W, FIG_H_SM), dash_extend_to=MASS_CUTOFF)

            # Range vs GVW (reciprocal)
            self._plot_scatter_reciprocal(
                x_m, y_r, color, title_name, "Range vs Vehicle Total Mass",
                "Vehicle Total Mass (kg)", "Max Range (km)",
                MASS_XLIM, RANGE_YLIM,
                sub / f"{fname_base}_Range_vs_GVW_reciprocal.png",
                figsize=(FIG_W, FIG_H_SM), dash_extend_to=MASS_CUTOFF)

            # Range vs Payload+Trailer
            self._plot_scatter_linear(
                x_pt, y_r, color, title_name, "Range vs Payload+Trailer",
                "Payload+Trailer (kg)", "Max Range (km)",
                PT_XLIM, RANGE_YLIM,
                sub / f"{fname_base}_Range_vs_PayloadTrailer.png",
                figsize=(FIG_W, FIG_H_SM))

            self._plot_scatter_reciprocal(
                x_pt, y_r, color, title_name, "Range vs Payload+Trailer",
                "Payload+Trailer (kg)", "Max Range (km)",
                PT_XLIM, RANGE_YLIM,
                sub / f"{fname_base}_Range_vs_PayloadTrailer_reciprocal.png",
                figsize=(FIG_W, FIG_H_SM))

        df.drop(columns="_op", inplace=True, errors="ignore")
        logger.info("per_operation 图已生成")

    # ── 2. 所有 Operation 合并图 ──────────────────────────────────────────

    def plot_all_operations(self, df: pd.DataFrame, output_dir: Path, *,
                            anonymous: bool = False):
        """所有 Operation 合并展示的多变体图。"""
        prefix = "anon_all_ops" if anonymous else "all_ops"
        combos = [
            ("kWhkm_vs_GVW", COL_MASS, COL_PERF,
             "Vehicle Total Mass (kg)", "Energy Performance (kWh/km)",
             MASS_XLIM, PERF_YLIM, "linear"),
            ("kWhkm_vs_PayloadTrailer", "Payload+Trailer (kg)", COL_PERF,
             "Payload+Trailer (kg)", "Energy Performance (kWh/km)",
             PT_XLIM, PERF_YLIM, "linear"),
            ("Range_vs_GVW", COL_MASS, "Max Range (km)",
             "Vehicle Total Mass (kg)", "Max Range (km)",
             MASS_XLIM, RANGE_YLIM, "reciprocal"),
            ("Range_vs_PayloadTrailer", "Payload+Trailer (kg)", "Max Range (km)",
             "Payload+Trailer (kg)", "Max Range (km)",
             PT_XLIM, RANGE_YLIM, "reciprocal"),
        ]
        for name, xcol, ycol, xlabel, ylabel, xlim, ylim, fit_type in combos:
            _dext = MASS_CUTOFF if xcol == COL_MASS else None
            for style in ("plain", "errorbar", "shaded"):
                fname = f"{prefix}_{name}" + (f"_{style}" if style != "plain" else "")
                self._plot_multi_ops(
                    df, xcol, ycol, xlabel, ylabel, xlim, ylim,
                    fit_type, style, anonymous,
                    output_dir / f"{fname}.png",
                    title_suffix=name.replace("_", " "),
                    dash_extend_to=_dext)

            # Range 额外生成 reciprocal 和 dual 变体
            if fit_type == "reciprocal":
                self._plot_multi_ops(
                    df, xcol, ycol, xlabel, ylabel, xlim, ylim,
                    "reciprocal", "plain", anonymous,
                    output_dir / f"{prefix}_{name}_reciprocal.png",
                    title_suffix=f'{name.replace("_", " ")} (Reciprocal Fit)',
                    dash_extend_to=_dext)
                self._plot_multi_ops(
                    df, xcol, ycol, xlabel, ylabel, xlim, ylim,
                    "dual", "plain", anonymous,
                    output_dir / f"{prefix}_{name}_dual.png",
                    title_suffix=f'{name.replace("_", " ")} (Linear + Reciprocal Fit)',
                    dash_extend_to=_dext)

        logger.info("all_operations 图已生成")

    # ── 3. 按 OEM 聚合图 ──────────────────────────────────────────────────

    def plot_per_oem(self, df: pd.DataFrame, output_dir: Path, *,
                     anonymous: bool = False):
        """按 OEM 分组聚合图。"""
        prefix = "anon_oem" if anonymous else "oem"
        combos = [
            ("kWhkm_vs_GVW", COL_MASS, COL_PERF,
             "Vehicle Total Mass (kg)", "Energy Performance (kWh/km)",
             MASS_XLIM, PERF_YLIM, "linear"),
            ("kWhkm_vs_PayloadTrailer", "Payload+Trailer (kg)", COL_PERF,
             "Payload+Trailer (kg)", "Energy Performance (kWh/km)",
             PT_XLIM, PERF_YLIM, "linear"),
            ("Range_vs_GVW", COL_MASS, "Max Range (km)",
             "Vehicle Total Mass (kg)", "Max Range (km)",
             MASS_XLIM, RANGE_YLIM, "reciprocal"),
            ("Range_vs_PayloadTrailer", "Payload+Trailer (kg)", "Max Range (km)",
             "Payload+Trailer (kg)", "Max Range (km)",
             PT_XLIM, RANGE_YLIM, "reciprocal"),
        ]
        for name, xcol, ycol, xlabel, ylabel, xlim, ylim, fit_type in combos:
            _dext = MASS_CUTOFF if xcol == COL_MASS else None
            for style in ("plain", "errorbar", "shaded"):
                fname = f"{prefix}_{name}" + (f"_{style}" if style != "plain" else "")
                self._plot_oem(
                    df, xcol, ycol, xlabel, ylabel, xlim, ylim,
                    fit_type, style, anonymous,
                    output_dir / f"{fname}.png",
                    title_suffix=name.replace("_", " "),
                    dash_extend_to=_dext)

            if fit_type == "reciprocal":
                self._plot_oem(
                    df, xcol, ycol, xlabel, ylabel, xlim, ylim,
                    "dual", "plain", anonymous,
                    output_dir / f"{prefix}_{name}_dual.png",
                    title_suffix=f'{name.replace("_", " ")} (Linear + Reciprocal Fit)',
                    dash_extend_to=_dext)

        logger.info("per_oem 图已生成")

    # ── 内部绘图函数 ──────────────────────────────────────────────────────

    def _plot_scatter_linear(self, x, y, color, name, subtitle,
                              xlabel, ylabel, xlim, ylim, save_path, *,
                              figsize=(FIG_W, FIG_H),
                              dash_extend_to: float | None = None):
        """单个 operation 的散点 + 线性拟合。"""
        fig, ax = plt.subplots(figsize=figsize, dpi=DPI)
        ax.scatter(x, y, c=color, alpha=ALPHA_SC, s=MARKER_SIZE, zorder=2)
        fit = _linear_fit(x, y)
        if fit:
            k, b, r2 = fit
            xf = x[np.isfinite(x)]
            x_lo = xlim[0] or xf.min()
            x_hi = xf.max() if dash_extend_to else (xlim[1] or xf.max())
            xl = np.linspace(x_lo, x_hi, 200)
            ax.plot(xl, k * xl + b, color=color, lw=FIT_LW, alpha=FIT_ALPHA,
                    label=f"y = {k:.2e}x + {b:.2e}  (R²={r2:.3f})")
            # 虚线延伸到 dash_extend_to
            if dash_extend_to and x_hi < dash_extend_to:
                xd = np.linspace(x_hi, dash_extend_to, 50)
                ax.plot(xd, k * xd + b, color=color, lw=FIT_LW,
                        linestyle="--", alpha=DASH_ALPHA)
        ax.set(xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim)
        ax.set_title(f"{name} — {subtitle}", fontsize=FS_TITLE)
        _apply_style(ax)
        fig.tight_layout()
        fig.savefig(save_path, dpi=DPI, bbox_inches="tight")
        plt.close(fig)

    def _plot_scatter_reciprocal(self, x, y, color, name, subtitle,
                                  xlabel, ylabel, xlim, ylim, save_path, *,
                                  figsize=(FIG_W, FIG_H),
                                  dash_extend_to: float | None = None):
        """单个 operation 的散点 + 倒数拟合。"""
        fig, ax = plt.subplots(figsize=figsize, dpi=DPI)
        ax.scatter(x, y, c=color, alpha=ALPHA_SC, s=MARKER_SIZE, zorder=2)
        rfit = _recip_fit(x, y)
        if rfit:
            popt, r2 = rfit
            xf = x[np.isfinite(x)]
            x_lo = max(xlim[0], xf.min())
            x_hi = xf.max() if dash_extend_to else (xlim[1] or xf.max())
            xl = np.linspace(x_lo, x_hi, 200)
            ax.plot(xl, _recip_model(xl, *popt), color=color, lw=FIT_LW,
                    alpha=FIT_ALPHA,
                    label=_recip_label("", popt, r2).strip())
            # 虚线延伸到 dash_extend_to
            if dash_extend_to and x_hi < dash_extend_to:
                xd = np.linspace(x_hi, dash_extend_to, 50)
                ax.plot(xd, _recip_model(xd, *popt), color=color, lw=FIT_LW,
                        linestyle="--", alpha=DASH_ALPHA)
        ax.set(xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim)
        ax.set_title(f"{name} — {subtitle} (Reciprocal)", fontsize=FS_TITLE)
        _apply_style(ax)
        fig.tight_layout()
        fig.savefig(save_path, dpi=DPI, bbox_inches="tight")
        plt.close(fig)

    def _plot_multi_ops(self, df, xcol, ycol, xlabel, ylabel, xlim, ylim,
                         fit_type, style, anonymous, save_path, *,
                         title_suffix="",
                         dash_extend_to: float | None = None):
        """所有 Operations 合并图（plain/errorbar/shaded 样式）。"""
        fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)
        df["_op"] = df["Vehicle"] + "_" + df["Make"] + "_" + df["Company"]

        for op, grp in sorted(df.groupby("_op"), key=lambda t: t[0]):
            x = pd.to_numeric(grp[xcol], errors="coerce").values
            y = pd.to_numeric(grp[ycol], errors="coerce").values
            m = np.isfinite(x) & np.isfinite(y) & (y > 0)
            if m.sum() < 5:
                continue
            x, y = x[m], y[m]

            parts = op.split("_", 2)
            reg, make = parts[0], parts[1]
            company = parts[2] if len(parts) > 2 else ""
            if anonymous:
                oem = self._anon_map.get(make, make)
                lbl_name = f"{oem}"
                color = self._colors.get("oem_by_label", {}).get(oem, "gray")
            else:
                lbl_name = f"{reg}({make}, {company})"
                color = grp["Color"].iloc[0]

            x_hi = x.max() if dash_extend_to else (xlim[1] or x.max())
            xl = np.linspace(xlim[0] or x.min(), x_hi, 200)
            n = len(x)

            if fit_type in ("linear", "dual"):
                fit = _linear_fit(x, y)
                if fit:
                    k, b, r2 = fit
                    yl = k * xl + b
                    label = _linear_label(lbl_name, k, b, r2, n)
                    ax.plot(xl, yl, color=color, lw=FIT_LW, alpha=FIT_ALPHA,
                            label=label)
                    # 虚线延伸
                    if dash_extend_to and x_hi < dash_extend_to:
                        xd = np.linspace(x_hi, dash_extend_to, 50)
                        ax.plot(xd, k * xd + b, color=color, lw=FIT_LW,
                                linestyle="--", alpha=DASH_ALPHA)
                    if style == "shaded":
                        sigma = np.std(y - (k * x + b))
                        ax.fill_between(xl, yl - sigma, yl + sigma,
                                        color=color, alpha=SHADE_ALPHA, linewidth=0)
                    if style == "errorbar":
                        ax.plot(xl, yl, color=color, lw=FIT_LW, alpha=FIT_ALPHA)
                        bc, bm, bs = _binned_stats(x, y)
                        if bc is not None:
                            ax.errorbar(bc, bm, yerr=bs, fmt="o", color=color,
                                        markersize=4, capsize=3, alpha=0.7,
                                        linewidth=1)

            if fit_type in ("reciprocal", "dual"):
                rfit = _recip_fit(x, y)
                if rfit:
                    popt, r2 = rfit
                    yl = _recip_model(xl, *popt)
                    ls = "--" if fit_type == "dual" else "-"
                    lbl = _recip_label(lbl_name, popt, r2, n) if fit_type != "dual" else None
                    ax.plot(xl, yl, color=color, lw=FIT_LW, linestyle=ls,
                            alpha=DASH_ALPHA if fit_type == "dual" else FIT_ALPHA,
                            label=lbl)
                    # 虚线延伸（仅非 dual 模式；dual 模式本身已是虚线）
                    if dash_extend_to and x_hi < dash_extend_to and fit_type != "dual":
                        xd = np.linspace(x_hi, dash_extend_to, 50)
                        ax.plot(xd, _recip_model(xd, *popt), color=color,
                                lw=FIT_LW, linestyle="--", alpha=DASH_ALPHA)
                    if style == "shaded" and fit_type != "dual":
                        sigma = np.std(y - _recip_model(x, *popt))
                        ax.fill_between(xl, yl - sigma, yl + sigma,
                                        color=color, alpha=SHADE_ALPHA, linewidth=0)
                    if style == "errorbar" and fit_type != "dual":
                        bc, bm, bs = _binned_stats(x, y)
                        if bc is not None:
                            ax.errorbar(bc, bm, yerr=bs, fmt="o", color=color,
                                        markersize=4, capsize=3, alpha=0.7,
                                        linewidth=1)

        df.drop(columns="_op", inplace=True, errors="ignore")
        title = f"{ylabel} vs {xlabel}"
        if style == "errorbar":
            title += " (with Error Bars)"
        elif style == "shaded":
            title += " (with Shaded ±1σ Band)"
        elif fit_type == "dual":
            title = f"{ylabel} vs {xlabel} (Linear + Reciprocal Fit)"
        elif fit_type == "reciprocal":
            title += " (Reciprocal Fit)"

        ax.set(xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim)
        ax.set_title(title, fontsize=FS_TITLE)
        _apply_style(ax)
        fig.tight_layout()
        fig.savefig(save_path, dpi=DPI, bbox_inches="tight")
        plt.close(fig)

    def _plot_oem(self, df, xcol, ycol, xlabel, ylabel, xlim, ylim,
                   fit_type, style, anonymous, save_path, *,
                   title_suffix="",
                   dash_extend_to: float | None = None):
        """按 OEM 聚合图。"""
        fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)
        group_col = "OEM" if anonymous else "Make"
        color_map = (self._colors.get("oem_by_label", {}) if anonymous
                     else self._colors.get("oem_by_make", {}))

        for grp_name, grp in sorted(df.groupby(group_col), key=lambda t: t[0]):
            x = pd.to_numeric(grp[xcol], errors="coerce").values
            y = pd.to_numeric(grp[ycol], errors="coerce").values
            m = np.isfinite(x) & np.isfinite(y) & (y > 0)
            if m.sum() < 5:
                continue
            x, y = x[m], y[m]
            color = color_map.get(grp_name, "gray")
            n = len(x)
            x_hi = x.max() if dash_extend_to else (xlim[1] or x.max())
            xl = np.linspace(xlim[0] or x.min(), x_hi, 200)

            if fit_type in ("linear", "dual"):
                fit = _linear_fit(x, y)
                if fit:
                    k, b, r2 = fit
                    yl = k * xl + b
                    ax.plot(xl, yl, color=color, lw=FIT_LW, alpha=FIT_ALPHA,
                            label=_linear_label(grp_name, k, b, r2, n))
                    # 虚线延伸
                    if dash_extend_to and x_hi < dash_extend_to:
                        xd = np.linspace(x_hi, dash_extend_to, 50)
                        ax.plot(xd, k * xd + b, color=color, lw=FIT_LW,
                                linestyle="--", alpha=DASH_ALPHA)
                    if style == "shaded":
                        sigma = np.std(y - (k * x + b))
                        ax.fill_between(xl, yl - sigma, yl + sigma,
                                        color=color, alpha=SHADE_ALPHA, linewidth=0)
                    if style == "errorbar":
                        bc, bm, bs = _binned_stats(x, y)
                        if bc is not None:
                            ax.errorbar(bc, bm, yerr=bs, fmt="o", color=color,
                                        markersize=4, capsize=3, alpha=0.7,
                                        linewidth=1)

            if fit_type in ("reciprocal", "dual"):
                rfit = _recip_fit(x, y)
                if rfit:
                    popt, r2 = rfit
                    yl = _recip_model(xl, *popt)
                    ls = "--" if fit_type == "dual" else "-"
                    lbl = None if fit_type == "dual" else _recip_label(grp_name, popt, r2, n)
                    ax.plot(xl, yl, color=color, lw=FIT_LW, linestyle=ls,
                            alpha=DASH_ALPHA if fit_type == "dual" else FIT_ALPHA,
                            label=lbl)
                    # 虚线延伸（仅非 dual 模式）
                    if dash_extend_to and x_hi < dash_extend_to and fit_type != "dual":
                        xd = np.linspace(x_hi, dash_extend_to, 50)
                        ax.plot(xd, _recip_model(xd, *popt), color=color,
                                lw=FIT_LW, linestyle="--", alpha=DASH_ALPHA)
                    if style == "shaded" and fit_type != "dual":
                        sigma = np.std(y - _recip_model(x, *popt))
                        ax.fill_between(xl, yl - sigma, yl + sigma,
                                        color=color, alpha=SHADE_ALPHA, linewidth=0)

        title = f"{ylabel} vs {xlabel} (per OEM)"
        if style != "plain":
            title += f" ({style})"
        ax.set(xlabel=xlabel, ylabel=ylabel, xlim=xlim, ylim=ylim)
        ax.set_title(title, fontsize=FS_TITLE)
        _apply_style(ax)
        fig.tight_layout()
        fig.savefig(save_path, dpi=DPI, bbox_inches="tight")
        plt.close(fig)


# ── CLI 入口 ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="从 xlsx 报告批量生成分析图（替代 excel_plotter 子包）")
    parser.add_argument("--version", default=_TOOLKIT_VERSION,
                        help="report-database version (default tracks the installed "
                             "jolt_toolkit version)")
    parser.add_argument("--out-dir", required=True,
                        help="图表输出目录（必填——顶层 figures/ 已弃用，请显式指定，"
                             "named/ 与 anon/ 作为其子目录）")
    parser.add_argument("--anon", action="store_true",
                        help="生成匿名版图表（OEM A/B/C/D）")
    args = parser.parse_args()

    report_dir = PROJECT_ROOT / "excel_report_database" / args.version
    if not report_dir.exists():
        logger.error("报告目录不存在: %s", report_dir)
        sys.exit(1)

    out_root = Path(args.out_dir)
    plotter = XlsxReportPlotter()

    # 实名版
    named_dir = out_root / "named"
    logger.info("生成实名版图表 → %s", named_dir)
    plotter.plot_all([str(report_dir)], output_dir=str(named_dir), anonymous=False)

    # 匿名版
    if args.anon:
        anon_dir = out_root / "anon"
        logger.info("生成匿名版图表 → %s", anon_dir)
        plotter.plot_all([str(report_dir)], output_dir=str(anon_dir), anonymous=True)

    logger.info("完成！")


if __name__ == "__main__":
    main()
