# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import unittest

from src.cli import InvocationError, LaunchMode, parse_invocation


class CliTests(unittest.TestCase):
    def test_empty_arguments_start_tray_with_default_config(self) -> None:
        invocation = parse_invocation([])
        self.assertIs(invocation.mode, LaunchMode.TRAY)
        self.assertIsNone(invocation.config_path)

    def test_tray_accepts_explicit_and_legacy_config_paths(self) -> None:
        self.assertEqual(
            parse_invocation(["--config", "custom.json"]).config_path,
            "custom.json",
        )
        self.assertEqual(parse_invocation(["legacy.json"]).config_path, "legacy.json")

    def test_settings_requires_a_config_path(self) -> None:
        invocation = parse_invocation(["--settings", "custom.json"])
        self.assertIs(invocation.mode, LaunchMode.SETTINGS)
        self.assertEqual(invocation.config_path, "custom.json")

        with self.assertRaises(InvocationError):
            parse_invocation(["--settings"])

    def test_rejects_unknown_or_extra_arguments(self) -> None:
        for arguments in (["--unknown"], ["one.json", "two.json"], ["--config"]):
            with self.subTest(arguments=arguments), self.assertRaises(InvocationError):
                parse_invocation(arguments)

    def test_internal_package_smoke_mode_is_explicit(self) -> None:
        invocation = parse_invocation(["--package-smoke-test"])
        self.assertIs(invocation.mode, LaunchMode.PACKAGE_SMOKE_TEST)
        self.assertFalse(invocation.allow_missing_bundled_tools)

        unbundled = parse_invocation(
            ["--package-smoke-test", "--allow-missing-bundled-tools"]
        )
        self.assertIs(unbundled.mode, LaunchMode.PACKAGE_SMOKE_TEST)
        self.assertTrue(unbundled.allow_missing_bundled_tools)

    def test_portableapps_smoke_mode_requires_launcher_config_argument(self) -> None:
        invocation = parse_invocation(
            ["--config", "X:/PortableApps/App/Data/config.json", "--portableapps-smoke-test"]
        )

        self.assertIs(invocation.mode, LaunchMode.PORTABLEAPPS_SMOKE_TEST)
        self.assertEqual(
            invocation.config_path,
            "X:/PortableApps/App/Data/config.json",
        )
        with self.assertRaises(InvocationError):
            parse_invocation(["--portableapps-smoke-test"])


if __name__ == "__main__":
    unittest.main()
