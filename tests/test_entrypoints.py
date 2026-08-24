# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from src import main, settings_main
from src.config import ConfigError
from src.single_instance import SingleInstanceError
from src.winui import DialogChoice


class EntrypointTests(unittest.TestCase):
    @patch("src.main._package_smoke_test", return_value=0)
    def test_package_smoke_mode_does_not_acquire_mutex(self, smoke_test) -> None:
        with patch.object(main.sys, "argv", ["launcher", "--package-smoke-test"]), patch(
            "src.main.SingleInstance"
        ) as single_instance:
            result = main.main()

        self.assertEqual(result, 0)
        smoke_test.assert_called_once_with(require_bundled_tools=True)
        single_instance.assert_not_called()

    @patch("src.main._package_smoke_test", return_value=0)
    def test_unbundled_package_smoke_explicitly_skips_tools(self, smoke_test) -> None:
        arguments = [
            "launcher",
            "--package-smoke-test",
            "--allow-missing-bundled-tools",
        ]
        with patch.object(main.sys, "argv", arguments), patch(
            "src.main.SingleInstance"
        ) as single_instance:
            result = main.main()

        self.assertEqual(result, 0)
        smoke_test.assert_called_once_with(require_bundled_tools=False)
        single_instance.assert_not_called()

    @patch("src.scrcpy_runtime.validate_bundled_installation")
    @patch("src.runtime.resource_path")
    def test_package_smoke_validates_bundled_tools(self, resource_path, validate) -> None:
        resource_path.return_value.is_file.return_value = True

        result = main._package_smoke_test(require_bundled_tools=True)

        self.assertEqual(result, 0)
        validate.assert_called_once_with()

    @patch("src.settings_main.run_settings")
    def test_packaged_settings_mode_does_not_acquire_tray_mutex(self, run_settings) -> None:
        run_settings.return_value = 0
        with patch.object(main.sys, "argv", ["launcher", "--settings", "config.json"]), patch(
            "src.main.SingleInstance"
        ) as single_instance:
            result = main.main()

        self.assertEqual(result, 0)
        run_settings.assert_called_once_with("config.json")
        single_instance.assert_not_called()

    @patch("src.main.show_error")
    @patch("src.main.setup_logging", return_value=Path("tray.log"))
    def test_invalid_command_line_is_controlled(self, _logging, show_error) -> None:
        with patch.object(main.sys, "argv", ["launcher", "--unknown"]), patch(
            "src.main.SingleInstance"
        ) as single_instance:
            result = main.main()

        self.assertEqual(result, 2)
        show_error.assert_called_once()
        single_instance.assert_not_called()

    @patch("src.main.show_error")
    @patch("src.main.ask_yes_no", return_value=DialogChoice.NO)
    @patch("src.main.inspect_recovery")
    @patch("src.main.load_config", side_effect=ConfigError("bad JSON"))
    @patch("src.main.setup_logging", return_value=Path("tray.log"))
    @patch("src.main.SingleInstance")
    def test_main_reports_config_error_and_does_not_start_tray(
        self, single_instance, _logging, _load, inspection, _ask, show_error
    ) -> None:
        single_instance.return_value.acquire.return_value = True
        inspection.return_value.backup_valid = False
        with patch.object(main.sys, "argv", ["scrcpy-launcher"]), patch(
            "src.main._run_tray"
        ) as run_tray:
            with self.assertLogs("src.main", level="ERROR"):
                result = main.main()

        self.assertEqual(result, 1)
        run_tray.assert_not_called()
        self.assertIn("bad JSON", _ask.call_args.args[1])
        show_error.assert_not_called()
        single_instance.return_value.release.assert_called_once_with()

    @patch("src.main.restore_backup")
    @patch("src.main.ask_yes_no_cancel", return_value=DialogChoice.YES)
    @patch("src.main.inspect_recovery")
    @patch("src.main.load_config", side_effect=ConfigError("bad JSON"))
    def test_startup_restores_valid_backup_after_confirmation(
        self, _load, inspection, _ask, restore
    ) -> None:
        inspection.return_value.backup_valid = True
        inspection.return_value.backup_path = Path("config.json.bak")
        restored = restore.return_value

        result = main._load_startup_config(Path("config.json"), Path("tray.log"))

        self.assertIs(result, restored)
        restore.assert_called_once_with(inspection.return_value)

    @patch("src.main.open_config_folder")
    @patch("src.main.ask_yes_no_cancel", return_value=DialogChoice.NO)
    @patch("src.main.inspect_recovery")
    @patch("src.main.load_config", side_effect=ConfigError("bad JSON"))
    def test_startup_opens_folder_and_exits_when_backup_prompt_is_no(
        self, _load, inspection, _ask, open_folder
    ) -> None:
        inspection.return_value.backup_valid = True
        inspection.return_value.backup_path = Path("config.json.bak")

        result = main._load_startup_config(Path("config.json"), Path("tray.log"))

        self.assertIsNone(result)
        open_folder.assert_called_once_with(Path("config.json"))

    @patch("src.main.open_config_folder")
    @patch("src.main.ask_yes_no_cancel", return_value=DialogChoice.CANCEL)
    @patch("src.main.inspect_recovery")
    @patch("src.main.load_config", side_effect=ConfigError("bad JSON"))
    def test_startup_cancel_exits_without_file_actions(
        self, _load, inspection, _ask, open_folder
    ) -> None:
        inspection.return_value.backup_valid = True
        inspection.return_value.backup_path = Path("config.json.bak")

        result = main._load_startup_config(Path("config.json"), Path("tray.log"))

        self.assertIsNone(result)
        open_folder.assert_not_called()

    @patch("src.main.open_config_folder")
    @patch("src.main.ask_yes_no", return_value=DialogChoice.YES)
    @patch("src.main.inspect_recovery")
    @patch("src.main.load_config", side_effect=ConfigError("missing"))
    def test_startup_can_open_folder_when_no_valid_backup_exists(
        self, _load, inspection, _ask, open_folder
    ) -> None:
        inspection.return_value.backup_valid = False

        result = main._load_startup_config(Path("config.json"), Path("tray.log"))

        self.assertIsNone(result)
        open_folder.assert_called_once_with(Path("config.json"))

    @patch("src.main.show_info")
    @patch("src.main.load_config")
    @patch("src.main.setup_logging", return_value=Path("tray.log"))
    @patch("src.main.SingleInstance")
    def test_duplicate_main_exits_without_loading_config(
        self, single_instance, _logging, load_config, show_info
    ) -> None:
        single_instance.return_value.acquire.return_value = False

        with patch.object(main.sys, "argv", ["scrcpy-launcher"]):
            result = main.main()

        self.assertEqual(result, 0)
        load_config.assert_not_called()
        show_info.assert_called_once()
        single_instance.return_value.release.assert_not_called()

    @patch("src.main.show_error")
    @patch("src.main.setup_logging", return_value=Path("tray.log"))
    @patch("src.main.SingleInstance")
    def test_mutex_failure_is_a_controlled_startup_error(
        self, single_instance, _logging, show_error
    ) -> None:
        single_instance.return_value.acquire.side_effect = SingleInstanceError("mutex failed")

        with patch.object(main.sys, "argv", ["scrcpy-launcher"]), self.assertLogs(
            "src.main", level="ERROR"
        ):
            result = main.main()

        self.assertEqual(result, 1)
        self.assertIn("mutex failed", show_error.call_args.args[1])
        single_instance.return_value.release.assert_not_called()

    @patch("src.main._run_tray")
    @patch("src.main.load_config")
    @patch("src.main.setup_logging", return_value=Path("tray.log"))
    @patch("src.main.SingleInstance")
    def test_main_releases_mutex_after_normal_tray_exit(
        self, single_instance, _logging, load_config, _run_tray
    ) -> None:
        single_instance.return_value.acquire.return_value = True
        load_config.return_value.config_path = Path("config.json")
        load_config.return_value.sessions = ()

        with patch.object(main.sys, "argv", ["scrcpy-launcher"]):
            result = main.main()

        self.assertEqual(result, 0)
        single_instance.return_value.release.assert_called_once_with()

    @patch("src.main.show_error")
    @patch("src.main._run_tray", side_effect=RuntimeError("tray failed"))
    @patch("src.main.load_config")
    @patch("src.main.setup_logging", return_value=Path("tray.log"))
    @patch("src.main.SingleInstance")
    def test_main_releases_mutex_after_tray_failure(
        self, single_instance, _logging, load_config, _run_tray, _show_error
    ) -> None:
        single_instance.return_value.acquire.return_value = True
        load_config.return_value.config_path = Path("config.json")
        load_config.return_value.sessions = ()

        with patch.object(main.sys, "argv", ["scrcpy-launcher"]), self.assertLogs(
            "src.main", level="ERROR"
        ):
            result = main.main()

        self.assertEqual(result, 1)
        single_instance.return_value.release.assert_called_once_with()

    @patch("src.settings_main.show_error")
    @patch("src.settings_main.show_settings", side_effect=ConfigError("invalid config"))
    @patch("src.settings_main.setup_logging", return_value=Path("settings.log"))
    def test_settings_reports_startup_failure(self, _logging, _show_settings, show_error) -> None:
        with patch.object(settings_main.sys, "argv", ["settings", "config.json"]):
            with self.assertLogs("src.settings_main", level="ERROR"):
                result = settings_main.main()

        self.assertEqual(result, 1)
        self.assertIn("invalid config", show_error.call_args.args[1])

    @patch("src.settings_main.show_error")
    @patch("src.settings_main.setup_logging", return_value=Path("settings.log"))
    def test_settings_reports_missing_config_argument(self, _logging, show_error) -> None:
        with patch.object(settings_main.sys, "argv", ["settings"]):
            with self.assertLogs("src.settings_main", level="ERROR"):
                result = settings_main.main()

        self.assertEqual(result, 1)
        self.assertIn("Usage", show_error.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
