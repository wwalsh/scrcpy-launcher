# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.main import _portableapps_smoke_test
from src.paths import PORTABLEAPPS_DATA_ENV


def close_log_handlers() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()


class PortableAppsSmokeTests(unittest.TestCase):
    def tearDown(self) -> None:
        close_log_handlers()

    def _package(self, directory: str) -> tuple[Path, Path, Path]:
        package = Path(directory) / "scrcpy-launcherPortable"
        executable = package / "App" / "scrcpy-launcher" / "scrcpy-launcher.exe"
        default = package / "App" / "DefaultData" / "config.json"
        data_dir = package / "Data"
        executable.parent.mkdir(parents=True)
        default.parent.mkdir(parents=True)
        default.write_text(
            '{"schema_version":2,"scrcpy_mode":"bundled",'
            '"scrcpy_path":"scrcpy.exe","sessions":[]}',
            encoding="utf-8",
        )
        return executable, default, data_dir

    def test_smoke_mode_seeds_and_uses_package_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable, _default, data_dir = self._package(directory)
            config_path = data_dir / "config.json"
            with patch.object(sys, "frozen", True, create=True), patch.object(
                sys, "executable", str(executable)
            ), patch.dict(os.environ, {PORTABLEAPPS_DATA_ENV: str(data_dir)}):
                try:
                    result = _portableapps_smoke_test(str(config_path))
                finally:
                    close_log_handlers()

            self.assertEqual(result, 0)
            self.assertTrue(config_path.is_file())
            self.assertTrue((data_dir / "logs" / "portableapps-smoke.log").is_file())

    def test_smoke_mode_rejects_data_outside_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable, _default, _data_dir = self._package(directory)
            unrelated_data = Path(directory) / "unrelated-data"
            with patch.object(sys, "frozen", True, create=True), patch.object(
                sys, "executable", str(executable)
            ), patch.dict(
                os.environ,
                {PORTABLEAPPS_DATA_ENV: str(unrelated_data)},
            ):
                try:
                    result = _portableapps_smoke_test(
                        str(unrelated_data / "config.json")
                    )
                finally:
                    close_log_handlers()

            self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
