"""
JOLT Toolkit — telemetry data toolkit for electric heavy goods vehicles.

Sub-packages:
  report_generator              report-generation pipeline
  analysis                      shared analysis utilities promoted from the
                                data_analysis_workspace sub-projects

Analysis figures:
  data_analysis_workspace/scripts/generate_figures.py  — Excel report analysis
  figures (standalone script, replacing the former excel_plotter)
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("jolt-toolkit")
except PackageNotFoundError:
    # Fallback when not installed: read the version from pyproject.toml
    import re as _re
    from pathlib import Path as _Path

    _pyproject = _Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
    _m = _re.search(r'^version\s*=\s*"([^"]+)"', _pyproject.read_text(), _re.MULTILINE)
    __version__ = _m.group(1) if _m else "0.0.0"
