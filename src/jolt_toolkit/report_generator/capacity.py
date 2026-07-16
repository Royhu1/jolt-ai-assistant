"""
report_generator.capacity
==========================
Effective battery-capacity post-processing, extracted from ``_generator`` in
the v3.0.0 behaviour-preserving refactor. Owns the row-tuple column-index
bookkeeping (``_row_idx`` / ``_IDX_*``), the ΔSOC-weighted donor-capacity
estimator (:func:`_soc_weighted_cap`), the per-period donor capacity
(:func:`_period_capacity_from_rows`), the quarterly weighted-average schema
(:func:`_recompute_weighted_capacity`), the time-local ±1σ capacity correction
(:func:`_correct_effective_capacity`) and the ``vehicles.json`` capacity-ledger
write-back (:func:`_persist_effective_capacity`).

The two big functions were ``@staticmethod``s on ``JOLTReportGenerator``; they
are re-exposed there (``JOLTReportGenerator._correct_effective_capacity`` /
``_persist_effective_capacity``) by ``_generator`` so existing call sites keep
working (:mod:`jolt_toolkit.scripts.recompute_from_cache`,
:mod:`jolt_toolkit.report_generator.capacity_backfill`).

Chinese comments/docstrings are preserved verbatim from the v2.2.8 source; the
whole-core English translation is Phase 4 of the v3.0.0 refactor.
"""

import logging

import numpy as np
import pandas as pd

from jolt_toolkit.report_generator.report_builder import HEADERS
from jolt_toolkit.report_generator.segment_algorithms import VEHICLE_CONFIG

# ── row-tuple 列索引（从 HEADERS 动态派生，排除首列 Leg Number）─────────────
# 这些常量仅用于电车分支的 effective-capacity 后处理，柴油车用独立的 DIESEL_HEADERS
# 不经过此路径。
def _row_idx(header_name: str) -> int:
    """返回 header_name 在 row tuple 中的 0-based 索引（不含 Leg Number 列）。"""
    return HEADERS.index(header_name) - 1


# The row tuple omits the leading 'Leg Number' column (see report_builder
# `_seg_to_row`), so every _IDX_* below is HEADERS.index(name) - 1. Guard the
# contract explicitly so a HEADERS reorder that moves 'Leg Number' fails loudly.
assert HEADERS[0] == "Leg Number"


_IDX_LEG_TYPE   = _row_idx('Leg Type')
_IDX_SOC_CHANGE = _row_idx('SOC Change (%)')
_IDX_ENERGY     = _row_idx('Energy Change (kWh)')
_IDX_DISTANCE   = _row_idx('Distance (km)')
_IDX_EPERF      = _row_idx('Energy Performance (kWh/km)')
_IDX_CAP        = _row_idx('Battery Capacity (kWh)')
_IDX_ESOURCE    = _row_idx('Energy Source')
_IDX_BPOWER     = _row_idx('Battery Power (kW)')
_IDX_DURATION   = _row_idx('Duration (HH:MM:SS)')
_IDX_ELEV       = _row_idx('Elevation Difference (m)')
_IDX_MASS       = _row_idx('Vehicle Mass (kg)')
_IDX_EPERF_CORR = _row_idx('Energy Performance Corrected by Elevation Difference (kWh/km)')
_IDX_EPERF_KIN  = _row_idx('Energy Performance Kinetics Corrected (kWh/km)')
_IDX_EP_EXCL_AUX = _row_idx('EP_exclude_aux')
_IDX_START      = _row_idx('Start Time (UTC)')

# ── v2.2.4: time-local (~1-month) effective-capacity window ──────────────────
# soc_estimate 段的容量改由「该行 Start Time ±CAP_WINDOW_HALF_DAYS 天」窗口内的
# 非 soc_estimate effective capacity 推算，以反映电池老化与季节温度漂移（长/全
# 量程报告尤甚，如 EX74JXY 2025-04→2026-02）。窗口内仍保持「充电段优先于放电段」。
# 窗口若无 donor 则逐步加倍半宽，最终退化为全周期均值（等价旧的全局行为），再退化
# 为 fallback_kwh。短报告（≤3 个月）由于周期跨度小，窗口很快覆盖全周期，行为与旧版
# 几乎一致。改这个常量即可整体调节窗宽。
CAP_WINDOW_HALF_DAYS = 15   # 半窗宽（天）；总窗口 ≈ 1 个月
_DAY_NS = 86_400 * 1_000_000_000


# ── v2.2.6+: 季度（报告周期）级 effective-capacity 加权平均 schema ────────────
# vehicles.json 的 ``effective_capacity_kwh`` 不再被「最后一次生成的那个周期均值」
# 覆盖（旧实现 = 容量漂移 / 丢失退化轨迹）。改为对 ``effective_capacity_quarterly``
# （``{period_key: {kwh, n}}``，period_key = 报告周期串 ``YYYYMMDD_YYYYMMDD``，与
# 季度报告 1:1）里所有「可靠」季度按 donor 数加权平均：Σ(kwh·n)/Σn。
# 一个季度若 donor 数 ``n < MIN_DONORS`` 视为不可靠（样本太少，单个异常容量读数即
# 可显著拉偏季度均值，标准误 ≈ σ/√n）：不计入加权平均，其存储 ``kwh`` 回退为该平均
# 值（``n`` 照存以便识别）。保留 ``effective_capacity_kwh`` 键名 = PDF 续航 /
# dashboard / SOC 估算种子等所有读者零改动地自动拿到稳定平均。
# 阈值取 5：活跃电车一个季度通常有数十次 measured 充/放电 donor，远超 5；< 5 干净
# 地标记「真正稀疏」的部分窗口（如 CMZ6260 的 ~6 周补窗）或几乎没跑的车。
MIN_DONORS = 5


# ── v2.2.8: per-vehicle SOC-energy fallback for stale counter anchors ─────────
# On a handful of vehicles the Total-Energy-Used counter ANCHORS (endpoint
# snapshots) are stale / bursty — far from the trip boundary — so a discharge
# leg's counter delta under/over-attributes energy (a frozen anchor makes one leg
# read ≈0 kWh while the next leg swallows the whole backlog, giving an implied
# capacity 2–3× the fleet median and EP 2.5–5 kWh/km). These are counter-ANCHOR
# failures, not ΔSOC failures — on these vehicles the SOC channel is densely
# sampled and reliable. For such vehicles we opt in (``soc_energy_fallback: true``
# in vehicles.json) to a **gated** step-2 rewrite: an outlier (±1σ) counter-sourced
# leg whose ΔSOC is large enough AND whose implied capacity is far enough from the
# inlier replacement gets its energy re-derived from ``ΔSOC × replacement_capacity``
# (Energy Source → 'soc_fallback'). The dual gate keeps the intervention surgical —
# it only fires when the counter is BOTH an outlier AND has a trustworthy large
# ΔSOC — so ordinary short / small-ΔSOC legs (where SOC quantisation dominates and
# the counter is the better measurement) keep their counter energy (MODE A).
#
# Vehicles NOT enabled: AV24LXJ/K/L (user-verified high-rate trustworthy counters —
# see the MODE B rejection note in ``_correct_effective_capacity``), EX74JXW/JXY
# (logger-grade moving_energy), the SOC-only Mercedes (LN25NKE/YN25RSY/YN75NMA are
# 100% soc_estimate so this is moot), and diesel (no SOC/counter).
#
# ``min_dsoc_pct`` bounds the integer-% SOC quantisation error of the fallback
# energy to ≤ ~±5 % (a ±0.5 % rounding on |ΔSOC| ≥ 10 %); ``min_dev`` requires the
# implied capacity to sit ≥ 30 % away from the replacement before we distrust the
# counter. Both are overridable per vehicle (``soc_fallback_min_dsoc_pct`` /
# ``soc_fallback_min_dev``); no vehicle overrides them today.
SOC_FALLBACK_MIN_DSOC_PCT = 10.0
SOC_FALLBACK_MIN_DEV = 0.30


def _resolve_soc_fallback(cfg) -> dict | None:
    """Build the per-vehicle SOC-energy-fallback control dict from a vehicle
    config, or ``None`` when the vehicle has not opted in.

    Returns ``{'enabled': True, 'min_dsoc_pct': float, 'min_dev': float}`` when
    ``cfg['soc_energy_fallback']`` is truthy, honouring optional per-vehicle
    overrides ``soc_fallback_min_dsoc_pct`` / ``soc_fallback_min_dev``; otherwise
    ``None`` (callers then run the default MODE A gate unchanged).
    """
    if not cfg or not cfg.get('soc_energy_fallback'):
        return None
    try:
        min_dsoc = float(cfg.get('soc_fallback_min_dsoc_pct',
                                 SOC_FALLBACK_MIN_DSOC_PCT))
    except (TypeError, ValueError):
        min_dsoc = SOC_FALLBACK_MIN_DSOC_PCT
    try:
        min_dev = float(cfg.get('soc_fallback_min_dev', SOC_FALLBACK_MIN_DEV))
    except (TypeError, ValueError):
        min_dev = SOC_FALLBACK_MIN_DEV
    return {'enabled': True, 'min_dsoc_pct': min_dsoc, 'min_dev': min_dev}


def _cap_is_valid(v) -> bool:
    """容量 / SOC 值是否为有效数字（非 None / 非 NaN）。"""
    if v is None:
        return False
    try:
        return not np.isnan(v)
    except (TypeError, ValueError):
        return False


def _soc_weighted_cap(caps, weights):
    """ΔSOC-weighted (combined-ratio) donor effective capacity — replaces the
    plain mean of per-segment implied capacities.

    Each donor's implied capacity is ``C_i = |ΔE_i| / (|ΔSOC_i|/100)``. SOC is
    integer-% quantised, so a single leg's ``C_i`` is noisy AND upward-biased for
    small ``|ΔSOC|`` (σ_C/C ≈ 0.5/|ΔSOC|, and Jensen makes ``E[1/ΔSOC] > 1/ΔSOC``);
    a **plain mean** of donor ``C_i`` is therefore inflated whenever the donor pool
    contains small-ΔSOC legs. This helper instead returns the ΔSOC-weighted mean

        C_eff = Σ(C_i · |ΔSOC_i|) / Σ|ΔSOC_i|  ==  100 · Σ|ΔE_i| / Σ|ΔSOC_i|

    i.e. the combined-ratio estimator — it uses all data (no arbitrary ΔSOC
    cutoff), smoothly down-weights the noisy short legs, and never divides by a
    single small ΔSOC, removing the small-ΔSOC bias entirely.

    Rejected alternatives (verified on AV24LXJ discharge donors): a hard
    ``|ΔSOC| ≥ X%`` cutoff (threshold-sensitive — ≥5% ok but ≥10% over-restricts
    and drifts, and discards data) and ``ΔSOC²`` / inverse-variance weighting
    (over-weights the largest legs and drifts low).

    ``weights`` are the per-donor ``|ΔSOC|`` (%). Entries whose weight is invalid
    / non-positive are excluded from the weighted sum (they can't be weighted); if
    the total usable weight is 0 the result degrades to a plain mean of ``caps``
    (guards ``Σ|ΔSOC| == 0``). Returns ``None`` for an empty pool.
    """
    caps = [float(c) for c in caps]
    if not caps:
        return None
    ws = [abs(float(w)) if (_cap_is_valid(w) and float(w) != 0.0) else 0.0
          for w in weights]
    tot = sum(ws)
    if tot <= 0.0:
        return float(np.mean(caps))
    return sum(c * w for c, w in zip(caps, ws)) / tot


def _period_capacity_from_rows(rows, idx_cap, idx_soc, idx_esrc):
    """复刻 ``_correct_effective_capacity`` 的 donor-based ``avg_eff_cap`` 定义：
    从非 ``soc_estimate`` 段（measured charge / discharge leg）按「充电优先」取
    effective capacity，donor 集内用 **ΔSOC 加权均值**（组合比估计
    ``100·Σ|ΔE|/Σ|ΔSOC|``，见 :func:`_soc_weighted_cap`）而非普通均值——普通均值在
    donor 池含小 ΔSOC 段时上偏（整数 % 量化 + Jensen）。返回
    ``(kwh|None, n_donors, source)``，source ∈ {'charge', 'discharge', 'fallback'}。
    ``n_donors`` 仍为 donor **计数**（供跨季度 donor 数加权平均，语义不变）。

    与 ``_persist_effective_capacity`` / backfill 共用同一口径：``rows`` 既可为报告
    row-tuple（传 ``_IDX_CAP`` / ``_IDX_SOC_CHANGE`` / ``_IDX_ESOURCE``），也可为从
    xlsx 读出的 ``(cap, soc, src)`` 三元组（传 0, 1, 2），保证 live 与 backfill 一致。

    donor 必须满足：``Energy Source`` 是真实的 measured 字符串（``isinstance str`` 且
    ∉ {'soc_estimate', 'soc_fallback'} —— 两者都是 SOC 推得的能量、非测量 donor）、
    ``cap`` 为正的有效数字、且 ``SOC Change`` 为可用的非零数值
    （作为加权权重；缺 ΔSOC 的段无法加权，故排除）。measured-leg 判据在 live 路径下对
    真实 measured leg 恒成立（其 energy_source 总是字符串），故对 live donor 集零影响；
    但在 backfill 读最终 xlsx 时它**排除掉 Stop 行**——Stop 行的 ``Energy Source`` /
    ``Battery Capacity`` 是 ``=NA()`` 公式，openpyxl ``data_only=True`` 会把 ``=NA()``
    读成整数 ``0``，否则会被误当成 cap=0 的 donor 污染均值。``cap > 0`` 是额外保险
    （effective capacity 物理上必为正；真实 donor 恒 > 0，故同样不影响 live 数值）。
    """
    charge, discharge = [], []   # list[(cap, |ΔSOC|)]
    for row in rows:
        cap = row[idx_cap]
        src = row[idx_esrc]
        soc = row[idx_soc]
        # measured donor := real energy counter (NOT SOC-derived). Exclude both
        # 'soc_estimate' (SOC × nominal) and 'soc_fallback' (v2.2.8 SOC-rewritten
        # stale-anchor legs) — neither is a measured capacity donor.
        if (isinstance(src, str) and src not in ('soc_estimate', 'soc_fallback')
                and _cap_is_valid(cap) and cap > 0 and _cap_is_valid(soc)):
            if soc > 0:
                charge.append((float(cap), abs(float(soc))))
            elif soc < 0:
                discharge.append((float(cap), abs(float(soc))))
    if charge:
        caps, ws = zip(*charge)
        return _soc_weighted_cap(caps, ws), len(charge), 'charge'
    if discharge:
        caps, ws = zip(*discharge)
        return _soc_weighted_cap(caps, ws), len(discharge), 'discharge'
    return None, 0, 'fallback'


def _recompute_weighted_capacity(quarterly: dict, min_donors: int = MIN_DONORS):
    """给定 ``{period_key: {kwh, n}}``，对**可靠**季度（``n >= min_donors``）按 donor
    数加权平均：Σ(kwh·n)/Σn。就地把稀疏季度（``n < min_donors``）的存储 ``kwh`` 回填
    为该平均值（``n`` 不动）。返回 ``(weighted_avg|None, n_reliable, n_sparse)``。

    退化：若没有任何可靠季度但存在 donor 季度（``0 < n < min_donors``），改用全部
    donor 季度做同样的加权平均，保证 ``effective_capacity_kwh`` 仍写得出（PDF 续航不
    落空）。完全没有 donor 季度 → 返回 ``(None, 0, 0)``，调用方不动既有标量。
    """
    reliable = [(v['kwh'], v['n']) for v in quarterly.values()
                if v.get('kwh') is not None and v.get('n', 0) >= min_donors]
    n_sparse = sum(1 for v in quarterly.values()
                   if v.get('kwh') is not None and 0 < v.get('n', 0) < min_donors)
    pool = reliable or [(v['kwh'], v['n']) for v in quarterly.values()
                        if v.get('kwh') is not None and v.get('n', 0) > 0]
    if not pool:
        return None, 0, n_sparse
    total_n = sum(n for _, n in pool)
    wavg = round(sum(k * n for k, n in pool) / total_n, 1)
    # 稀疏季度的存储 kwh 回退为加权平均（n 保留以便判定）
    for v in quarterly.values():
        if v.get('n', 0) < min_donors:
            v['kwh'] = wavg
    return wavg, len(reliable), n_sparse


def _correct_effective_capacity(rows, idx_cap, idx_energy, idx_soc,
                                 idx_eperf, idx_dist, idx_esrc,
                                 idx_bpower, idx_dur,
                                 idx_eperf_corr, idx_elev, idx_mass,
                                 fallback_kwh, idx_eperf_kin=None,
                                 idx_start=None, soc_fallback=None):
    """
    后处理：修正 effective battery capacity 并反算相关字段。

    返回 (rows, effective_cap, cap_source)：
    - effective_cap: 整个报告周期的最终 effective capacity 均值 (kWh)，
      供 ``_persist_effective_capacity`` 写回 vehicles.json（语义不变）。
    - cap_source: 'charge' | 'discharge' | 'fallback'

    time-local (~1-month) 容量（v2.2.4）
    --------------------------------------
    每个 soc_estimate 段的替换容量改由「该段 Start Time ±``CAP_WINDOW_HALF_DAYS``
    天」窗口内的非 soc_estimate effective capacity 推算，窗口内仍保持
    「充电段优先于放电段」。这样长报告里的电池老化 / 季节温度漂移就不会被一个
    全周期均值抹平。``idx_start`` 是 row tuple 中 'Start Time (UTC)' 列的索引
    （值为 ``pd.Timestamp``）；为 ``None`` 时退回旧的全周期单一均值行为。

    优雅降级（逐级）：
    1. ±CAP_WINDOW_HALF_DAYS 天窗口内的 donor（充电优先，再放电）。
    2. 窗口无 donor → 逐步加倍半宽，直到找到 donor 或窗口覆盖整个周期
       （覆盖整个周期即等价于旧的全局均值行为）。
    3. 整个周期都没有 donor（或该行缺时间戳）→ 全局均值。
    4. 全局也没有 donor → ``fallback_kwh``。

    步骤 1：按上述时间局部逻辑替代每个 soc_estimate 段的容量值并反算 energy。
    步骤 2：用**全局 ±1σ** 检测异常 effective capacity，替换值同样取「inlier
            donor 的时间局部窗口均值」，避免把错误季节的偏差重新注入。
            **energy 反算按 ``energy_source`` 门控**：只有 soc_estimate 段
            （energy 本就由 SOC × capacity 推得）才重算 energy / EP / corrected
            / kinetics；counter-sourced 段（``energy_source`` ∈ {total_energy,
            moving_energy}）**默认**（MODE A）只修正 capacity 列本身，其 energy /
            EP / corrected / kinetics 一律保留计数器原值 —— 异常的 IMPLIED
            capacity 通常源于分母 ΔSOC 的整数 % 量化不可靠（短程/小 ΔSOC 被低估），
            而非计数器 energy 有误，用 SOC 反算会把整数 % 的低估注入短程 leg 形成伪
            低 EP 带。

    逐车 SOC-energy fallback（v2.2.8，opt-in，见 ``soc_fallback`` 参数）
    ----------------------------------------------------------------
    少数车（如 YK73WFN / EV73SAL / N88GNW / T88RNW / TA70WTL / CMZ6260 /
    KY24LHT）的 Total-Energy-Used 计数器**锚点陈旧/突发**（首尾快照远离 trip
    边界），造成成对的欠/过归因：一条 leg 因锚点冻结读成 ≈0 kWh，紧接的 leg 吞掉
    全部积压，IMPLIED capacity 达车队中位数 2–3 倍、EP 2.5–5 kWh/km。这是**计数
    器锚点失效**而非 ΔSOC 失效——这些车的 SOC 通道密采可靠。对**开启 fallback 的
    车**，步骤 2 的 counter-sourced 异常行改走**双门控 SOC 反算**：仅当
    ``|ΔSOC| ≥ min_dsoc_pct``（把整数 % 量化误差限制在 ≤ ~±5 %）**且**
    ``|原 IMPLIED cap − 替换 cap| / 替换 cap ≥ min_dev`` 时，才用
    ``ΔSOC/100 × 替换 cap`` 反算 energy（符号随 ΔSOC，放电为负）、把 Energy Source
    置为 ``'soc_fallback'`` 并按 soc_estimate 段的方式重算 EP / Battery Power /
    corrected / kinetics；否则退回 MODE A（仅修 capacity 列、保留计数器 energy）。
    双门控保证干预外科手术式精准：只有当计数器**既是 ±1σ 异常又有可信的大 ΔSOC**
    时才反算，普通短程/小 ΔSOC leg（SOC 量化主导、计数器更可信）保留计数器值。
    ``soc_fallback=None`` 时（默认、未开启的车）行为与旧版 MODE A 完全一致。

    已评估并否决的替代方案（MODE B，v2.2.7 A/B 对比，不采用）
    --------------------------------------------------------------
    曾评估一个「随 ΔSOC 缩放的异常阈值」方案：把固定 ±1σ 换成逐 leg 的
    σ_i = sqrt(σ_true² + σ_soc²)（σ_soc = C·0.5/|ΔSOC%| 为量化噪声，σ_true 由
    干净大 ΔSOC(≥10%) 段稳健估计），|C−μ| > 2σ_i 判异常，且异常行**无论
    energy_source** 都用 SOC 反算。**否决**：AV24LXJ/K/L 全量对比显示它主要在
    **中等 ΔSOC（中位 8%，仅约 1/3 ≥10%）**触发——此处 SOC 量化仍达 ±5–12%——
    用「ΔSOC×车队平均容量」这个**推断值**覆盖了原始计数器的**实测能量**
    （逐 trip 计数器增量与报告 E 吻合、零 reset、基本单调，且首尾快照多紧贴 trip
    边界，是可信的直接能量测量），把真实 EP 变异同质化、单车造出几十条不合理
    EP（>2.0 kWh/km，例如把教科书级 EP 1.00 改写成 1.51、1.23 改写成 0.81）。两法
    对原始伪低带的修复完全一致（小 ΔSOC 段两法都不触发、保留计数器）。故 MODE A
    对全体车队保持默认。**v2.2.8 的逐车 fallback（上）正是 MODE B 被否决之处的外科
    版**：它不是「无论 energy_source 都盲目 SOC 反算」，而是叠加了「大 ΔSOC + 大偏差」
    双门控、且**只对显式开启的车**生效——AV24LXJ/K/L 正因为上面这段实测计数器可信
    的结论**不开启**（vehicles.json 无 ``soc_energy_fallback``），故其数值路径与
    v2.2.7 逐字节一致。

    待查（FUTURE，勿在此处理）
    --------------------------
    1. 差异集里计数器 energy **系统性低于** SOC 推断（约 248 升 vs 65 降），
       可能是 SOC 表在短/中程 trip 上的非线性；值得单独排查，但不应由「盲目
       SOC 替换」来掩盖。
    2. 少数「陈旧快照」导致的 anchor spillover（首快照早于 trip 起点很久 → 计数器
       增量多计 → EP 虚高，如 AV24LXJ 2024-06-24 07:45 EP 2.34）应由**专门的
       anchor-spillover 守卫**处理，而非全盘 SOC 反算。
    """
    # v2.2.8 per-vehicle SOC-energy fallback control (None = MODE A only).
    fb_enabled = bool(soc_fallback and soc_fallback.get('enabled'))
    fb_min_dsoc = float((soc_fallback or {}).get('min_dsoc_pct',
                                                 SOC_FALLBACK_MIN_DSOC_PCT))
    fb_min_dev = float((soc_fallback or {}).get('min_dev',
                                                SOC_FALLBACK_MIN_DEV))

    def _apply_soc_energy(row, soc_chg, cap):
        """Re-derive energy from ``ΔSOC/100 × cap`` (signed) and recompute the
        downstream EP / Battery Power / elevation- & kinetics-corrected EP,
        exactly as a native ``soc_estimate`` leg. Shared by the step-1
        soc_estimate rewrite and the v2.2.8 step-2 SOC-fallback rewrite."""
        row[idx_energy] = round(soc_chg / 100.0 * cap, 3)
        dist = row[idx_dist]
        if _cap_is_valid(dist) and dist > 0 and _cap_is_valid(row[idx_energy]):
            row[idx_eperf] = round(abs(row[idx_energy]) / dist, 4)
        dur_days = row[idx_dur]
        if _cap_is_valid(dur_days) and dur_days > 0 and _cap_is_valid(row[idx_energy]):
            dur_h = dur_days * 24.0
            row[idx_bpower] = round(row[idx_energy] / dur_h, 3)
        _recalc_eperf_corrected(row)

    def _fallback_applies(row, original_cap, repl):
        """Dual gate for the v2.2.8 SOC-energy fallback (counter-sourced outlier
        rows only). True iff ΔSOC is large enough that the fallback's integer-%
        quantisation error stays small (``|ΔSOC| ≥ fb_min_dsoc``) AND the row's
        original IMPLIED capacity sits far enough from the inlier replacement
        (``|original_cap − repl| / repl ≥ fb_min_dev``) to distrust the counter.
        ``repl`` must be a positive replacement capacity."""
        soc_chg = row[idx_soc]
        if not (_cap_is_valid(soc_chg) and abs(float(soc_chg)) >= fb_min_dsoc):
            return False
        if not (_cap_is_valid(repl) and repl > 0 and _cap_is_valid(original_cap)):
            return False
        return abs(float(original_cap) - repl) / repl >= fb_min_dev

    def _recalc_eperf_corrected(row):
        """energy 修改后重算海拔修正和动能修正能量效率。"""
        e = row[idx_energy]
        d = row[idx_dist]
        h = row[idx_elev]
        m = row[idx_mass]
        if not all(_cap_is_valid(v) for v in (e, d, h, m)):
            return
        if d <= 0:
            return
        ke_per_d = None
        if idx_eperf_kin is not None:
            old_corr = row[idx_eperf_corr]
            old_kin = row[idx_eperf_kin]
            if _cap_is_valid(old_corr) and _cap_is_valid(old_kin):
                ke_per_d = old_corr - old_kin
        e_grav = m * 9.81 * h / 3_600_000.0
        row[idx_eperf_corr] = round((abs(e) - e_grav) / d, 4)
        if ke_per_d is not None and idx_eperf_kin is not None:
            row[idx_eperf_kin] = round(row[idx_eperf_corr] - ke_per_d, 4)

    # ── 时间戳与窗口准备 ───────────────────────────────────────────
    def _naive_ns(v):
        """row 的 Start Time → tz-naive ns 整数；不可解析则 None。"""
        if v is None:
            return None
        try:
            ts = pd.Timestamp(v)
        except (TypeError, ValueError):
            return None
        if ts is pd.NaT or pd.isna(ts):
            return None
        if ts.tzinfo is not None:
            ts = ts.tz_convert(None)
        # pd.Timestamp.value 对标量恒为 ns，无需 .as_unit
        return int(ts.value)

    # 每个 row 的起始时间（ns）；idx_start 为 None 时全部 None → 退回全局行为
    if idx_start is not None:
        row_ns = [_naive_ns(row[idx_start]) for row in rows]
    else:
        row_ns = [None] * len(rows)
    valid_ns = [n for n in row_ns if n is not None]
    period_span_days = ((max(valid_ns) - min(valid_ns)) / _DAY_NS
                        if len(valid_ns) >= 2 else 0.0)
    # 加倍半宽的上限：覆盖整个周期即等价旧全局行为
    max_half_days = max(float(CAP_WINDOW_HALF_DAYS), period_span_days)

    def _window_mean(donors, t_ns, base_half_days):
        """donors: list[(ns, cap, w)]，w = |ΔSOC|。在 ±base_half 天窗口内取
        **ΔSOC 加权均值**（组合比估计 Σ(cap·w)/Σw，见 :func:`_soc_weighted_cap`），
        无 donor 则逐步加倍半宽直至找到或覆盖整个周期。返回
        (mean|None, n_used, half_used)；窗口内 Σw==0 时降级为普通均值。"""
        if not donors or t_ns is None:
            return None, 0, base_half_days
        arr_ns = np.array([d[0] for d in donors], dtype=np.int64)
        arr_cap = np.array([d[1] for d in donors], dtype=float)
        arr_w = np.array([d[2] for d in donors], dtype=float)
        half = float(base_half_days)
        while True:
            win_ns = int(half * _DAY_NS)
            mask = np.abs(arr_ns - t_ns) <= win_ns
            if mask.any():
                caps_w = arr_cap[mask]
                ws_w = arr_w[mask]
                tot = float(ws_w.sum())
                # same estimator as _soc_weighted_cap (kept inline verbatim): the
                # numpy vectorised Σ(cap·w)/Σw here differs in float accumulation
                # order (and skips the invalid-weight filtering, unreachable for
                # window donors) from the Python-level helper, so routing through it
                # could perturb the byte-identical output — deliberately not shared.
                m = (float((caps_w * ws_w).sum() / tot) if tot > 0.0
                     else float(caps_w.mean()))
                return m, int(mask.sum()), half
            if half >= max_half_days:
                return None, 0, half
            half = min(half * 2.0, max_half_days)

    # ── 步骤 1：time-local effective capacity 替换 soc_estimate 段 ────
    # 充电段: SOC 上升 (soc > 0)；放电段: SOC 下降 (soc < 0)
    # donor 携带 |ΔSOC| 作为组合比权重（充/放电容量在段内用 ΔSOC 加权均值，
    # 消除小 ΔSOC 段的整数 % 量化上偏；见 _soc_weighted_cap）。
    charge_donors = []      # list[(ns, cap, w)] ; w = |ΔSOC|
    discharge_donors = []
    charge_caps = []        # list[(cap, w)]  全周期（不要求有时间戳）
    discharge_caps = []
    for row, n in zip(rows, row_ns):
        cap = row[idx_cap]
        src = row[idx_esrc]
        soc = row[idx_soc]
        # measured donor := NOT SOC-derived. On fresh generation 'soc_fallback'
        # cannot yet appear here (it is assigned later, in step 2); the check is
        # defensive for replay paths that might feed already-corrected rows.
        if (_cap_is_valid(cap) and src not in ('soc_estimate', 'soc_fallback')
                and _cap_is_valid(soc)):
            w = abs(float(soc))
            if soc > 0:
                charge_caps.append((cap, w))
                if n is not None:
                    charge_donors.append((n, cap, w))
            elif soc < 0:
                discharge_caps.append((cap, w))
                if n is not None:
                    discharge_donors.append((n, cap, w))

    # 全周期 ΔSOC 加权均值（充电优先），用于退化与最终持久化语义（口径不变）。
    # 用不依赖时间戳的 *_caps，确保即使 idx_start=None（旧调用）也能给出
    # 正确的全局 charge/discharge 加权均值而非误落到 fallback。
    if charge_caps:
        caps, ws = zip(*charge_caps)
        avg_eff_cap = _soc_weighted_cap(caps, ws)
        cap_source = 'charge'
    elif discharge_caps:
        caps, ws = zip(*discharge_caps)
        avg_eff_cap = _soc_weighted_cap(caps, ws)
        cap_source = 'discharge'
    else:
        avg_eff_cap = fallback_kwh
        cap_source = 'fallback'

    def _local_cap_for(t_ns):
        """充电优先的时间局部 effective capacity。返回 (cap|None, src, half)。"""
        m, _, half = _window_mean(charge_donors, t_ns, CAP_WINDOW_HALF_DAYS)
        if m is not None:
            return m, 'charge', half
        m, _, half = _window_mean(discharge_donors, t_ns, CAP_WINDOW_HALF_DAYS)
        if m is not None:
            return m, 'discharge', half
        return None, cap_source, half

    n_local = n_widened = n_global = n_fallback = 0
    widened_half_max = 0.0
    for row, t_ns in zip(rows, row_ns):
        if row[idx_esrc] == 'soc_estimate' and _cap_is_valid(row[idx_soc]):
            cap, _src, half = _local_cap_for(t_ns)
            if cap is None:
                # 该行缺时间戳或全周期无 donor → 全局均值（或 fallback_kwh）
                cap = avg_eff_cap
                if cap_source == 'fallback':
                    n_fallback += 1
                else:
                    n_global += 1
            elif half <= CAP_WINDOW_HALF_DAYS:
                n_local += 1
            else:
                n_widened += 1
                widened_half_max = max(widened_half_max, half)
            row[idx_cap] = round(cap, 2)
            _apply_soc_energy(row, row[idx_soc], cap)

    logging.info(
        "步骤 1 (time-local ±%d天, 周期跨度=%.0f天): soc_estimate 替换 — "
        "局部=%d, 扩窗=%d(最大半宽 %.0f天), 全局回退=%d, fallback=%d; "
        "donor(充电=%d, 放电=%d), 全局均值=%.1f kWh(来源=%s)",
        CAP_WINDOW_HALF_DAYS, period_span_days, n_local, n_widened,
        widened_half_max, n_global, n_fallback,
        len(charge_donors), len(discharge_donors), avg_eff_cap, cap_source)

    # ── 步骤 2：全局 ±1σ 检测 + 时间局部 inlier 均值替换 ─────────────
    all_caps = [row[idx_cap] for row in rows if _cap_is_valid(row[idx_cap])]
    if len(all_caps) >= 3:
        cap_mean = float(np.mean(all_caps))
        cap_std  = float(np.std(all_caps))
        lo = cap_mean - cap_std
        hi = cap_mean + cap_std
        # inlier donors（±1σ 内）连同时间戳 + |ΔSOC| 权重，供异常行做时间局部
        # 替换。替换均值同样用 ΔSOC 加权（组合比估计），避免小 ΔSOC 段的量化上偏
        # 重新注入替换值。缺 ΔSOC 的行权重记 0（自然排除出加权和）。
        # (soc_fallback rows are SOC-derived, not measured caps — exclude them
        # as inlier donors. On fresh generation none exist at this point, so
        # this is a defensive no-op; it matters only for replay of already-
        # corrected rows. soc_estimate rows are intentionally KEPT here — after
        # step 1 they carry a donor-derived cap, matching pre-v2.2.8 behaviour.)
        inlier_donors = [
            (n, row[idx_cap],
             abs(float(row[idx_soc])) if _cap_is_valid(row[idx_soc]) else 0.0)
            for row, n in zip(rows, row_ns)
            if n is not None and _cap_is_valid(row[idx_cap])
            and lo <= row[idx_cap] <= hi and row[idx_esrc] != 'soc_fallback'
        ]
        inlier_global_mean = (
            _soc_weighted_cap([c for _, c, _ in inlier_donors],
                              [w for _, _, w in inlier_donors])
            if inlier_donors else cap_mean)
        corrected = n_repl_local = n_energy_kept = n_soc_fallback = 0
        for row, t_ns in zip(rows, row_ns):
            cap = row[idx_cap]
            if _cap_is_valid(cap) and (cap < lo or cap > hi):
                # 原始 IMPLIED capacity（capacity 列被替换 **之前** 的值），用于
                # SOC-fallback 的偏差门控判断。
                original_cap = cap
                repl, _, _ = _window_mean(inlier_donors, t_ns,
                                          CAP_WINDOW_HALF_DAYS)
                if repl is not None:
                    n_repl_local += 1
                else:
                    repl = inlier_global_mean
                # 始终修正 capacity 列本身：既让展示合理，也让本周期最终
                # 持久化的均值不被异常 IMPLIED capacity 污染（持久化语义不变）。
                row[idx_cap] = round(repl, 2)
                # energy 反算**仅**适用于 soc_estimate 段（无可靠能量计数器，
                # 其 energy 本就由 SOC × capacity 推得）。对 counter-sourced 段
                # （energy_source ∈ {total_energy, moving_energy}），异常的
                # IMPLIED capacity 说明分母 ΔSOC 不可靠（整数 % 量化，短程/小
                # ΔSOC 被低估），而非计数器 energy 有误 —— **默认（MODE A）**必须
                # 保留计数器给出的 energy / EP / corrected / kinetics，绝不能用
                # SOC 反算覆盖（否则短程 leg 会得到虚低 EP，形成伪低带）。
                if row[idx_esrc] == 'soc_estimate':
                    soc_chg = row[idx_soc]
                    if _cap_is_valid(soc_chg) and soc_chg != 0:
                        _apply_soc_energy(row, soc_chg, repl)
                elif fb_enabled and _fallback_applies(row, original_cap, repl):
                    # v2.2.8 逐车 SOC-energy fallback：counter-sourced 异常行，
                    # 但 ΔSOC 大到量化误差可控、且 IMPLIED cap 严重偏离 —— 判定
                    # 为计数器锚点陈旧，用 SOC 反算取代不可信的计数器 energy。
                    _apply_soc_energy(row, row[idx_soc], repl)
                    row[idx_esrc] = 'soc_fallback'
                    n_soc_fallback += 1
                else:
                    n_energy_kept += 1
                corrected += 1
        logging.info(
            "步骤 2 (全局 ±1σ 检测 + time-local 替换): 修正 %d 行异常 effective "
            "capacity (其中 %d 行用局部窗口均值; counter-sourced: %d 行 SOC "
            "fallback 反算(soc_fallback), %d 行仅修容量列保留计数器 energy; "
            "全局均值=%.1f, σ=%.1f, 范围=[%.1f, %.1f], inlier donor=%d)",
            corrected, n_repl_local, n_soc_fallback, n_energy_kept,
            cap_mean, cap_std, lo, hi, len(inlier_donors))
        # 步骤 2 后的全周期均值作为最终持久化的 effective capacity（语义不变）
        final_caps = [row[idx_cap] for row in rows if _cap_is_valid(row[idx_cap])]
        if final_caps:
            avg_eff_cap = float(np.mean(final_caps))

    return rows, round(avg_eff_cap, 1), cap_source


def _persist_effective_capacity(reg, eff_cap, n_donors, source, period_key):
    """将本报告周期的 effective capacity 合入 vehicles.json（v2.2.6+ merge）。

    新 schema：
    - ``effective_capacity_quarterly``: ``{period_key: {kwh, n}}``，period_key =
      报告周期串 ``YYYYMMDD_YYYYMMDD``，与季度报告 1:1。本期写
      ``{kwh: round(eff_cap, 1), n: n_donors}``。
    - ``effective_capacity_kwh``: 对所有可靠季度（``n >= MIN_DONORS``）按 donor
      数加权平均（Σ(kwh·n)/Σn）。稀疏季度（``n < MIN_DONORS``）不计入，其存储
      ``kwh`` 由 :func:`_recompute_weighted_capacity` 回填为该平均。保留键名使
      PDF 续航 / dashboard / SOC 种子零改动地拿到稳定平均。

    仅当 source 为 'charge' / 'discharge'（来自遥测 donor）时写入；
    source='fallback'（无 donor，如纯 soc_estimate 的 SOC-only Mercedes）不写、
    不动既有标量。这同时修掉了旧实现「单周期均值覆盖」导致的容量漂移 bug。
    """
    if source == 'fallback' or eff_cap is None:
        logging.info("effective capacity 来源为 fallback（无 donor），"
                     "不更新 vehicles.json: %s %s", reg, period_key)
        return

    import json
    from filelock import FileLock
    from jolt_toolkit.configs import get_config_path
    path = get_config_path('vehicles.json')
    # Guard the read-modify-write so parallel report runs cannot clobber
    # each other's capacity ledger entries (values/timing unchanged).
    with FileLock(str(path) + '.lock'):
        with open(path, 'r', encoding='utf-8') as f:
            all_cfg = json.load(f)
        if reg not in all_cfg:
            return

        entry = all_cfg[reg]
        old_val = entry.get('effective_capacity_kwh')
        quarterly = entry.get('effective_capacity_quarterly') or {}
        quarterly[period_key] = {'kwh': round(float(eff_cap), 1), 'n': int(n_donors)}

        wavg, n_rel, n_sparse = _recompute_weighted_capacity(quarterly)
        entry['effective_capacity_quarterly'] = quarterly
        if wavg is not None:
            entry['effective_capacity_kwh'] = wavg

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(all_cfg, f, indent=2, ensure_ascii=False)
            f.write('\n')
    # 同步内存中的 VEHICLE_CONFIG
    VEHICLE_CONFIG.setdefault(reg, {})
    VEHICLE_CONFIG[reg]['effective_capacity_quarterly'] = quarterly
    if wavg is not None:
        VEHICLE_CONFIG[reg]['effective_capacity_kwh'] = wavg
    logging.info(
        "effective_capacity 已更新: %s  %.1f → %.1f kWh "
        "(本期 %s: kwh=%.1f n=%d 来源=%s; 可靠季度=%d, 稀疏=%d)",
        reg, old_val or 0, wavg if wavg is not None else (old_val or 0),
        period_key, round(float(eff_cap), 1), int(n_donors), source,
        n_rel, n_sparse)
