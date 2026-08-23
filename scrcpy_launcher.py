# SPDX-License-Identifier: GPL-3.0-only

"""PyInstaller-compatible application entry point."""

from src.main import main


if __name__ == "__main__":
    raise SystemExit(main())
