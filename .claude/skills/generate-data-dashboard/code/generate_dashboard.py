"""Thin CLI runner for the skill-owned data-availability dashboard.

Behaviourally identical to the former
``python -m jolt_toolkit.report_generator.data_dashboard`` (same argument
surface: ``--version`` / ``--db-root`` / ``--out`` / ``--details none|all|REG,…``
/ ``--fetch-uplot``); the dashboard code now lives in this skill directory
(v3.1.0 re-homing) and only imports jolt_toolkit for shared names
(HEADERS/DIESEL_HEADERS, segmentation constants, config loaders).

Usage (from the repo root, jolt_toolkit importable — conda ``jolt`` env or
``PYTHONPATH=src``)::

    python .claude/skills/generate-data-dashboard/code/generate_dashboard.py \
        --version 2.2.8 [--db-root <reports root>] [--out <html path>] \
        [--details none|all|REG,REG]

No paid weather/OpenWeather API is touched — the only (optional, one-off)
network step is ``--fetch-uplot`` for the vendored chart library.
"""

import sys
from pathlib import Path

# Make the sibling modules importable regardless of how this file is invoked.
_CODE_DIR = Path(__file__).resolve().parent
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

from data_dashboard import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
