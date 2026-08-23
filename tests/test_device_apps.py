# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import unittest
from pathlib import Path

from src.device_apps import AppListParseError, DeviceApp, parse_scrcpy_app_list


FIXTURES = Path(__file__).resolve().parent / "fixtures"


class DeviceAppParserTests(unittest.TestCase):
    def test_parses_sanitized_scrcpy_4_1_output(self) -> None:
        output = (FIXTURES / "scrcpy-list-apps-v4.1.txt").read_text(encoding="utf-8")

        apps = parse_scrcpy_app_list(output)

        self.assertEqual(len(apps), 6)
        self.assertEqual(
            apps[0],
            DeviceApp("Calculator", "com.google.android.calculator", True),
        )
        self.assertEqual(
            [app.package_name for app in apps if app.name == "Authenticator"],
            ["com.azure.authenticator", "com.bitwarden.authenticator"],
        )
        self.assertEqual(apps[4].name, "Google\N{NO-BREAK SPACE}Wallet")
        self.assertFalse(apps[4].is_system)
        self.assertEqual(apps[5].package_name, "com.lonelycatgames.Xplore")

    def test_parses_upstream_wrapped_long_name_format(self) -> None:
        output = (FIXTURES / "scrcpy-list-apps-v4.1-wrapped.txt").read_text(
            encoding="utf-8"
        )

        self.assertEqual(
            parse_scrcpy_app_list(output),
            [
                DeviceApp(
                    "Application Name Longer Than Thirty Characters",
                    "com.example.long_application_name",
                    False,
                )
            ],
        )

    def test_deduplicates_exact_packages_but_allows_duplicate_names(self) -> None:
        output = """[server] INFO: List of apps:
 - Same                          com.example.first
 - Same                          com.example.second
 - Renamed                       com.example.first
"""

        apps = parse_scrcpy_app_list(output)

        self.assertEqual(
            [app.package_name for app in apps],
            ["com.example.first", "com.example.second"],
        )

    def test_accepts_an_empty_but_recognized_list(self) -> None:
        self.assertEqual(parse_scrcpy_app_list("[server] INFO: List of apps:\n"), [])

    def test_rejects_output_without_the_list_header(self) -> None:
        with self.assertRaisesRegex(AppListParseError, "does not contain"):
            parse_scrcpy_app_list("scrcpy 4.1\nERROR: device offline\n")

    def test_rejects_malformed_or_incomplete_rows(self) -> None:
        malformed_outputs = (
            "[server] INFO: List of apps:\nnot an app row\n",
            "[server] INFO: List of apps:\n - Long application name without package\n",
            "[server] INFO: List of apps:\n - App package-without-dot\n",
        )
        for output in malformed_outputs:
            with self.subTest(output=output), self.assertRaises(AppListParseError):
                parse_scrcpy_app_list(output)


if __name__ == "__main__":
    unittest.main()
