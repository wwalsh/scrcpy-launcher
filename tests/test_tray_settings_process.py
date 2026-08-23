# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import Mock, patch

from src import tray


class TraySettingsProcessTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_process = tray._settings_process
        tray._settings_process = None

    def tearDown(self) -> None:
        tray._settings_process = self._original_process

    def test_running_process_is_open_and_finished_process_is_cleared(self) -> None:
        process = Mock(spec=subprocess.Popen)
        process.poll.return_value = None
        tray._settings_process = process

        self.assertTrue(tray._settings_is_open())

        process.poll.return_value = 0
        self.assertFalse(tray._settings_is_open())
        self.assertIsNone(tray._settings_process)

    @patch("src.tray.subprocess.Popen")
    def test_duplicate_spawn_is_prevented(self, popen) -> None:
        process = Mock()
        process.poll.return_value = None
        tray._settings_process = process

        started = tray._spawn_settings_process("config.json")

        self.assertFalse(started)
        popen.assert_not_called()

    @patch("src.tray.subprocess.Popen")
    def test_new_process_can_start_after_previous_process_exits(self, popen) -> None:
        finished = Mock()
        finished.poll.return_value = 0
        tray._settings_process = finished
        replacement = Mock()
        popen.return_value = replacement

        started = tray._spawn_settings_process("C:/config.json")

        self.assertTrue(started)
        self.assertIs(tray._settings_process, replacement)
        command = popen.call_args.args[0]
        self.assertEqual(command[1:3], ["-m", "src.settings_main"])
        self.assertEqual(command[3], "C:/config.json")

    @patch("src.tray.settings_launch_spec")
    @patch("src.tray.subprocess.Popen")
    def test_spawn_uses_runtime_launch_spec(self, popen, launch_spec) -> None:
        launch_spec.return_value.command = ["launcher.exe", "--settings", "C:/config.json"]
        launch_spec.return_value.cwd = None

        started = tray._spawn_settings_process("C:/config.json")

        self.assertTrue(started)
        popen.assert_called_once_with(launch_spec.return_value.command, cwd=None)

    @patch("src.tray._settings_is_open", return_value=True)
    def test_open_settings_disables_settings_and_quit(self, _is_open) -> None:
        settings_flags, settings_label, quit_flags, quit_label = tray._settings_menu_state()

        self.assertTrue(settings_flags & tray.win32con.MF_GRAYED)
        self.assertTrue(quit_flags & tray.win32con.MF_GRAYED)
        self.assertEqual(settings_label, "Settings (open)")
        self.assertEqual(quit_label, "Quit (close Settings first)")

    @patch("src.tray._settings_is_open", return_value=False)
    def test_closed_settings_restores_normal_menu(self, _is_open) -> None:
        settings_flags, settings_label, quit_flags, quit_label = tray._settings_menu_state()

        self.assertEqual(settings_flags, tray.win32con.MF_STRING)
        self.assertEqual(quit_flags, tray.win32con.MF_STRING)
        self.assertEqual(settings_label, "Settings")
        self.assertEqual(quit_label, "Quit")


if __name__ == "__main__":
    unittest.main()
