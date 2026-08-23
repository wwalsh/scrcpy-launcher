# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from src.devices import DeviceDiscoveryError, detect_devices, find_adb, parse_adb_devices


ADB_OUTPUT = """List of devices attached
EXAMPLE_SECOND_DEVICE_SERIAL device product:B160V model:B160V device:B160V transport_id:12
EXAMPLE_DEVICE_SERIAL unauthorized usb:1-2 transport_id:11
192.168.1.5:5555 offline transport_id:13
"""


class DeviceTests(unittest.TestCase):
    def test_parses_connected_and_unavailable_devices(self) -> None:
        devices = parse_adb_devices(ADB_OUTPUT)

        self.assertEqual([device.state for device in devices], ["device", "unauthorized", "offline"])
        self.assertEqual(devices[0].model, "B160V")
        self.assertEqual(devices[0].transport_id, "12")
        self.assertEqual(devices[0].label, "B160V — EXAMPLE_SECOND_DEVICE_SERIAL")

    def test_normalizes_adb_model_spacing_for_display(self) -> None:
        devices = parse_adb_devices(
            "List of devices attached\nABC device model:moto_g_power_5G___2024\n"
        )

        self.assertEqual(devices[0].label, "moto g power 5G 2024 — ABC")

    @patch("src.devices.subprocess.run")
    @patch("src.devices.find_adb", return_value=Path("adb.exe"))
    def test_detect_devices_runs_long_listing(self, _find_adb, run) -> None:
        run.return_value = subprocess.CompletedProcess([], 0, ADB_OUTPUT, "")

        devices = detect_devices("scrcpy.exe")

        self.assertEqual(len(devices), 3)
        _find_adb.assert_called_once_with("scrcpy.exe", allow_path_fallback=True)
        self.assertEqual(run.call_args.args[0], ["adb.exe", "devices", "-l"])

    @patch("src.devices.subprocess.run", side_effect=subprocess.TimeoutExpired("adb", 5))
    @patch("src.devices.find_adb", return_value=Path("adb.exe"))
    def test_reports_timeout(self, _find_adb, _run) -> None:
        with self.assertRaisesRegex(DeviceDiscoveryError, "timed out"):
            detect_devices("scrcpy.exe")

    @patch("src.devices.shutil.which", return_value=None)
    def test_reports_missing_adb(self, _which) -> None:
        with patch("src.devices.Path.is_file", return_value=False):
            with self.assertRaisesRegex(DeviceDiscoveryError, "not found"):
                detect_devices("C:/missing/scrcpy.exe")

    @patch("src.devices.shutil.which", return_value="C:/system/adb.exe")
    def test_bundled_mode_does_not_fall_back_to_system_adb(self, which) -> None:
        with patch("src.devices.Path.is_file", return_value=False):
            with self.assertRaisesRegex(DeviceDiscoveryError, "not found"):
                find_adb("C:/app/tools/scrcpy/scrcpy.exe", allow_path_fallback=False)

        which.assert_not_called()


if __name__ == "__main__":
    unittest.main()
