# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _loaded_after(module: str, candidates: tuple[str, ...]) -> dict[str, bool]:
    expression = ";".join(
        [
            "import sys",
            f"import {module}",
            *[
                f"print({candidate!r}, {candidate!r} in sys.modules)"
                for candidate in candidates
            ],
        ]
    )
    completed = subprocess.run(
        [sys.executable, "-c", expression],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return {
        name: loaded == "True"
        for name, loaded in (line.split() for line in completed.stdout.splitlines())
    }


class ImportEfficiencyTests(unittest.TestCase):
    def test_main_import_does_not_initialize_mode_specific_ui_or_networking(self) -> None:
        loaded = _loaded_after(
            "src.main",
            ("src.tray", "src.settings", "tkinter", "src.update_check", "urllib.request"),
        )

        self.assertFalse(any(loaded.values()))

    def test_tray_import_does_not_initialize_update_networking(self) -> None:
        loaded = _loaded_after("src.tray", ("src.update_check", "urllib.request"))

        self.assertFalse(any(loaded.values()))

    def test_settings_mode_does_not_initialize_tray_or_update_networking(self) -> None:
        expression = ";".join(
            [
                "import sys",
                "import src.main as main",
                "import src.settings_main as settings_main",
                "settings_main.run_settings = lambda _path: 0",
                "sys.argv = ['launcher', '--settings', 'config.json']",
                "assert main.main() == 0",
                "print('src.tray', 'src.tray' in sys.modules)",
                "print('src.update_check', 'src.update_check' in sys.modules)",
                "print('urllib.request', 'urllib.request' in sys.modules)",
            ]
        )
        completed = subprocess.run(
            [sys.executable, "-c", expression],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )

        self.assertEqual(
            completed.stdout.splitlines(),
            ["src.tray False", "src.update_check False", "urllib.request False"],
        )


if __name__ == "__main__":
    unittest.main()
