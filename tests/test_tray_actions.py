# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from src import tray
from src.config import Session
from src.winui import DialogChoice


class TrayActionTests(unittest.TestCase):
    @patch("src.tray.launch_session")
    @patch("src.tray._resolve_configured_scrcpy", return_value="C:/scrcpy.exe")
    def test_global_window_height_is_applied_to_all_launched_sessions(
        self, _resolve, launch
    ) -> None:
        config = Mock()
        config.window_height_enabled = True
        config.window_height = 720
        session = Session("Phone", ["--window-height=480", "--no-audio"])

        tray._launch_configured_session(config, session)

        launch.assert_called_once()
        self.assertEqual(
            launch.call_args.args[1],
            ["--window-height=720", "--no-audio"],
        )

    @patch("src.tray.shutil.which", return_value="adb.exe")
    @patch("src.tray._resolve_configured_scrcpy")
    def test_adb_lookup_reuses_menu_scrcpy_resolution(self, resolve, which) -> None:
        config = Mock()

        result = tray._resolve_adb_path(config, scrcpy_path="C:/app/scrcpy.exe")

        self.assertEqual(result, "adb.exe")
        resolve.assert_not_called()
        which.assert_called_once_with("adb.exe")

    def test_stop_all_sessions_delegates_to_launcher_manager(self) -> None:
        with patch("src.tray.stop_all_sessions", return_value=2) as stop:
            tray._stop_all_sessions()

        stop.assert_called_once_with()

    @patch("src.tray.stop_adb_server", return_value=True)
    @patch("src.tray._resolve_adb_path", return_value="C:/app/tools/adb.exe")
    @patch("src.tray.ask_yes_no_information", return_value=DialogChoice.YES)
    def test_stop_adb_server_requires_confirmation(
        self, ask, resolve, stop
    ) -> None:
        config = Mock()

        tray._stop_adb_server(config)

        ask.assert_called_once()
        resolve.assert_called_once_with(config)
        stop.assert_called_once_with("C:/app/tools/adb.exe")

    @patch("src.tray.stop_adb_server")
    @patch("src.tray._resolve_adb_path", return_value="C:/app/tools/adb.exe")
    @patch("src.tray.ask_yes_no_information", return_value=DialogChoice.NO)
    def test_stop_adb_server_does_not_run_when_declined(
        self, _ask, _resolve, stop
    ) -> None:
        tray._stop_adb_server(object())  # type: ignore[arg-type]

        stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
