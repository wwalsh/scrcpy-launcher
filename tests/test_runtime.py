# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from src.runtime import resource_path, settings_launch_spec


class RuntimeTests(unittest.TestCase):
    @patch("src.runtime.is_frozen", return_value=False)
    def test_source_settings_uses_module_entrypoint(self, _frozen) -> None:
        spec = settings_launch_spec("C:/config.json")

        self.assertEqual(
            spec.command,
            [sys.executable, "-m", "src.settings_main", "C:/config.json"],
        )
        self.assertIsNotNone(spec.cwd)

    @patch("src.runtime.is_frozen", return_value=True)
    def test_frozen_settings_uses_same_executable(self, _frozen) -> None:
        spec = settings_launch_spec("C:/config.json")

        self.assertEqual(
            spec.command,
            [sys.executable, "--settings", "C:/config.json"],
        )
        self.assertIsNone(spec.cwd)

    @patch("src.runtime.is_frozen", return_value=True)
    def test_frozen_resource_uses_bundle_root(self, _frozen) -> None:
        with patch.object(sys, "_MEIPASS", "C:/bundle", create=True):
            self.assertEqual(resource_path("icon.ico"), Path("C:/bundle/icon.ico"))


if __name__ == "__main__":
    unittest.main()
