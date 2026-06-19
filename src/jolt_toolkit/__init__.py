"""
JOLT Toolkit — 电动重卡遥测数据工具包。

子包：
  report_generator          报告生成管线
  vehicle_params_identificator  滚阻 / 风阻参数辨识
  analysis                  从 data_analysis_workspace 子项目上提的共享分析工具

分析图绘制：
  data_analysis_workspace/scripts/generate_figures.py  — Excel 报告分析图（独立脚本，替代原 excel_plotter）
"""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("jolt-toolkit")
except PackageNotFoundError:
    # 未安装时 fallback：从 pyproject.toml 读取
    from pathlib import Path as _Path
    import re as _re
    _pyproject = _Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
    _m = _re.search(r'^version\s*=\s*"([^"]+)"', _pyproject.read_text(), _re.MULTILINE)
    __version__ = _m.group(1) if _m else "0.0.0"
