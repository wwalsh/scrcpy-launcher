# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import unittest
from unittest.mock import patch

from src import winui


class WinUiTests(unittest.TestCase):
    @patch("src.winui.ctypes.windll.shell32.ShellExecuteW", return_value=33)
    def test_open_url_accepts_https_and_uses_default_browser(self, shell_execute) -> None:
        self.assertTrue(winui.open_url("https://example.com/project"))

        self.assertEqual(shell_execute.call_args.args[1], "open")
        self.assertEqual(shell_execute.call_args.args[2], "https://example.com/project")

    @patch("src.winui.ctypes.windll.shell32.ShellExecuteW")
    def test_open_url_rejects_non_https_without_shelling_out(self, shell_execute) -> None:
        with self.assertLogs("src.winui", level="ERROR"):
            self.assertFalse(winui.open_url("file:///C:/private.txt"))

        shell_execute.assert_not_called()

    @patch("src.winui.ctypes.windll.shell32.ShellExecuteW", return_value=31)
    def test_open_url_reports_shell_failure(self, _shell_execute) -> None:
        with self.assertLogs("src.winui", level="ERROR"):
            self.assertFalse(winui.open_url("https://example.com/project"))


if __name__ == "__main__":
    unittest.main()
