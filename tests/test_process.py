# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import io
import subprocess
import unittest
from unittest.mock import Mock, patch

from src.process import hidden_process_kwargs, read_bounded_text, run_hidden


class ProcessHelperTests(unittest.TestCase):
    @patch("src.process.subprocess.Popen")
    def test_run_hidden_applies_common_text_and_window_options(self, popen) -> None:
        process = Mock()
        process.stdout = io.StringIO("output")
        process.stderr = io.StringIO("")
        process.wait.return_value = 0
        popen.return_value = process

        result = run_hidden(["adb.exe", "devices"], timeout=5)

        self.assertEqual(result.args, ["adb.exe", "devices"])
        self.assertEqual(result.stdout, "output")
        self.assertEqual(popen.call_args.args[0], ["adb.exe", "devices"])
        options = popen.call_args.kwargs
        self.assertIs(options["stdout"], subprocess.PIPE)
        self.assertIs(options["stderr"], subprocess.PIPE)
        self.assertTrue(options["text"])
        self.assertEqual(options["encoding"], "utf-8")
        self.assertEqual(options["errors"], "replace")
        self.assertNotIn("timeout", options)
        self.assertNotIn("check", options)
        self.assertEqual(
            options["creationflags"], getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )

    @patch("src.process.subprocess.Popen")
    def test_run_hidden_supports_explicit_streams(self, popen) -> None:
        process = Mock()
        process.stdout = None
        process.stderr = io.StringIO("")
        process.wait.return_value = 0
        popen.return_value = process

        run_hidden(
            ["adb.exe", "kill-server"],
            capture_output=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        options = popen.call_args.kwargs
        self.assertNotIn("capture_output", options)
        self.assertIs(options["stdout"], subprocess.DEVNULL)
        self.assertIs(options["stderr"], subprocess.PIPE)

    def test_hidden_process_kwargs_contains_no_console_flag(self) -> None:
        self.assertEqual(
            hidden_process_kwargs(),
            {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)},
        )

    def test_read_bounded_text_drains_and_marks_truncated_output(self) -> None:
        self.assertEqual(
            read_bounded_text(io.StringIO("0123456789"), 4),
            "0123\n…[output truncated]",
        )


if __name__ == "__main__":
    unittest.main()
