# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from src.config import CURRENT_SCHEMA_VERSION, SCRCPY_MODE_CUSTOM, Config
from src.launcher import _ProcessManager
from src.settings import _SettingsDialog


class AppSessionIntegrationTests(unittest.TestCase):
    def _config_path(self, directory: str) -> Path:
        path = Path(directory) / "config.json"
        scrcpy_path = Path(directory) / "scrcpy.exe"
        scrcpy_path.write_bytes(b"MZ")
        path.write_text(
            json.dumps(
                {
                    "schema_version": CURRENT_SCHEMA_VERSION,
                    "scrcpy_mode": SCRCPY_MODE_CUSTOM,
                    "scrcpy_path": str(scrcpy_path),
                    "sessions": [
                        {
                            "name": "Phone",
                            "args": ["--serial=ABC", "--no-audio"],
                        },
                        {
                            "name": "Tablet",
                            "args": ["--serial=XYZ", "--new-display"],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _update_shell(config: Config, args: list[str]) -> _SettingsDialog:
        shell = object.__new__(_SettingsDialog)
        shell._config = config
        shell._listbox = MagicMock()
        shell._listbox.curselection.return_value = (0,)
        shell._name_var = MagicMock()
        shell._name_var.get.return_value = "Phone"
        shell._get_args = MagicMock(return_value=args)
        shell._update_move_buttons = MagicMock()
        return shell

    def test_apply_then_save_persists_selected_package_without_reordering_other_args(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._config_path(directory)
            config = Config(path)
            selected_args = [
                "--serial=ABC",
                "--no-audio",
                "--start-app=+com.example.selected",
            ]
            shell = self._update_shell(config, selected_args)

            self.assertTrue(shell._update_session())
            self.assertEqual(config.sessions[0].args, selected_args)
            self.assertNotIn("--start-app", "\n".join(Config(path).sessions[0].args))

            config.save()
            reloaded = Config(path)
            self.assertEqual(reloaded.sessions[0].args, selected_args)
            self.assertEqual(reloaded.sessions[1].args, ["--serial=XYZ", "--new-display"])

    def test_cancel_after_apply_leaves_saved_configuration_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._config_path(directory)
            original = path.read_bytes()
            config = Config(path)
            shell = self._update_shell(
                config,
                ["--serial=ABC", "--start-app=com.example.unsaved"],
            )
            self.assertTrue(shell._update_session())
            shell._destroy_dialog = MagicMock()

            shell._cancel()

            self.assertFalse(shell._saved)
            shell._destroy_dialog.assert_called_once_with()
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(Config(path).sessions[0].args, ["--serial=ABC", "--no-audio"])

    def test_switching_sessions_loads_only_the_selected_sessions_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Config(self._config_path(directory))
            shell = object.__new__(_SettingsDialog)
            shell._config = config
            shell._listbox = MagicMock()
            shell._listbox.curselection.return_value = (1,)
            shell._name_var = MagicMock()
            shell._write_args = MagicMock()
            shell._update_move_buttons = MagicMock()
            shell._invalidate_app_discovery = MagicMock()

            shell._on_select()

            shell._name_var.set.assert_called_once_with("Tablet")
            shell._write_args.assert_called_once_with(["--serial=XYZ", "--new-display"])
            shell._invalidate_app_discovery.assert_called_once_with()

    @patch("src.launcher.threading.Thread")
    @patch("src.launcher.subprocess.Popen")
    def test_saved_selected_package_is_forwarded_exactly_to_scrcpy(
        self, popen, thread
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._config_path(directory)
            config = Config(path)
            selected_args = [
                "--serial=ABC",
                "--window-title=Selected App",
                "--new-display",
                "--start-app=+com.example.selected",
            ]
            config.update_session(0, "Phone", selected_args)
            config.save()
            reloaded = Config(path)
            session = reloaded.sessions[0]
            popen.return_value = Mock()

            _ProcessManager().launch(reloaded.scrcpy_path, session.args)

            self.assertEqual(
                popen.call_args.args[0],
                [reloaded.scrcpy_path, *selected_args],
            )
            thread.return_value.start.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
