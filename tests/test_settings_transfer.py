# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.config import Config
from src.settings import _SettingsDialog
from src.settings_import import (
    IMPORT_MODE_MERGE,
    IMPORT_MODE_REPLACE,
    _import_summary_text,
)
from src.session_transfer import SESSION_BACKUP_FORMAT, SESSION_BACKUP_VERSION


class SettingsTransferTests(unittest.TestCase):
    def _write_config(self, directory: str, sessions: list[dict]) -> tuple[Path, Config]:
        path = Path(directory) / "config.json"
        path.write_text(
            json.dumps({"scrcpy_path": "scrcpy.exe", "sessions": sessions}),
            encoding="utf-8",
        )
        return path, Config(path)

    def _write_backup(self, directory: str, sessions: list[dict]) -> Path:
        path = Path(directory) / "sessions.json"
        path.write_text(
            json.dumps(
                {
                    "format": SESSION_BACKUP_FORMAT,
                    "version": SESSION_BACKUP_VERSION,
                    "sessions": sessions,
                }
            ),
            encoding="utf-8",
        )
        return path

    def _dialog(self, config: Config) -> _SettingsDialog:
        dialog = _SettingsDialog.__new__(_SettingsDialog)
        dialog._dialog = object()
        dialog._config = config
        dialog._listbox = MagicMock()
        dialog._listbox.curselection.return_value = (0,) if config.sessions else ()
        dialog._prepare_session_transfer = MagicMock(return_value=True)
        dialog._reload_session_list = MagicMock()
        return dialog

    def test_import_mode_cancellation_does_not_mutate_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _path, config = self._write_config(
                directory, [{"name": "Original", "args": []}]
            )
            backup = self._write_backup(
                directory, [{"name": "Imported", "args": []}]
            )
            dialog = self._dialog(config)

            with patch("src.settings.filedialog.askopenfilename", return_value=str(backup)), patch(
                "src.settings._choose_import_mode", return_value=None
            ), patch("src.settings.messagebox.showinfo") as showinfo:
                dialog._import_sessions()

            self.assertEqual([session.name for session in config.sessions], ["Original"])
            dialog._reload_session_list.assert_not_called()
            showinfo.assert_not_called()

    def test_merge_is_staged_in_memory_and_reports_renames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path, config = self._write_config(
                directory, [{"name": "Phone", "args": []}]
            )
            original_bytes = config_path.read_bytes()
            backup = self._write_backup(
                directory,
                [
                    {"name": "phone", "args": ["--serial=ABC"]},
                    {"name": "Tablet", "args": []},
                ],
            )
            dialog = self._dialog(config)

            with patch("src.settings.filedialog.askopenfilename", return_value=str(backup)), patch(
                "src.settings._choose_import_mode", return_value=IMPORT_MODE_MERGE
            ), patch("src.settings.messagebox.showinfo") as showinfo:
                dialog._import_sessions()

            self.assertEqual(
                [session.name for session in config.sessions],
                ["Phone", "phone (2)", "Tablet"],
            )
            self.assertEqual(config_path.read_bytes(), original_bytes)
            dialog._reload_session_list.assert_called_once_with(1)
            self.assertIn("phone → phone (2)", showinfo.call_args.args[1])
            self.assertIn("Click Save", showinfo.call_args.args[1])

    def test_replace_with_empty_backup_is_staged_in_memory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path, config = self._write_config(
                directory, [{"name": "Original", "args": []}]
            )
            original_bytes = config_path.read_bytes()
            backup = self._write_backup(directory, [])
            dialog = self._dialog(config)

            with patch("src.settings.filedialog.askopenfilename", return_value=str(backup)), patch(
                "src.settings._choose_import_mode", return_value=IMPORT_MODE_REPLACE
            ), patch("src.settings.messagebox.showinfo"):
                dialog._import_sessions()

            self.assertEqual(config.sessions, ())
            self.assertEqual(config_path.read_bytes(), original_bytes)
            dialog._reload_session_list.assert_called_once_with(None)

    def test_invalid_import_does_not_mutate_or_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _path, config = self._write_config(
                directory, [{"name": "Original", "args": []}]
            )
            backup = Path(directory) / "broken.json"
            backup.write_text("{broken", encoding="utf-8")
            dialog = self._dialog(config)

            with patch("src.settings.filedialog.askopenfilename", return_value=str(backup)), patch(
                "src.settings.messagebox.showerror"
            ) as showerror:
                dialog._import_sessions()

            self.assertEqual([session.name for session in config.sessions], ["Original"])
            dialog._reload_session_list.assert_not_called()
            self.assertEqual(showerror.call_args.args[0], "Import failed")

    def test_export_writes_only_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _path, config = self._write_config(
                directory, [{"name": "Phone", "args": ["--no-audio"]}]
            )
            destination = Path(directory) / "export.json"
            dialog = self._dialog(config)

            with patch(
                "src.settings.filedialog.asksaveasfilename", return_value=str(destination)
            ), patch("src.settings.messagebox.showinfo"):
                dialog._export_sessions()

            exported = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(exported["sessions"], [{"name": "Phone", "args": ["--no-audio"]}])
            self.assertEqual(set(exported), {"format", "version", "sessions"})
            dialog._prepare_session_transfer.assert_called_once_with()

    def test_import_summary_limits_long_rename_lists(self) -> None:
        renames = tuple((f"Name {index}", f"Name {index} (2)") for index in range(12))

        summary = _import_summary_text(IMPORT_MODE_MERGE, 12, 3, renames)

        self.assertIn("…and 2 more", summary)
        self.assertNotIn("Name 11 →", summary)


if __name__ == "__main__":
    unittest.main()
