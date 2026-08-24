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
    PORTABLEAPPS_DATA_ENV,
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

    def test_portableapps_package_uses_launcher_data_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {PORTABLEAPPS_DATA_ENV: directory}
        ):
            result = resolve_config_path(frozen=True)

            self.assertEqual(result, Path(directory).resolve() / "config.json")

    def test_portableapps_environment_is_ignored_in_source_mode(self) -> None:
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {PORTABLEAPPS_DATA_ENV: str(Path(directory) / "Data")}
        ):
            os.chdir(directory)
            try:
                result = resolve_config_path(frozen=False)
            finally:
                os.chdir(previous)

            self.assertEqual(result, (Path(directory) / "config.json").resolve())

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

    def test_portableapps_first_run_seeds_data_config_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "scrcpy-launcherPortable"
            executable = package / "App" / "scrcpy-launcher" / "scrcpy-launcher.exe"
            default_path = package / "App" / "DefaultData" / "config.json"
            data_dir = package / "Data"
            config_path = data_dir / "config.json"
            default = b'{"scrcpy_mode":"bundled"}\n'
            executable.parent.mkdir(parents=True)
            default_path.parent.mkdir(parents=True)
            default_path.write_bytes(default)

            with patch.dict(os.environ, {PORTABLEAPPS_DATA_ENV: str(data_dir)}):
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

    def test_portableapps_seed_rejects_an_unrelated_explicit_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {PORTABLEAPPS_DATA_ENV: str(Path(directory) / "Data")}
        ):
            self.assertFalse(
                seed_portable_config(
                    Path(directory) / "elsewhere.json",
                    frozen=True,
                    executable=Path(directory) / "App" / "app" / "app.exe",
                )
            )


if __name__ == "__main__":
    unittest.main()
