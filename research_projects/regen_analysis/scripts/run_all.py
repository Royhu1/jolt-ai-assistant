"""
run_all.py — 一键运行 YK73WFN 再生制动分析全流程
"""
from __future__ import annotations

import subprocess
import sys
import os
import time

# Windows 编码兼容
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(SCRIPTS_DIR, "..", "..", ".."))

STEPS = [
    ("01_data_explore.py",   "数据探索"),
    ("02_find_windows.py",   "寻找有效分析窗口"),
    ("03_energy_model.py",   "能耗模型参数标定"),
    ("04_regen_analysis.py", "单窗口精细分析"),
    ("05_full_analysis.py",  "全数据集统计分析"),
]


def main():
    print("=" * 60)
    print("YK73WFN 再生制动分析 — 全流程运行")
    print("=" * 60)

    overall_start = time.time()
    for script_name, description in STEPS:
        script_path = os.path.join(SCRIPTS_DIR, script_name)
        print(f"\n{'─' * 50}")
        print(f"▶ {script_name}: {description}")
        print(f"{'─' * 50}")

        t0 = time.time()
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=ROOT,
            capture_output=False,
        )
        elapsed = time.time() - t0
        if result.returncode != 0:
            print(f"\n✗ {script_name} 失败 (返回码 {result.returncode})，中止流程。")
            sys.exit(result.returncode)
        print(f"✓ {script_name} 完成 ({elapsed:.1f}s)")

    total = time.time() - overall_start
    print(f"\n{'=' * 60}")
    print(f"全流程完成，总耗时 {total:.1f}s")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
