# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import unittest
import sys
from unittest.mock import Mock, patch

from src.launcher import (
    SessionLaunchError,
    _ProcessManager,
    _StartupState,
    _process_has_visible_window,
)


class LauncherTests(unittest.TestCase):
    @patch.dict(sys.modules)
    def test_process_window_lookup_uses_win32process(self) -> None:
        win32gui = Mock()
        win32con = Mock(GW_OWNER=8)
        win32process = Mock()
        win32gui.IsWindowVisible.return_value = True
        win32gui.GetWindow.return_value = 0
        win32process.GetWindowThreadProcessId.return_value = (1, 123)
        win32gui.EnumWindows.side_effect = lambda callback, extra: callback(10, extra)
        sys.modules.update(
            {
                "win32gui": win32gui,
                "win32con": win32con,
                "win32process": win32process,
            }
        )

        self.assertTrue(_process_has_visible_window(123))
        win32process.GetWindowThreadProcessId.assert_called_once_with(10)

    @patch("src.launcher.threading.Thread")
    @patch("src.launcher.subprocess.Popen")
    def test_launch_starts_hidden_monitored_process(self, popen, thread) -> None:
        process = Mock()
        popen.return_value = process
        manager = _ProcessManager()
        callback = Mock()

        result = manager.launch("scrcpy.exe", ["--no-audio"], callback)

        self.assertIs(result, process)
        self.assertEqual(popen.call_args.args[0], ["scrcpy.exe", "--no-audio"])
        self.assertIsNotNone(popen.call_args.kwargs["stderr"])
        self.assertEqual(thread.return_value.start.call_count, 2)

    @patch("src.launcher.subprocess.Popen", side_effect=FileNotFoundError)
    def test_missing_executable_has_actionable_error(self, _popen) -> None:
        with self.assertRaisesRegex(SessionLaunchError, "executable not found"):
            _ProcessManager().launch("missing-scrcpy.exe", [])

    def test_nonzero_exit_reports_captured_stderr(self) -> None:
        manager = _ProcessManager()
        process = Mock()
        process.communicate.return_value = (None, "ERROR: more than one device")
        process.returncode = 1
        manager._processes.append(process)
        callback = Mock()
        startup_state = _StartupState()

        with self.assertLogs("src.launcher", level="ERROR"):
            manager._monitor(process, callback, startup_state)

        callback.assert_called_once()
        error = callback.call_args.args[0]
        self.assertIn("code 1", str(error))
        self.assertIn("more than one device", str(error))
        self.assertNotIn(process, manager._processes)

    def test_nonzero_exit_after_startup_does_not_report_error(self) -> None:
        manager = _ProcessManager()
        process = Mock()
        process.communicate.return_value = (None, "device disconnected")
        process.returncode = 1
        manager._processes.append(process)
        callback = Mock()
        startup_state = _StartupState()
        startup_state.suppress_errors.set()

        with self.assertLogs("src.launcher", level="INFO"):
            manager._monitor(process, callback, startup_state)

        callback.assert_not_called()

    def test_successful_exit_does_not_report_error(self) -> None:
        manager = _ProcessManager()
        process = Mock()
        process.communicate.return_value = (None, "normal diagnostic output")
        process.returncode = 0
        manager._processes.append(process)
        callback = Mock()

        manager._monitor(process, callback, _StartupState())

        callback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
