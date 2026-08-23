# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src.config_recovery import (
    BackupInvalidError,
    BackupRestoreError,
    ConfigRecoveryError,
    inspect_recovery,
    open_config_folder,
    restore_backup,
)


VALID = {"schema_version": 1, "scrcpy_path": "scrcpy.exe", "sessions": []}


class ConfigRecoveryTests(unittest.TestCase):
    def _paths(self, directory: str) -> tuple[Path, Path]:
        primary = Path(directory) / "config.json"
        return primary, Path(f"{primary}.bak")

    def test_inspection_reports_valid_primary_and_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            primary, backup = self._paths(directory)
            primary.write_text(json.dumps(VALID), encoding="utf-8")
            backup.write_text(json.dumps(VALID), encoding="utf-8")

            inspection = inspect_recovery(primary)

            self.assertTrue(inspection.primary_valid)
            self.assertTrue(inspection.backup_valid)

    def test_inspection_reports_each_invalid_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            primary, backup = self._paths(directory)
            primary.write_text("{broken", encoding="utf-8")
            backup.write_text("[]", encoding="utf-8")

            inspection = inspect_recovery(primary)

            self.assertFalse(inspection.primary_valid)
            self.assertFalse(inspection.backup_valid)

    def test_inspection_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            primary, backup = self._paths(directory)
            primary.write_text("{broken", encoding="utf-8")
            backup.write_text(json.dumps(VALID), encoding="utf-8")
            before = (primary.read_bytes(), backup.read_bytes())

            inspect_recovery(primary)

            self.assertEqual((primary.read_bytes(), backup.read_bytes()), before)

    def test_restore_archives_primary_and_leaves_backup_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            primary, backup = self._paths(directory)
            corrupt = b"{broken"
            primary.write_bytes(corrupt)
            backup.write_text(json.dumps(VALID), encoding="utf-8")
            backup_before = backup.read_bytes()
            inspection = inspect_recovery(primary)

            restored = restore_backup(
                inspection,
                now=lambda: datetime(2026, 8, 22, 12, 34, 56),
            )

            archive = Path(directory) / "config.json.corrupt-20260822-123456"
            self.assertEqual(archive.read_bytes(), corrupt)
            self.assertEqual(backup.read_bytes(), backup_before)
            self.assertEqual(restored.scrcpy_path, "scrcpy.exe")
            self.assertEqual(json.loads(primary.read_text(encoding="utf-8")), VALID)

    def test_restore_handles_missing_primary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            primary, backup = self._paths(directory)
            backup.write_text(json.dumps(VALID), encoding="utf-8")

            restored = restore_backup(inspect_recovery(primary))

            self.assertEqual(restored.scrcpy_path, "scrcpy.exe")
            self.assertEqual(list(Path(directory).glob("*.corrupt-*")), [])

    def test_restore_does_not_touch_predictable_adjacent_temp_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            primary, backup = self._paths(directory)
            primary.write_text("{broken", encoding="utf-8")
            backup.write_text(json.dumps(VALID), encoding="utf-8")
            predictable = primary.parent / f"{primary.name}.restore.tmp"
            predictable.write_text("unrelated", encoding="utf-8")

            restore_backup(inspect_recovery(primary))

            self.assertEqual(predictable.read_text(encoding="utf-8"), "unrelated")

    def test_restore_rejects_invalid_backup_without_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            primary, backup = self._paths(directory)
            primary.write_text("{primary", encoding="utf-8")
            backup.write_text("{backup", encoding="utf-8")
            before = (primary.read_bytes(), backup.read_bytes())

            with self.assertRaises(BackupInvalidError):
                restore_backup(inspect_recovery(primary))

            self.assertEqual((primary.read_bytes(), backup.read_bytes()), before)

    def test_restore_revalidates_backup_if_it_changes_after_inspection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            primary, backup = self._paths(directory)
            primary.write_text("{primary", encoding="utf-8")
            backup.write_text(json.dumps(VALID), encoding="utf-8")
            inspection = inspect_recovery(primary)
            backup.write_text("{now broken", encoding="utf-8")
            before = (primary.read_bytes(), backup.read_bytes())

            with self.assertRaises(BackupInvalidError):
                restore_backup(inspection)

            self.assertEqual((primary.read_bytes(), backup.read_bytes()), before)

    def test_restore_copy_failure_leaves_primary_and_backup_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            primary, backup = self._paths(directory)
            primary.write_text("{primary", encoding="utf-8")
            backup.write_text(json.dumps(VALID), encoding="utf-8")
            inspection = inspect_recovery(primary)
            before = (primary.read_bytes(), backup.read_bytes())

            with patch("src.config_recovery.atomic_copy", side_effect=OSError("copy failed")):
                with self.assertRaises(BackupRestoreError):
                    restore_backup(inspection)

            self.assertEqual((primary.read_bytes(), backup.read_bytes()), before)

    def test_open_config_folder_creates_and_opens_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "nested" / "config.json"
            with patch("src.config_recovery.os.startfile", create=True) as startfile:
                open_config_folder(config_path)

            self.assertTrue(config_path.parent.is_dir())
            startfile.assert_called_once_with(config_path.parent.resolve())


if __name__ == "__main__":
    unittest.main()
