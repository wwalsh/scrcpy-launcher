# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.autostart import (
    AutostartError,
    AutostartManager,
    AutostartStatus,
    AutostartUnavailableError,
    VALUE_NAME,
    _delete_registration,
    _read_registration,
    _write_registration,
    create_autostart_manager,
)
from src.paths import PORTABLEAPPS_DATA_ENV


class AutostartTests(unittest.TestCase):
    def _manager(self, directory: str) -> AutostartManager:
        return AutostartManager(
            Path(directory) / "scrcpy launcher.exe",
            Path(directory) / "config file.json",
        )

    def test_expected_command_quotes_paths_and_selects_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self._manager(directory)

            self.assertEqual(
                manager.expected_command,
                f'"{(Path(directory) / "scrcpy launcher.exe").resolve()}" '
                f'--config "{(Path(directory) / "config file.json").resolve()}"',
            )

    def test_state_distinguishes_disabled_enabled_and_stale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self._manager(directory)
            with patch("src.autostart._read_registration", return_value=None):
                self.assertIs(manager.state().status, AutostartStatus.DISABLED)
            with patch(
                "src.autostart._read_registration",
                return_value=manager.expected_command.upper(),
            ):
                self.assertIs(manager.state().status, AutostartStatus.ENABLED)
            with patch("src.autostart._read_registration", return_value="old command"):
                state = manager.state()
                self.assertIs(state.status, AutostartStatus.STALE)
                self.assertEqual(state.registered_command, "old command")

    def test_apply_enables_or_disables_registration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self._manager(directory)
            with patch("src.autostart._write_registration") as write:
                manager.apply(True)
                write.assert_called_once_with(manager.expected_command)
            with patch("src.autostart._delete_registration") as delete:
                manager.apply(False)
                delete.assert_called_once_with()

    @patch("src.autostart.is_frozen", return_value=False)
    def test_source_mode_is_unavailable(self, _frozen) -> None:
        with self.assertRaises(AutostartUnavailableError):
            create_autostart_manager("config.json")

    @patch("src.autostart.is_frozen", return_value=True)
    @patch("src.paths.sys.frozen", True, create=True)
    def test_portableapps_mode_is_unavailable(self, _frozen) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {PORTABLEAPPS_DATA_ENV: directory}
        ):
            with self.assertRaisesRegex(
                AutostartUnavailableError,
                "PortableApps.com edition",
            ):
                create_autostart_manager(Path(directory) / "config.json")

    @patch("src.autostart.winreg.OpenKey", side_effect=FileNotFoundError)
    def test_missing_registry_value_reads_as_disabled(self, _open_key) -> None:
        self.assertIsNone(_read_registration())

    @patch("src.autostart.winreg.SetValueEx")
    @patch("src.autostart.winreg.CreateKeyEx")
    def test_registry_write_uses_current_user_run_value(self, create_key, set_value) -> None:
        key = MagicMock()
        create_key.return_value.__enter__.return_value = key

        _write_registration("expected command")

        set_value.assert_called_once()
        self.assertEqual(set_value.call_args.args[0], key)
        self.assertEqual(set_value.call_args.args[1], VALUE_NAME)
        self.assertEqual(set_value.call_args.args[4], "expected command")

    @patch("src.autostart.winreg.OpenKey", side_effect=OSError("denied"))
    def test_registry_errors_are_actionable(self, _open_key) -> None:
        with self.assertRaisesRegex(AutostartError, "Could not read"):
            _read_registration()

    @patch("src.autostart.winreg.OpenKey", side_effect=FileNotFoundError)
    def test_deleting_missing_registration_is_idempotent(self, _open_key) -> None:
        _delete_registration()


if __name__ == "__main__":
    unittest.main()
