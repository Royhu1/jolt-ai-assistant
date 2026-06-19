"""
pedal_histogram.py
==================
踏板位置直方图计算工具。

从 Logger 的 EEC2（油门踏板位置）和 EBC1（制动踏板位置）通道提取峰值事件，
然后将峰值分布编码为逗号分隔的直方图字符串。

算法来源：旧版 JOLT 代码库 jolt_utils.py，迁移至 jolt_toolkit 统一管线。
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Logger EEC2 / EBC1 通道列名 ────────────────────────────────────────────
EEC2_COL = 'EEC2 accelerator pedal position 1'
EBC1_COL = 'EBC1 brake pedal position'

# 仅对行驶距离 > 10 km 的放电段计算踏板直方图
MIN_DISTANCE_FOR_PEDAL_KM = 10.0

# 最少样本数（少于此数认为数据不足，不计算直方图）
MIN_SAMPLES = 10


def extract_pedal_events_by_rise_fall(
    df: pd.DataFrame,
    time_col: str = "Time",
    value_col: str = EEC2_COL,
    delta_up: float = 10.0,
    delta_down: float = 8.0,
    smooth_window: int = 0,
    min_width: int = 1,
    min_separation: int = 1,
) -> dict:
    """
    基于上升/回落阈值的踏板事件检测。

    事件定义：从某次局部低点起，数值上升至少 delta_up，
    随后从该段内峰值回落至少 delta_down。

    Args:
        df:              包含时间列和踏板位置列的 DataFrame
        time_col:        时间列名
        value_col:       踏板位置列名（百分比，0-100）
        delta_up:        判定上升阈值（百分比点）
        delta_down:      判定回落阈值（百分比点）
        smooth_window:   可选：滑动中值去噪窗口（奇数，0 表示不去噪）
        min_width:       可选：事件最短持续样本数
        min_separation:  可选：事件之间的最小间隔样本数

    Returns:
        peaks: {1: {"t": 峰值时间戳, "value": 峰值}, 2: {...}, ...}
    """
    s = df.copy()
    s[time_col] = pd.to_datetime(s[time_col])
    s = s.sort_values(time_col).reset_index(drop=True)

    y = s[value_col].astype(float).values.copy()
    t = s[time_col].values

    if len(y) < 2:
        return {}

    # 可选去噪（1 Hz 数据通常不必；有毛刺时建议 3 或 5）
    if smooth_window and smooth_window >= 3 and smooth_window % 2 == 1:
        y = (pd.Series(y)
             .rolling(smooth_window, center=True)
             .median()
             .bfill()
             .ffill()
             .values)

    # 状态机
    SEEK_RISE, IN_EVENT = 0, 1
    state = SEEK_RISE

    # 记录器
    last_min_val = y[0]
    last_min_idx = 0
    peak_val = y[0]
    peak_idx = 0
    last_event_end_idx = -(10 ** 9)

    events = []
    for i in range(1, len(y)):
        val = y[i]

        if state == SEEK_RISE:
            # 更新局部低点
            if val < last_min_val:
                last_min_val = val
                last_min_idx = i

            # 是否满足上升阈值
            if val - last_min_val >= delta_up:
                state = IN_EVENT
                peak_val = val
                peak_idx = i

        elif state == IN_EVENT:
            # 追踪峰值
            if val > peak_val:
                peak_val = val
                peak_idx = i

            # 是否满足回落阈值（相对该事件峰值）
            if peak_val - val >= delta_down:
                # 最短宽度 & 事件间隔检查
                if ((peak_idx - last_min_idx + 1) >= min_width
                        and (i - last_event_end_idx) >= min_separation):
                    events.append((peak_idx, peak_val))
                    last_event_end_idx = i

                # 重置为寻找下一次上升：从当前点当作新的「局部低点」起算
                state = SEEK_RISE
                last_min_val = val
                last_min_idx = i

    # 组装 dict（按时间先后编号）
    peaks = {}
    for k, (idx, pval) in enumerate(events, start=1):
        peaks[k] = {"t": pd.Timestamp(t[idx]), "value": float(pval)}
    return peaks


def peaks_histogram_string(peaks: dict, bins: int = 10) -> str | None:
    """
    将检测到的峰值分布编码为逗号分隔的直方图字符串。

    将 0-100% 的峰值按 bins 个区间进行分组统计。

    Args:
        peaks: extract_pedal_events_by_rise_fall 返回的峰值字典
        bins:  直方图分箱数（将 0-100% 分为 bins 个区间）

    Returns:
        逗号分隔的计数字符串，如 "2,5,8,12,15,18,14,11,8,3"；无峰值时返回 None
    """
    if not peaks:
        return None

    v = [0] * bins
    bin_width = 100.0 / bins

    for event in peaks.values():
        if event and 'value' in event:
            bin_index = min(int(event['value'] / bin_width), bins - 1)
            v[bin_index] += 1

    return ','.join(map(str, v))


def compute_pedal_histogram(
    pedal_series: pd.Series | pd.DataFrame,
    value_col: str | None = None,
) -> str | None:
    """
    便捷函数：从踏板位置时间序列计算直方图字符串。

    接受索引为时间戳的 Series 或 DataFrame：
    - Series：直接使用值
    - DataFrame：使用 value_col 指定的列

    Args:
        pedal_series: 踏板位置数据（百分比，0-100），索引为 datetime
        value_col:    DataFrame 时使用的列名

    Returns:
        直方图字符串或 None
    """
    if pedal_series is None or len(pedal_series) < MIN_SAMPLES:
        return None

    # 统一转换为 DataFrame 格式
    if isinstance(pedal_series, pd.Series):
        df = pedal_series.dropna().reset_index()
        df.columns = ['Time', 'value']
        col = 'value'
    elif isinstance(pedal_series, pd.DataFrame):
        if value_col is None:
            # 取第一个非索引列
            value_col = pedal_series.columns[0]
        df = pedal_series[[value_col]].dropna().reset_index()
        df.columns = ['Time', value_col]
        col = value_col
    else:
        return None

    if len(df) < MIN_SAMPLES:
        return None

    peaks = extract_pedal_events_by_rise_fall(df, time_col='Time', value_col=col)
    return peaks_histogram_string(peaks)
