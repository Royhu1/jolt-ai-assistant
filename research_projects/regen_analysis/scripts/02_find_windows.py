"""
02_find_windows.py — YK73WFN 再生制动分析：寻找有效分析时间窗口
在 telematics 相邻采样点之间寻找同时有 logger 覆盖的时间窗口。
"""
from __future__ import annotations

import json
import glob
import os
import sys

import numpy as np
import pandas as pd

# ── 项目路径 ────────────────────────────────────────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CFG_PATH = os.path.join(ROOT, "research_projects", "regen_analysis", "config.json")
with open(CFG_PATH, encoding="utf-8") as f:
    CFG = json.load(f)

TABLES_DIR = os.path.join(ROOT, CFG["paths"]["tables_dir"])
os.makedirs(TABLES_DIR, exist_ok=True)


# ── Logger 索引构建 ──────────────────────────────────────────────────────────
def build_logger_index() -> pd.DataFrame:
    """
    为每个 logger 文件构建时间索引（起止时间 + 行数）。
    返回 DataFrame: [file_path, start_ts, end_ts, n_rows]
    """
    logger_dir = os.path.join(ROOT, CFG["paths"]["logger_dir"])
    files = sorted(glob.glob(os.path.join(logger_dir, "*.csv")))
    records = []
    for f in files:
        try:
            df = pd.read_csv(f, usecols=["UnixTime", "EngTrq"])
            if df["EngTrq"].isna().all():
                continue
            ts = pd.to_datetime(df["UnixTime"], unit="ms", utc=True)
            records.append({
                "file_path": f,
                "start_ts": ts.min(),
                "end_ts": ts.max(),
                "n_rows": len(df),
            })
        except Exception:
            pass
    idx = pd.DataFrame(records)
    idx = idx.sort_values("start_ts").reset_index(drop=True)
    print(f"[Logger 索引] {len(idx)} 个有效文件, "
          f"{idx['start_ts'].min()} → {idx['end_ts'].max()}")
    return idx


# ── Telematics 加载 ──────────────────────────────────────────────────────────
def load_telematics(vehicle_id: int) -> pd.DataFrame:
    """加载 vehicleId 对应的所有 telematics 记录。"""
    srf_dir = os.path.join(ROOT, CFG["paths"]["srf_raw_dir"])
    dfs = []
    for f in sorted(glob.glob(os.path.join(srf_dir, "*.csv"))):
        try:
            tmp = pd.read_csv(f, nrows=1, usecols=["vehicleId"])
            if int(tmp["vehicleId"].iloc[0]) == vehicle_id:
                df = pd.read_csv(f, low_memory=False)
                dfs.append(df)
        except Exception:
            pass
    if not dfs:
        return pd.DataFrame()
    all_df = pd.concat(dfs, ignore_index=True)
    all_df["eventDatetime"] = pd.to_datetime(all_df["eventDatetime"])
    all_df = all_df.sort_values("eventDatetime").reset_index(drop=True)
    # 去重（同一时间戳可能出现在多个文件中）
    all_df = all_df.drop_duplicates(subset=["eventDatetime"]).reset_index(drop=True)
    print(f"[Telematics] {len(all_df)} 行 (去重后)")
    return all_df


# ── 从 logger 索引中加载指定时间窗口的数据 ────────────────────────────────────
def load_logger_window(logger_idx: pd.DataFrame,
                       t_start: pd.Timestamp,
                       t_end: pd.Timestamp) -> pd.DataFrame:
    """
    加载覆盖 [t_start, t_end] 的 logger 数据行。
    返回已排序、已转换时间戳的 DataFrame。
    """
    # 找出时间上有重叠的文件
    overlap = logger_idx[
        (logger_idx["end_ts"] >= t_start) & (logger_idx["start_ts"] <= t_end)
    ]
    if overlap.empty:
        return pd.DataFrame()

    dfs = []
    for _, row in overlap.iterrows():
        df = pd.read_csv(row["file_path"])
        df["timestamp"] = pd.to_datetime(df["UnixTime"], unit="ms", utc=True)
        mask = (df["timestamp"] >= t_start) & (df["timestamp"] <= t_end)
        dfs.append(df.loc[mask])

    if not dfs:
        return pd.DataFrame()
    result = pd.concat(dfs, ignore_index=True)
    result = result.sort_values("timestamp").reset_index(drop=True)
    return result


# ── 窗口搜索 ──────────────────────────────────────────────────────────────
def find_valid_windows(tele_df: pd.DataFrame,
                       logger_idx: pd.DataFrame) -> pd.DataFrame:
    """
    遍历 telematics 相邻采样对，寻找同时有 logger 覆盖的有效窗口。
    """
    recup_col = CFG["telematics_cols"]["recup_wh"]
    recup_sec_col = CFG["telematics_cols"]["recup_sec"]
    wf = CFG["window_filter"]

    # 只保留 recuperation 有效的行
    valid_tele = tele_df.dropna(subset=[recup_col]).copy()
    valid_tele = valid_tele.sort_values("eventDatetime").reset_index(drop=True)
    print(f"[窗口搜索] 有效 telematics 行: {len(valid_tele)}")

    # Logger 时间范围
    logger_start = logger_idx["start_ts"].min()
    logger_end = logger_idx["end_ts"].max()

    windows = []
    for i in range(len(valid_tele) - 1):
        row0 = valid_tele.iloc[i]
        row1 = valid_tele.iloc[i + 1]

        t0 = row0["eventDatetime"]
        t1 = row1["eventDatetime"]
        dt_s = (t1 - t0).total_seconds()

        # 时间差筛选
        if dt_s < wf["min_duration_s"] or dt_s > wf["max_duration_s"]:
            continue

        # 时间窗口必须在 logger 覆盖范围内
        if t1 < logger_start or t0 > logger_end:
            continue

        # Recuperation 差值
        recup0 = row0[recup_col]
        recup1 = row1[recup_col]
        delta_recup = recup1 - recup0
        if delta_recup <= wf["min_recup_delta_wh"]:
            continue

        # 加载 logger 数据检查覆盖率
        logger_win = load_logger_window(logger_idx, t0, t1)
        if logger_win.empty:
            continue

        # 覆盖率 = 有效 logger 行数 / 预期行数（1Hz，dt_s 行）
        expected_rows = dt_s
        coverage = len(logger_win) / expected_rows

        if coverage < wf["min_logger_coverage"]:
            continue

        # 必须有行驶（速度 > 0）
        speed_col = CFG["logger_cols"]["speed"]
        if speed_col not in logger_win.columns:
            continue
        moving = (logger_win[speed_col] > 0).sum()
        if moving == 0:
            continue

        # 统计窗口特征
        brake_col = CFG["logger_cols"]["brake_pedal"]
        brake_sw_col = CFG["logger_cols"]["brake_switch"]
        eng_trq_col = CFG["logger_cols"]["engine_torque_pct"]

        brake_events = (logger_win[brake_col] > 5).sum() if brake_col in logger_win.columns else 0
        brake_switch_events = (logger_win[brake_sw_col] == 1).sum() if brake_sw_col in logger_win.columns else 0
        max_speed = logger_win[speed_col].max()
        mean_speed = logger_win.loc[logger_win[speed_col] > 0, speed_col].mean()

        # EngTrq 负值样本数（电动车中 EngTrq 可能不负，但检查一下）
        eng_trq_zero = (logger_win[eng_trq_col] == 0).sum() if eng_trq_col in logger_win.columns else 0

        # Recuperation 时间差
        recup_sec0 = row0.get(recup_sec_col, np.nan)
        recup_sec1 = row1.get(recup_sec_col, np.nan)
        delta_recup_sec = recup_sec1 - recup_sec0 if pd.notna(recup_sec0) and pd.notna(recup_sec1) else np.nan

        # 质量
        mass_col = CFG["logger_cols"]["mass"]
        mass_median = logger_win[mass_col].median() if mass_col in logger_win.columns else np.nan

        windows.append({
            "window_idx": len(windows),
            "t_start": t0,
            "t_end": t1,
            "duration_s": dt_s,
            "duration_min": round(dt_s / 60, 1),
            "recup_wh_start": recup0,
            "recup_wh_end": recup1,
            "delta_recup_wh": delta_recup,
            "delta_recup_sec": delta_recup_sec,
            "logger_rows": len(logger_win),
            "logger_coverage": round(coverage, 3),
            "moving_rows": int(moving),
            "max_speed_kmh": round(float(max_speed), 1),
            "mean_speed_kmh": round(float(mean_speed), 1) if pd.notna(mean_speed) else np.nan,
            "brake_pedal_events": int(brake_events),
            "brake_switch_events": int(brake_switch_events),
            "eng_trq_zero_count": int(eng_trq_zero),
            "mass_median_kg": round(float(mass_median), 0) if pd.notna(mass_median) else np.nan,
        })

    result = pd.DataFrame(windows)
    print(f"[窗口搜索] 找到 {len(result)} 个有效窗口")
    return result


# ── 主函数 ──────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("YK73WFN 再生制动分析 — Step 2: 寻找有效分析窗口")
    print("=" * 60)

    # 构建 logger 索引
    logger_idx = build_logger_index()

    # 加载 telematics
    vehicle_id = CFG["vehicle"]["vehicleId"]
    tele_df = load_telematics(vehicle_id)
    if tele_df.empty:
        print("Telematics 数据为空，退出。")
        sys.exit(1)

    # 搜索窗口
    windows_df = find_valid_windows(tele_df, logger_idx)

    if windows_df.empty:
        print("未找到有效窗口！请检查筛选条件。")
        sys.exit(1)

    # 保存
    out_path = os.path.join(TABLES_DIR, "valid_windows.csv")
    windows_df.to_csv(out_path, index=False)
    print(f"\n有效窗口已保存: {out_path}")
    print(f"总计 {len(windows_df)} 个窗口")
    print(windows_df[["window_idx", "t_start", "duration_min",
                       "delta_recup_wh", "logger_coverage",
                       "max_speed_kmh", "brake_pedal_events"]].to_string(index=False))
    print("\nStep 2 完成。")


if __name__ == "__main__":
    main()
