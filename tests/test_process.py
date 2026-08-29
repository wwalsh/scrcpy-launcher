# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from src.process import hidden_process_kwargs, run_hidden


class ProcessHelperTests(unittest.TestCase):
    @patch("src.process.subprocess.run")
    def test_run_hidden_applies_common_text_and_window_options(self, run) -> None:
        expected = subprocess.CompletedProcess(["adb.exe"], 0, "output", "")
        run.return_value = expected

        result = run_hidden(["adb.exe", "devices"], timeout=5)

        self.assertIs(result, expected)
        self.assertEqual(run.call_args.args[0], ["adb.exe", "devices"])
        options = run.call_args.kwargs
        self.assertTrue(options["capture_output"])
        self.assertTrue(options["text"])
        self.assertEqual(options["encoding"], "utf-8")
        self.assertEqual(options["errors"], "replace")
        self.assertEqual(options["timeout"], 5)
        self.assertFalse(options["check"])
        self.assertEqual(
            options["creationflags"], getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )

    @patch("src.process.subprocess.run")
    def test_run_hidden_supports_explicit_streams(self, run) -> None:
        run.return_value = subprocess.CompletedProcess([], 0, "", "")

        run_hidden(
            ["adb.exe", "kill-server"],
            capture_output=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        options = run.call_args.kwargs
        self.assertNotIn("capture_output", options)
        self.assertIs(options["stdout"], subprocess.DEVNULL)
        self.assertIs(options["stderr"], subprocess.PIPE)

    def test_hidden_process_kwargs_contains_no_console_flag(self) -> None:
        self.assertEqual(
            hidden_process_kwargs(),
            {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)},
        )


if __name__ == "__main__":
    unittest.main()
