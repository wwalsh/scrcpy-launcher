# SPDX-License-Identifier: GPL-3.0-only

"""Entry point for the settings UI process.

Launched as a separate process from the tray application.
Runs the tkinter settings dialog and exits when the user closes it.
"""

from __future__ import annotations

import logging
import sys

from .logging_setup import setup_logging
from .settings import show_settings
from .winui import show_error

logger = logging.getLogger(__name__)


def main() -> int:
    config_path = sys.argv[1] if len(sys.argv) >= 2 else None
    return run_settings(config_path)


def run_settings(config_path: str | None) -> int:
    """Run Settings for a resolved configuration path without owning the tray mutex."""
    log_path = setup_logging("settings")
    if config_path is None:
        message = "Usage: python -m src.settings_main <config_path>"
        logger.error(message)
        show_error("scrcpy-launcher Settings Error", f"{message}\n\nLog: {log_path}")
        return 1
    try:
        show_settings(config_path)
    except Exception as exc:
        logger.exception("Settings failed")
        show_error(
            "scrcpy-launcher Settings Error",
            f"Settings could not be opened:\n\n{exc}\n\nLog: {log_path}",
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
