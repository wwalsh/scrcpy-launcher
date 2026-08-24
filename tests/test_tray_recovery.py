# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import ctypes
import unittest
from unittest.mock import Mock, call, patch

from src import tray


class TrayRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_message = tray._taskbar_created_message
        self._original_title = tray._tray_title
        self._original_icon = tray._tray_icon_handle

    def tearDown(self) -> None:
        tray._taskbar_created_message = self._original_message
        tray._tray_title = self._original_title
        tray._tray_icon_handle = self._original_icon

    @patch("src.tray.win32gui.DefWindowProc", return_value=91)
    @patch("src.tray._restore_icon")
    def test_unrelated_message_does_not_restore_icon(self, restore, default_proc) -> None:
        tray._taskbar_created_message = 5000

        result = tray._wnd_proc(101, 4999, 2, 3)

        self.assertEqual(result, 91)
        restore.assert_not_called()
        default_proc.assert_called_once_with(101, 4999, 2, 3)

    @patch("src.tray._restore_icon", return_value=True)
    def test_taskbar_created_message_restores_icon_once(self, restore) -> None:
        tray._taskbar_created_message = 5000

        result = tray._wnd_proc(101, 5000, 0, 0)

        self.assertEqual(result, 0)
        restore.assert_called_once_with(101)

    @patch("src.tray._load_icon")
    @patch("src.tray._add_icon", return_value=True)
    def test_repeated_recovery_reuses_loaded_icon(self, add_icon, load_icon) -> None:
        tray._tray_title = "Phone"
        tray._tray_icon_handle = 303

        self.assertTrue(tray._restore_icon(101))
        self.assertTrue(tray._restore_icon(101))

        self.assertEqual(
            add_icon.call_args_list,
            [call(101, "Phone", 303), call(101, "Phone", 303)],
        )
        load_icon.assert_not_called()

    @patch("src.tray._shell32.Shell_NotifyIconW", return_value=1)
    def test_icon_registration_preserves_callback_and_identity(self, notify) -> None:
        self.assertTrue(tray._add_icon(101, "Phone", 303))

        operation, data_pointer = notify.call_args.args
        data = ctypes.cast(
            data_pointer,
            ctypes.POINTER(tray._NOTIFYICONDATAW),
        ).contents
        self.assertEqual(operation, tray.NIM_ADD)
        self.assertEqual(data.hWnd, 101)
        self.assertEqual(data.uID, 0)
        self.assertEqual(data.uCallbackMessage, tray.WM_NOTIFY)
        self.assertEqual(data.hIcon, 303)
        self.assertEqual(data.szTip, "Phone")

    @patch("src.tray._add_icon", side_effect=OSError("shell unavailable"))
    def test_recovery_failure_is_logged_and_nonfatal(self, _add_icon) -> None:
        tray._tray_title = "Phone"
        tray._tray_icon_handle = 303

        with self.assertLogs("src.tray", level="ERROR"):
            restored = tray._restore_icon(101)

        self.assertFalse(restored)

    @patch("src.tray._add_icon", return_value=False)
    def test_rejected_recovery_is_logged_and_nonfatal(self, _add_icon) -> None:
        tray._tray_title = "Phone"
        tray._tray_icon_handle = 303

        with self.assertLogs("src.tray", level="ERROR"):
            restored = tray._restore_icon(101)

        self.assertFalse(restored)

    @patch("src.tray._log_scrcpy_selection")
    @patch("src.tray.win32gui.GetModuleHandle", return_value=404)
    @patch("src.tray.win32gui.UnregisterClass")
    @patch("src.tray.win32gui.DestroyWindow")
    @patch("src.tray.win32gui.DestroyIcon")
    @patch("src.tray._hide_icon")
    @patch("src.tray.win32gui.PumpMessages")
    @patch("src.tray._add_icon", return_value=True)
    @patch("src.tray._load_icon", return_value=303)
    @patch("src.tray._create_window", return_value=202)
    @patch("src.tray._register_window_class", return_value=101)
    @patch("src.tray.win32gui.RegisterWindowMessage", return_value=5000)
    def test_shutdown_order_and_runtime_state_cleanup(
        self,
        _register_message,
        _register_class,
        _create_window,
        _load_icon,
        _add_icon,
        _pump,
        hide_icon,
        destroy_icon,
        destroy_window,
        unregister_class,
        _module_handle,
        _log_selection,
    ) -> None:
        events: list[str] = []
        hide_icon.side_effect = lambda _hwnd: events.append("hide")
        destroy_icon.side_effect = lambda _hicon: events.append("destroy-icon")
        destroy_window.side_effect = lambda _hwnd: events.append("destroy-window")
        unregister_class.side_effect = lambda _name, _instance: events.append("unregister")
        config = Mock()
        config.sessions = []

        tray.run_tray(config)

        self.assertEqual(events, ["hide", "destroy-icon", "destroy-window", "unregister"])
        _add_icon.assert_called_once_with(202, "scrcpy", 303)
        self.assertIsNone(tray._taskbar_created_message)
        self.assertEqual(tray._tray_title, "")
        self.assertEqual(tray._tray_icon_handle, 0)

    @patch("src.tray._log_scrcpy_selection")
    @patch("src.tray.win32gui.GetModuleHandle", return_value=404)
    @patch("src.tray.win32gui.UnregisterClass")
    @patch("src.tray._create_window", side_effect=OSError("window unavailable"))
    @patch("src.tray._register_window_class", return_value=101)
    @patch("src.tray.win32gui.RegisterWindowMessage", return_value=5000)
    def test_partial_initialization_unregisters_class_and_clears_state(
        self,
        _register_message,
        _register_class,
        _create_window,
        unregister_class,
        _module_handle,
        _log_selection,
    ) -> None:
        config = Mock()
        config.sessions = []

        with self.assertRaisesRegex(OSError, "window unavailable"):
            tray.run_tray(config)

        unregister_class.assert_called_once_with(tray._WINDOW_CLASS, 404)
        self.assertIsNone(tray._taskbar_created_message)
        self.assertEqual(tray._tray_title, "")
        self.assertEqual(tray._tray_icon_handle, 0)


if __name__ == "__main__":
    unittest.main()
