# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from src.config import SCRCPY_MODE_BUNDLED, SCRCPY_MODE_CUSTOM
from src.scrcpy_runtime import ScrcpyResolution
from src.device_apps import DeviceApp
from src.devices import Device
from src.settings_app_selector import _filter_device_apps
from src.settings import (
    _connected_serial_for_selection,
    _detect_devices_for_selection,
    _is_current_app_result,
)


class SettingsLogicTests(unittest.TestCase):
    def test_connected_serial_requires_an_explicit_online_device(self) -> None:
        devices = [
            Device("ONLINE", "device"),
            Device("OFFLINE", "offline"),
        ]
        labels = {
            "Automatic": "",
            "Online": "ONLINE",
            "Offline": "OFFLINE",
            "Configured but absent": "MISSING",
        }

        self.assertEqual(
            _connected_serial_for_selection("Online", labels, devices), "ONLINE"
        )
        for label in ("Automatic", "Offline", "Configured but absent", "Unknown"):
            with self.subTest(label=label):
                self.assertEqual(
                    _connected_serial_for_selection(label, labels, devices), ""
                )

    def test_app_filter_sorts_and_matches_names_or_packages(self) -> None:
        apps = [
            DeviceApp("Zulu", "com.example.zulu", False),
            DeviceApp("Authenticator", "com.bitwarden.authenticator", False),
            DeviceApp("Authenticator", "com.azure.authenticator", False),
            DeviceApp("Google\N{NO-BREAK SPACE}Wallet", "com.google.wallet", True),
        ]

        self.assertEqual(
            [app.package_name for app in _filter_device_apps(apps, "")],
            [
                "com.azure.authenticator",
                "com.bitwarden.authenticator",
                "com.google.wallet",
                "com.example.zulu",
            ],
        )
        self.assertEqual(
            [app.package_name for app in _filter_device_apps(apps, "BITWARDEN")],
            ["com.bitwarden.authenticator"],
        )
        self.assertEqual(
            [app.name for app in _filter_device_apps(apps, "wallet")],
            ["Google\N{NO-BREAK SPACE}Wallet"],
        )

    def test_app_results_require_matching_generation_and_device(self) -> None:
        key = ("bundled", "C:/scrcpy.exe", "ABC")
        other_device = ("bundled", "C:/scrcpy.exe", "XYZ")
        other_runtime = ("custom", "C:/other.exe", "ABC")
        self.assertTrue(_is_current_app_result(3, 3, key, key))
        self.assertFalse(_is_current_app_result(2, 3, key, key))
        self.assertFalse(_is_current_app_result(3, 3, key, other_device))
        self.assertFalse(_is_current_app_result(3, 3, key, other_runtime))
        self.assertFalse(_is_current_app_result(3, 3, key, None))

    @patch("src.settings.detect_devices", return_value=[])
    @patch("src.settings.resolve_scrcpy")
    def test_bundled_selection_requires_adjacent_adb(self, resolve, detect) -> None:
        path = Path("C:/app/tools/scrcpy/scrcpy.exe")
        resolve.return_value = ScrcpyResolution(path, SCRCPY_MODE_BUNDLED, "bundled")

        _detect_devices_for_selection(SCRCPY_MODE_BUNDLED, "retained.exe")

        resolve.assert_called_once_with(SCRCPY_MODE_BUNDLED, "retained.exe")
        detect.assert_called_once_with(str(path), allow_path_fallback=False)

    @patch("src.settings.detect_devices", return_value=[])
    @patch("src.settings.resolve_scrcpy")
    def test_custom_selection_retains_path_adb_fallback(self, resolve, detect) -> None:
        path = Path("C:/tools/scrcpy.exe")
        resolve.return_value = ScrcpyResolution(path, SCRCPY_MODE_CUSTOM, "custom")

        _detect_devices_for_selection(SCRCPY_MODE_CUSTOM, str(path))

        detect.assert_called_once_with(str(path), allow_path_fallback=True)


if __name__ == "__main__":
    unittest.main()
