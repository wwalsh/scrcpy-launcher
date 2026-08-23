# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.paths import (
    PORTABLE_DEFAULT_CONFIG,
    PORTABLE_MARKER,
    resolve_config_path,
    seed_portable_config,
)


class PathTests(unittest.TestCase):
    def test_explicit_path_wins_in_source_and_frozen_modes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            explicit = Path(directory) / "custom.json"
            self.assertEqual(
                resolve_config_path(explicit, frozen=False),
                explicit.resolve(),
            )
            self.assertEqual(
                resolve_config_path(explicit, frozen=True),
                explicit.resolve(),
            )

    def test_source_default_is_config_in_current_directory(self) -> None:
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            os.chdir(directory)
            try:
                result = resolve_config_path(frozen=False)
            finally:
                os.chdir(previous)

            self.assertEqual(result, (Path(directory) / "config.json").resolve())

    def test_frozen_default_uses_roaming_app_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"APPDATA": directory}
        ):
            result = resolve_config_path(frozen=True)

            self.assertEqual(
                result,
                (Path(directory) / "scrcpy-launcher" / "config.json").resolve(),
            )

    def test_marked_portable_package_uses_adjacent_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "scrcpy-launcher.exe"
            (root / PORTABLE_MARKER).write_text("portable", encoding="ascii")

            result = resolve_config_path(frozen=True, executable=executable)

            self.assertEqual(result, root / "config.json")

    def test_portable_first_run_seeds_once_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "scrcpy-launcher.exe"
            config_path = root / "config.json"
            default = b'{"scrcpy_mode":"bundled"}\n'
            (root / PORTABLE_MARKER).write_text("portable", encoding="ascii")
            (root / PORTABLE_DEFAULT_CONFIG).write_bytes(default)

            self.assertTrue(
                seed_portable_config(
                    config_path,
                    frozen=True,
                    executable=executable,
                )
            )
            self.assertEqual(config_path.read_bytes(), default)
            config_path.write_bytes(b"user configuration")
            self.assertFalse(
                seed_portable_config(
                    config_path,
                    frozen=True,
                    executable=executable,
                )
            )
            self.assertEqual(config_path.read_bytes(), b"user configuration")


if __name__ == "__main__":
    unittest.main()
