# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import subprocess
import io
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.config import SCRCPY_MODE_BUNDLED, SCRCPY_MODE_CUSTOM
from src.device_apps import (
    AppDiscoveryError,
    DeviceApp,
    discover_device_apps,
    list_device_apps,
)
from src.scrcpy_runtime import ScrcpyResolution, ScrcpyResolutionError


APP_OUTPUT = """scrcpy 4.1 <https://github.com/Genymobile/scrcpy>
[server] INFO: List of apps:
 * Settings                       com.android.settings
 - Example                        com.example.app
"""


class DeviceAppDiscoveryTests(unittest.TestCase):
    @staticmethod
    def _process(stdout: str, stderr: str, returncode: int = 0) -> Mock:
        process = Mock()
        process.stdout = io.StringIO(stdout)
        process.stderr = io.StringIO(stderr)
        process.wait.return_value = returncode
        return process

    @patch("src.process.subprocess.Popen")
    def test_runs_hidden_explicit_serial_command_and_accepts_success_stderr(self, popen) -> None:
        popen.return_value = self._process(APP_OUTPUT, "scrcpy-server: 1 file pushed")

        apps = list_device_apps(Path("C:/scrcpy/scrcpy.exe"), " SERIAL-1 ")

        self.assertEqual(
            apps,
            [
                DeviceApp("Settings", "com.android.settings", True),
                DeviceApp("Example", "com.example.app", False),
            ],
        )
        self.assertEqual(
            popen.call_args.args[0],
            ["C:\\scrcpy\\scrcpy.exe", "--serial", "SERIAL-1", "--list-apps"],
        )
        options = popen.call_args.kwargs
        self.assertIs(options["stdout"], subprocess.PIPE)
        self.assertIs(options["stderr"], subprocess.PIPE)
        self.assertTrue(options["text"])
        self.assertEqual(options["encoding"], "utf-8")
        self.assertEqual(options["errors"], "replace")
        self.assertNotIn("timeout", options)
        self.assertEqual(
            options["creationflags"], getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        self.assertNotIn("check", options)

    @patch("src.device_apps.list_device_apps", return_value=[])
    @patch("src.device_apps.resolve_scrcpy")
    def test_resolves_selected_mode_before_discovery(self, resolve, list_apps) -> None:
        resolution = ScrcpyResolution(
            Path("D:/portable/tools/scrcpy/scrcpy.exe"),
            SCRCPY_MODE_BUNDLED,
            "bundled scrcpy 5.0.1",
        )
        resolve.return_value = resolution

        result = discover_device_apps(
            SCRCPY_MODE_BUNDLED,
            "retained-custom.exe",
            "ABC",
            timeout=12,
            root="D:/portable",
        )

        self.assertEqual(result, [])
        resolve.assert_called_once_with(
            SCRCPY_MODE_BUNDLED,
            "retained-custom.exe",
            root="D:/portable",
        )
        list_apps.assert_called_once_with(resolution.path, "ABC", timeout=12)

    @patch("src.device_apps.list_device_apps")
    @patch("src.device_apps.resolve_scrcpy")
    def test_custom_mode_uses_only_resolved_custom_executable(self, resolve, list_apps) -> None:
        custom = Path("C:/custom/scrcpy.exe")
        resolve.return_value = ScrcpyResolution(
            custom, SCRCPY_MODE_CUSTOM, "custom scrcpy executable"
        )
        list_apps.return_value = []

        discover_device_apps(SCRCPY_MODE_CUSTOM, str(custom), "ABC")

        resolve.assert_called_once_with(SCRCPY_MODE_CUSTOM, str(custom), root=None)
        list_apps.assert_called_once_with(custom, "ABC", timeout=20.0)

    @patch("src.device_apps.list_device_apps")
    @patch(
        "src.device_apps.resolve_scrcpy",
        side_effect=ScrcpyResolutionError("Bundled scrcpy is missing. Repair or reinstall."),
    )
    def test_resolution_failure_is_controlled_without_process_fallback(
        self, _resolve, list_apps
    ) -> None:
        with self.assertRaisesRegex(AppDiscoveryError, "Repair or reinstall"):
            discover_device_apps(SCRCPY_MODE_BUNDLED, "custom.exe", "ABC")

        list_apps.assert_not_called()

    @patch("src.process.subprocess.Popen")
    def test_requires_explicit_serial_and_positive_timeout(self, popen) -> None:
        with self.assertRaisesRegex(AppDiscoveryError, "Select a connected"):
            list_device_apps("scrcpy.exe", "  ")
        with self.assertRaisesRegex(AppDiscoveryError, "greater than zero"):
            list_device_apps("scrcpy.exe", "ABC", timeout=0)

        popen.assert_not_called()

    @patch("src.process.subprocess.Popen")
    def test_timeout_is_controlled(self, popen) -> None:
        process = self._process("", "")
        process.wait.side_effect = [subprocess.TimeoutExpired("scrcpy", 7), 1]
        popen.return_value = process
        with self.assertRaisesRegex(
            AppDiscoveryError, "timed out after 7 seconds.*Refresh apps"
        ):
            list_device_apps("scrcpy.exe", "ABC", timeout=7)

    @patch("src.process.subprocess.Popen", side_effect=OSError("blocked"))
    def test_process_launch_failure_is_controlled(self, _popen) -> None:
        with self.assertRaisesRegex(AppDiscoveryError, "Could not run scrcpy.*blocked"):
            list_device_apps("scrcpy.exe", "ABC")

    @patch("src.process.subprocess.Popen")
    def test_nonzero_exit_prefers_stderr_diagnostics(self, popen) -> None:
        popen.return_value = self._process(
            "scrcpy 4.1\n - Private App                   com.private.app\n",
            "ERROR: device ABC is unauthorized",
            1,
        )

        with self.assertRaisesRegex(AppDiscoveryError, "Device ABC is unauthorized") as raised:
            list_device_apps("scrcpy.exe", "ABC")

        self.assertNotIn("Private App", str(raised.exception))
        self.assertIn("USB debugging", str(raised.exception))

    @patch("src.process.subprocess.Popen")
    def test_unsupported_list_apps_option_has_upgrade_guidance(self, popen) -> None:
        popen.return_value = self._process(
            "scrcpy 1.20\n", "ERROR: Unknown option --list-apps", 1
        )

        with self.assertRaisesRegex(
            AppDiscoveryError, "does not support --list-apps.*bundled scrcpy 5.0.1"
        ):
            list_device_apps("old-scrcpy.exe", "ABC")

    @patch("src.process.subprocess.Popen")
    def test_offline_and_missing_devices_have_recovery_guidance(self, popen) -> None:
        for diagnostic, expected in (
            ("ERROR: device ABC is offline", "offline.*refresh devices"),
            ("ERROR: Could not find any ADB device ABC", "no longer available.*refresh devices"),
        ):
            with self.subTest(diagnostic=diagnostic):
                popen.return_value = self._process("scrcpy 4.1\n", diagnostic, 1)
                with self.assertRaisesRegex(AppDiscoveryError, expected):
                    list_device_apps("scrcpy.exe", "ABC")

    @patch("src.process.subprocess.Popen")
    def test_nonzero_exit_filters_partial_inventory_from_stdout(self, popen) -> None:
        popen.return_value = self._process(
            "scrcpy 4.1\nERROR: connection failed\n - Secret com.secret.app\n",
            "",
            1,
        )

        with self.assertRaisesRegex(AppDiscoveryError, "connection failed") as raised:
            list_device_apps("scrcpy.exe", "ABC")

        self.assertNotIn("Secret", str(raised.exception))

    @patch("src.process.subprocess.Popen")
    def test_parser_failure_is_wrapped_without_inventory(self, popen) -> None:
        popen.return_value = self._process("unexpected output", "")

        with self.assertRaisesRegex(
            AppDiscoveryError, "unsupported application list.*bundled scrcpy 5.0.1"
        ):
            list_device_apps("scrcpy.exe", "ABC")

    @patch("src.process.subprocess.Popen")
    def test_valid_empty_list_is_successful(self, popen) -> None:
        popen.return_value = self._process("[server] INFO: List of apps:\n", "")

        self.assertEqual(list_device_apps("scrcpy.exe", "ABC"), [])


if __name__ == "__main__":
    unittest.main()
