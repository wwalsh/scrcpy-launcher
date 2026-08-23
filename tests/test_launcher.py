# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from src.launcher import SessionLaunchError, _ProcessManager


class LauncherTests(unittest.TestCase):
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
        thread.return_value.start.assert_called_once_with()

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

        with self.assertLogs("src.launcher", level="ERROR"):
            manager._monitor(process, callback)

        callback.assert_called_once()
        error = callback.call_args.args[0]
        self.assertIn("code 1", str(error))
        self.assertIn("more than one device", str(error))
        self.assertNotIn(process, manager._processes)

    def test_successful_exit_does_not_report_error(self) -> None:
        manager = _ProcessManager()
        process = Mock()
        process.communicate.return_value = (None, "normal diagnostic output")
        process.returncode = 0
        manager._processes.append(process)
        callback = Mock()

        manager._monitor(process, callback)

        callback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
