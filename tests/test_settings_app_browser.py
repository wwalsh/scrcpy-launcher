# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import queue
import unittest
from concurrent.futures import Future
from unittest.mock import MagicMock, call, patch

from src.device_apps import DeviceApp
from src.devices import Device
from src.settings_app_selector import _AppSelectionDialog
from src.settings import (
    _SettingsDialog,
    _app_cache_key,
    _selected_start_app_value,
)


class _ImmediateExecutor:
    """Run submitted work immediately while preserving the executor contract."""

    def submit(self, function):
        future = Future()
        try:
            future.set_result(function())
        except BaseException as exc:
            future.set_exception(exc)
        return future

    def shutdown(self, *, wait, cancel_futures):
        pass


def _settings_shell() -> _SettingsDialog:
    dialog = object.__new__(_SettingsDialog)
    dialog._device_var = MagicMock()
    dialog._device_var.get.return_value = "Phone"
    dialog._device_by_label = {"Phone": "ABC"}
    dialog._detected_devices = [Device("ABC", "device")]
    dialog._device_loading = False
    dialog._app_request = 0
    dialog._app_loading = False
    dialog._app_poll_job = None
    dialog._app_cache = {}
    dialog._app_results = queue.Queue()
    dialog._device_poll_job = None
    dialog._device_results = queue.Queue()
    dialog._device_executor = _ImmediateExecutor()
    dialog._device_future = None
    dialog._app_executor = _ImmediateExecutor()
    dialog._app_future = None
    dialog._select_app_button = MagicMock()
    dialog._refresh_apps_button = MagicMock()
    dialog._app_status_var = MagicMock()
    dialog._mode_var = MagicMock()
    dialog._mode_var.get.return_value = "bundled"
    dialog._path_var = MagicMock()
    dialog._path_var.get.return_value = "retained.exe"
    dialog._dialog = MagicMock()
    dialog._dialog.winfo_exists.return_value = False
    dialog._start_app_var = MagicMock()
    dialog._start_app_var.get.return_value = ""
    return dialog


class SettingsAppBrowserTests(unittest.TestCase):
    @patch("src.settings.discover_device_apps")
    def test_uncached_selection_starts_background_discovery_without_mutating_session(
        self, discover
    ) -> None:
        shell = _settings_shell()
        apps = [DeviceApp("Example", "com.example.app", False)]
        discover.return_value = apps

        shell._select_device_app()

        discover.assert_called_once_with("bundled", "retained.exe", "ABC")
        key = shell._current_app_cache_key()
        self.assertEqual(shell._app_results.get_nowait(), (1, key, apps, "", True))
        self.assertTrue(shell._app_loading)
        shell._select_app_button.configure.assert_called_with(state="disabled")
        shell._refresh_apps_button.configure.assert_called_with(state="disabled")
        shell._start_app_var.set.assert_not_called()

    @patch("src.settings._AppSelectionDialog")
    @patch("src.settings.discover_device_apps")
    def test_cached_selection_opens_immediately_without_discovery(
        self, discover, chooser
    ) -> None:
        shell = _settings_shell()
        app = DeviceApp("Example", "com.example.app", False)
        shell._app_cache[shell._current_app_cache_key()] = [app]
        chooser.return_value.selected = None

        shell._select_device_app()

        discover.assert_not_called()
        chooser.assert_called_once_with(shell._dialog, [app])
        shell._start_app_var.set.assert_not_called()

    @patch("src.settings.discover_device_apps")
    def test_refresh_forces_discovery_when_cache_exists(self, discover) -> None:
        shell = _settings_shell()
        key = shell._current_app_cache_key()
        shell._app_cache[key] = [DeviceApp("Old", "com.example.old", False)]
        fresh = [DeviceApp("New", "com.example.new", False)]
        discover.return_value = fresh

        shell._refresh_device_apps()

        discover.assert_called_once_with("bundled", "retained.exe", "ABC")
        self.assertEqual(shell._app_results.get_nowait(), (1, key, fresh, "", False))

    @patch("src.settings._AppSelectionDialog")
    def test_stale_result_is_discarded_without_opening_browser(self, chooser) -> None:
        shell = _settings_shell()
        shell._app_request = 2
        old_key = _app_cache_key("bundled", "retained.exe", "OLD")
        shell._app_results.put(
            (1, old_key, [DeviceApp("Old", "com.example.old", False)], "", True)
        )

        shell._poll_app_results()

        chooser.assert_not_called()
        self.assertEqual(shell._app_cache, {})
        shell._start_app_var.set.assert_not_called()

    @patch("src.settings._AppSelectionDialog")
    def test_current_selection_applies_package_to_start_app(self, chooser) -> None:
        shell = _settings_shell()
        app = DeviceApp("Example", "com.example.app", False)
        shell._app_request = 4
        shell._app_loading = True
        key = shell._current_app_cache_key()
        shell._app_results.put((4, key, [app], "", True))
        chooser.return_value.selected = app

        shell._poll_app_results()

        self.assertEqual(shell._app_cache[key], [app])
        status = shell._app_status_var.set.call_args.args[0]
        self.assertIn("Selected Example", status)
        shell._start_app_var.set.assert_called_once_with("com.example.app")

    @patch("src.settings._AppSelectionDialog")
    def test_cancel_keeps_existing_start_app(self, chooser) -> None:
        shell = _settings_shell()
        shell._start_app_var.get.return_value = "+?Old App"
        chooser.return_value.selected = None

        shell._open_app_chooser([DeviceApp("Example", "com.example.app", False)])

        shell._start_app_var.set.assert_not_called()

    def test_selected_package_preserves_force_stop_and_removes_search_prefix(self) -> None:
        package = "com.example.app"
        self.assertEqual(_selected_start_app_value("+?Example", package), "+" + package)
        self.assertEqual(_selected_start_app_value("+old.package", package), "+" + package)
        self.assertEqual(_selected_start_app_value("?Example", package), package)
        self.assertEqual(_selected_start_app_value("old.package", package), package)

    def test_quick_option_sync_deduplicates_start_app_and_preserves_other_args(self) -> None:
        shell = _settings_shell()
        shell._syncing_controls = False
        shell._get_args = MagicMock(
            return_value=[
                "--serial=ABC",
                "--start-app=old.one",
                "--no-audio",
                "--start-app=old.two",
            ]
        )
        shell._window_title_var = MagicMock()
        shell._window_title_var.get.return_value = ""
        shell._start_app_var.get.return_value = "+com.example.app"
        shell._turn_screen_off_var = MagicMock()
        shell._turn_screen_off_var.get.return_value = False
        shell._no_audio_var = MagicMock()
        shell._no_audio_var.get.return_value = True
        shell._new_display_var = MagicMock()
        shell._new_display_var.get.return_value = False
        shell._write_args = MagicMock()

        shell._on_quick_options_changed()

        shell._write_args.assert_called_once_with(
            ["--serial=ABC", "--start-app=+com.example.app", "--no-audio"]
        )

    @patch("src.settings.messagebox.showerror")
    def test_current_discovery_error_is_reported_on_ui_poll(self, showerror) -> None:
        shell = _settings_shell()
        shell._app_request = 3
        shell._app_loading = True
        key = shell._current_app_cache_key()
        cached = [DeviceApp("Old", "com.example.old", False)]
        shell._app_cache[key] = cached
        shell._app_results.put((3, key, None, "device disconnected", False))

        shell._poll_app_results()

        self.assertFalse(shell._app_loading)
        self.assertIs(shell._app_cache[key], cached)
        self.assertIn("retained", shell._app_status_var.set.call_args.args[0])
        showerror.assert_called_once()
        self.assertIn("device disconnected", showerror.call_args.args[1])
        shell._start_app_var.set.assert_not_called()

    @patch("src.settings.messagebox.showinfo")
    def test_empty_app_list_is_reported_without_opening_browser(self, showinfo) -> None:
        shell = _settings_shell()
        shell._app_request = 3
        shell._app_loading = True
        key = shell._current_app_cache_key()
        shell._app_results.put((3, key, [], "", True))

        shell._poll_app_results()

        showinfo.assert_called_once()
        self.assertEqual(shell._app_cache[key], [])
        shell._start_app_var.set.assert_not_called()

    @patch("src.settings._AppSelectionDialog")
    def test_successful_refresh_replaces_cache_without_opening_browser(self, chooser) -> None:
        shell = _settings_shell()
        shell._dialog.winfo_exists.return_value = True
        old = DeviceApp("Old", "com.example.old", False)
        new = DeviceApp("New", "com.example.new", False)
        key = shell._current_app_cache_key()
        shell._app_cache[key] = [old]
        shell._app_request = 5
        shell._app_loading = True
        shell._app_poll_job = "app-poll"
        shell._app_results.put((5, key, [new], "", False))

        shell._poll_app_results()

        self.assertEqual(shell._app_cache[key], [new])
        self.assertIsNone(shell._app_poll_job)
        shell._dialog.after.assert_not_called()
        chooser.assert_not_called()
        self.assertIn("Refreshed 1 application", shell._app_status_var.set.call_args.args[0])

    def test_cache_keys_separate_devices_and_custom_runtimes(self) -> None:
        bundled_a = _app_cache_key("bundled", "ignored-a.exe", "ABC")
        bundled_b = _app_cache_key("bundled", "ignored-b.exe", "ABC")
        other_device = _app_cache_key("bundled", "ignored.exe", "XYZ")
        custom_a = _app_cache_key("custom", "C:/tools/a/scrcpy.exe", "ABC")
        custom_b = _app_cache_key("custom", "C:/tools/b/scrcpy.exe", "ABC")

        self.assertEqual(bundled_a, bundled_b)
        self.assertNotEqual(bundled_a, other_device)
        self.assertNotEqual(custom_a, custom_b)

    def test_default_status_tracks_connected_device_and_cache(self) -> None:
        shell = _settings_shell()
        key = shell._current_app_cache_key()

        self.assertEqual(
            shell._default_app_status(),
            "Select app to load applications from this device",
        )
        shell._app_cache[key] = [DeviceApp("Example", "com.example.app", False)]
        self.assertEqual(shell._default_app_status(), "1 application cached for this device")

    def test_custom_path_change_invalidates_devices_and_pending_app_results(self) -> None:
        shell = _settings_shell()
        shell._device_request = 4
        shell._app_request = 6
        shell._device_loading = True
        shell._device_poll_job = "device-poll"
        shell._syncing_controls = False
        shell._apply_device_choices = MagicMock()
        shell._refresh_button = MagicMock()
        shell._device_status_var = MagicMock()

        shell._on_scrcpy_path_changed()

        self.assertEqual(shell._device_request, 5)
        self.assertEqual(shell._app_request, 7)
        self.assertFalse(shell._device_loading)
        self.assertIsNone(shell._device_poll_job)
        self.assertEqual(shell._detected_devices, [])
        self.assertFalse(shell._syncing_controls)
        shell._apply_device_choices.assert_called_once_with()
        self.assertIn("refresh devices", shell._device_status_var.set.call_args.args[0])
        shell._refresh_button.configure.assert_called_once_with(state="normal")
        shell._dialog.after_cancel.assert_called_once_with("device-poll")

    def test_device_polling_has_one_callback_and_stops_after_current_result(self) -> None:
        shell = _settings_shell()
        shell._dialog.winfo_exists.return_value = True
        shell._dialog.after.return_value = "device-poll"
        shell._device_loading = True
        shell._device_request = 3
        shell._refresh_button = MagicMock()
        shell._device_status_var = MagicMock()
        shell._apply_device_choices = MagicMock()
        shell._device_results.put((3, [Device("ABC", "device")], ""))

        shell._schedule_device_poll()
        shell._schedule_device_poll()
        shell._poll_device_results()

        shell._dialog.after.assert_called_once_with(100, shell._poll_device_results)
        self.assertIsNone(shell._device_poll_job)
        self.assertFalse(shell._device_loading)
        self.assertEqual(shell._detected_devices, [Device("ABC", "device")])

    def test_application_polling_reschedules_only_while_request_is_active(self) -> None:
        shell = _settings_shell()
        shell._dialog.winfo_exists.return_value = True
        shell._dialog.after.return_value = "app-poll"
        shell._app_loading = True

        shell._schedule_app_poll()
        shell._schedule_app_poll()
        shell._poll_app_results()

        self.assertEqual(shell._dialog.after.call_count, 2)
        shell._dialog.after.assert_called_with(100, shell._poll_app_results)
        self.assertEqual(shell._app_poll_job, "app-poll")

    def test_closing_settings_invalidates_pending_results(self) -> None:
        shell = _settings_shell()
        shell._device_request = 5
        shell._app_request = 7
        shell._device_loading = True
        shell._app_loading = True
        shell._device_poll_job = "device-poll"
        shell._app_poll_job = "app-poll"

        shell._destroy_dialog()

        self.assertEqual(shell._device_request, 6)
        self.assertEqual(shell._app_request, 8)
        self.assertFalse(shell._device_loading)
        self.assertFalse(shell._app_loading)
        self.assertIsNone(shell._device_poll_job)
        self.assertIsNone(shell._app_poll_job)
        self.assertEqual(
            shell._dialog.after_cancel.call_args_list,
            [call("device-poll"), call("app-poll")],
        )
        shell._dialog.destroy.assert_called_once_with()

    def test_dialog_choose_and_cancel_contract(self) -> None:
        app = DeviceApp("Example", "com.example.app", False)
        chooser = object.__new__(_AppSelectionDialog)
        chooser._tree = MagicMock()
        chooser._tree.selection.return_value = ("app-0",)
        chooser._app_by_item = {"app-0": app}
        chooser._close = MagicMock()
        chooser.selected = None

        chooser._choose()
        self.assertIs(chooser.selected, app)
        chooser._close.assert_called_once_with()

        self.assertEqual(chooser._choose_event(), "break")

        chooser._close.reset_mock()
        chooser._cancel()
        self.assertIsNone(chooser.selected)
        chooser._close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
