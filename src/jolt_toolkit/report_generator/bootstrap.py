"""
Project setup utilities (config + logging).

Keep this module small and stable: `main.py` should stay lightweight and import from here.
"""

from __future__ import annotations

import logging


def bootstrap() -> AppContext:
    project_root = get_project_root()

    load_dotenv(project_root / ".env")
    setup_logging(None, project_root=project_root)

    config_path = resolve_config_path(project_root)
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    config = load_json(config_path)
    setup_logging(config, project_root=project_root)
    _LOG.info("Loaded config: %s", config_path)

    return AppContext(project_root=project_root, config_path=config_path, config=config)
