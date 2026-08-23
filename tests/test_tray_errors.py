# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src import tray
from src.config import ConfigError, Session
from src.launcher import SessionLaunchError
from src.scrcpy_runtime import ScrcpyResolution, ScrcpyResolutionError


class TrayErrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_state = tray._state

    def tearDown(self) -> None:
        tray._state = self._original_state

    @patch("src.tray.show_error")
    @patch("src.tray.load_config", side_effect=ConfigError("broken config"))
    @patch("src.tray.win32gui.DestroyMenu")
    @patch("src.tray.win32gui.TrackPopupMenu", return_value=0)
    @patch("src.tray.win32gui.SetForegroundWindow")
    @patch("src.tray.win32gui.AppendMenu")
    @patch("src.tray.win32gui.CreatePopupMenu", return_value=1)
    @patch("src.tray.win32gui.GetCursorPos", return_value=(0, 0))
    def test_reload_error_retains_last_good_config(
        self,
        _cursor,
        _create,
        _append,
        _foreground,
        _track,
        _destroy,
        _load,
        show_error,
    ) -> None:
        last_good = Mock()
        last_good.config_path = "config.json"
        last_good.sessions = (Session("Phone", []),)
        tray._state = last_good

        with self.assertLogs("src.tray", level="ERROR"):
            tray._show_menu(123)

        self.assertIs(tray._state, last_good)
        self.assertIn("broken config", show_error.call_args.args[1])

    @patch("src.tray.show_error")
    @patch("src.tray.launch_session", side_effect=SessionLaunchError("missing executable"))
    def test_immediate_launch_error_is_visible(self, _launch, show_error) -> None:
        with self.assertLogs("src.tray", level="ERROR"):
            tray._launch_session("missing.exe", Session("Phone", []))

        self.assertIn("Phone", show_error.call_args.args[1])
        self.assertIn("missing executable", show_error.call_args.args[1])

    @patch("src.tray.show_error")
    @patch("src.tray.launch_session")
    def test_asynchronous_launch_error_is_visible(self, launch, show_error) -> None:
        def invoke_callback(_path, _args, callback):
            callback(SessionLaunchError("adb unauthorized"))

        launch.side_effect = invoke_callback

        with self.assertLogs("src.tray", level="ERROR"):
            tray._launch_session("scrcpy.exe", Session("Phone", []))

        self.assertIn("adb unauthorized", show_error.call_args.args[1])

    @patch("src.tray._launch_configured_session")
    def test_left_click_launches_first_ordered_session(self, launch) -> None:
        config = Mock()
        config.sessions = (Session("First", ["--serial=1"]), Session("Second", []))

        tray._launch_first_session(config)

        launch.assert_called_once_with(config, config.sessions[0])

    @patch("src.tray._launch_session")
    @patch("src.tray.resolve_scrcpy")
    def test_configured_launch_uses_resolved_executable(self, resolve, launch) -> None:
        config = Mock(scrcpy_mode="bundled", scrcpy_path="scrcpy.exe")
        resolution = ScrcpyResolution(Path("C:/app/tools/scrcpy/scrcpy.exe"), "bundled", "bundled")
        resolve.return_value = resolution
        session = Session("Phone", [])

        tray._launch_configured_session(config, session)

        launch.assert_called_once_with(str(resolution.path), session)

    @patch("src.tray.show_error")
    @patch("src.tray._launch_session")
    @patch("src.tray.resolve_scrcpy", side_effect=ScrcpyResolutionError("repair install"))
    def test_resolution_error_is_visible_before_launch(self, _resolve, launch, show_error) -> None:
        config = Mock(scrcpy_mode="bundled", scrcpy_path="scrcpy.exe")

        tray._launch_configured_session(config, Session("Phone", []))

        launch.assert_not_called()
        self.assertIn("repair install", show_error.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
