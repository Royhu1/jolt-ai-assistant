"""Standalone dispatcher kept for parity with the former
``python -m jolt_toolkit.vehicle_params_identificator``. Preferred entry:

    python research_projects/parameter_identify/code/run_identification.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_identification import main  # noqa: E402

main()
