# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.logging_setup import log_path_for, redact_log_message, setup_logging
from src.paths import PORTABLEAPPS_DATA_ENV


class LoggingSetupTests(unittest.TestCase):
    def test_uses_local_app_data_component_log(self) -> None:
        with patch.dict("os.environ", {"LOCALAPPDATA": "C:/Users/Test/AppData/Local"}):
            path = log_path_for("tray")

        self.assertEqual(
            path,
            Path("C:/Users/Test/AppData/Local/scrcpy-launcher/tray.log"),
        )

    def test_setup_writes_persistent_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"LOCALAPPDATA": directory}
        ), patch("src.logging_setup.sys.stderr", None):
            path = setup_logging("test")
            logging.getLogger("test.logger").error("persistent diagnostic")
            root = logging.getLogger()
            handlers = list(root.handlers)
            for handler in handlers:
                handler.flush()

            self.assertIn("persistent diagnostic", path.read_text(encoding="utf-8"))

            for handler in handlers:
                root.removeHandler(handler)
                handler.close()

    def test_portableapps_logs_are_stored_under_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {PORTABLEAPPS_DATA_ENV: directory}
        ), patch("src.paths.sys.frozen", True, create=True):
            path = log_path_for("tray")

        self.assertEqual(path, Path(directory).resolve() / "logs" / "tray.log")

    def test_portableapps_logging_does_not_fall_back_to_host_temp(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {PORTABLEAPPS_DATA_ENV: directory}
        ), patch("src.paths.sys.frozen", True, create=True), patch(
            "src.logging_setup.Path.mkdir", side_effect=OSError("read only")
        ), patch("src.logging_setup.RotatingFileHandler") as file_handler, patch(
            "src.logging_setup.sys.stderr", None
        ):
            path = setup_logging("tray")

        self.assertEqual(path, Path(directory).resolve() / "logs" / "tray.log")
        file_handler.assert_not_called()

    def test_redacts_profile_paths_and_device_serials(self) -> None:
        message = (
            r"C:\Users\Alice\AppData --serial=ABC123 "
            "--serial XYZ789; Device PHONE-42 is unauthorized"
        )

        redacted = redact_log_message(message)

        self.assertNotIn("Alice", redacted)
        self.assertNotIn("ABC123", redacted)
        self.assertNotIn("XYZ789", redacted)
        self.assertNotIn("PHONE-42", redacted)
        self.assertIn("%USERPROFILE%", redacted)
        self.assertGreaterEqual(redacted.count("<redacted>"), 3)

    def test_persistent_formatter_redacts_exception_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"LOCALAPPDATA": directory}
        ), patch("src.logging_setup.sys.stderr", None):
            path = setup_logging("privacy")
            try:
                raise RuntimeError(
                    r"failed at C:\Users\Alice\private for device ABC123 is offline"
                )
            except RuntimeError:
                logging.getLogger("privacy.test").exception("operation failed")

            root = logging.getLogger()
            handlers = list(root.handlers)
            for handler in handlers:
                handler.flush()
            content = path.read_text(encoding="utf-8")

            self.assertNotIn("Alice", content)
            self.assertNotIn("ABC123", content)
            self.assertIn("%USERPROFILE%", content)
            self.assertIn("device <redacted> is offline", content)

            for handler in handlers:
                root.removeHandler(handler)
                handler.close()


if __name__ == "__main__":
    unittest.main()
