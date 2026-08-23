# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from src import tray
from src.update_check import (
    LATEST_RELEASE_URL,
    REPOSITORY_URL,
    UpdateCheckError,
    UpdateResult,
)
from src.winui import DialogChoice


class TrayAboutUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_thread = tray._update_check_thread
        tray._update_check_thread = None

    def tearDown(self) -> None:
        tray._update_check_thread = self._original_thread

    @patch("src.tray._open_project_url")
    @patch("src.tray.ask_yes_no_information", return_value=DialogChoice.YES)
    def test_about_displays_versions_and_can_open_project(self, ask, open_project) -> None:
        tray._show_about()

        message = ask.call_args.args[1]
        self.assertIn(tray.APP_VERSION, message)
        self.assertIn(tray.BUNDLED_SCRCPY_VERSION, message)
        self.assertIn("GPL-3.0-only", message)
        open_project.assert_called_once_with(REPOSITORY_URL)

    @patch("src.tray._open_project_url")
    @patch("src.tray.ask_yes_no_information", return_value=DialogChoice.NO)
    def test_about_does_not_open_project_when_declined(self, _ask, open_project) -> None:
        tray._show_about()

        open_project.assert_not_called()

    @patch("src.tray._open_project_url")
    @patch("src.tray.ask_yes_no_information", return_value=DialogChoice.YES)
    @patch("src.tray.check_latest_release")
    def test_available_update_can_open_latest_release(self, check, _ask, open_project) -> None:
        check.return_value = UpdateResult("0.7.1", "0.8.0", True)

        tray._run_update_check()

        open_project.assert_called_once_with(LATEST_RELEASE_URL)
        self.assertIsNone(tray._update_check_thread)

    @patch("src.tray.show_info")
    @patch("src.tray.check_latest_release")
    def test_current_version_reports_up_to_date(self, check, show_info) -> None:
        check.return_value = UpdateResult("0.7.1", "0.7.1", False)

        tray._run_update_check()

        self.assertIn("up to date", show_info.call_args.args[1])

    @patch("src.tray.show_error")
    @patch("src.tray.check_latest_release", side_effect=UpdateCheckError("offline"))
    def test_update_failure_is_nonfatal_and_visible(self, _check, show_error) -> None:
        with self.assertLogs("src.tray", level="WARNING"):
            tray._run_update_check()

        self.assertIn("offline", show_error.call_args.args[1])

    @patch("src.tray.threading.Thread")
    def test_start_update_check_creates_one_daemon_worker(self, thread_type) -> None:
        worker = Mock()
        thread_type.return_value = worker

        self.assertTrue(tray._start_update_check())

        thread_type.assert_called_once_with(
            target=tray._run_update_check,
            name="scrcpy-launcher-update-check",
            daemon=True,
        )
        worker.start.assert_called_once_with()

    def test_running_update_disables_menu_item(self) -> None:
        worker = Mock()
        worker.is_alive.return_value = True
        tray._update_check_thread = worker

        flags, label = tray._update_menu_state()

        self.assertTrue(flags & tray.win32con.MF_GRAYED)
        self.assertIn("in progress", label)


if __name__ == "__main__":
    unittest.main()
