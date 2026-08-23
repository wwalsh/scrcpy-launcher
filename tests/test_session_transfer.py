# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.config import Session
from src.safe_io import MAX_JSON_FILE_BYTES
from src.session_transfer import (
    SESSION_BACKUP_FORMAT,
    SESSION_BACKUP_VERSION,
    SessionBackupReadError,
    SessionBackupValidationError,
    SessionBackupWriteError,
    UnsupportedSessionBackupVersionError,
    export_session_backup,
    load_session_backup,
    parse_session_backup,
)


class SessionTransferTests(unittest.TestCase):
    def test_export_and_import_round_trip_unicode_sessions(self) -> None:
        sessions = (
            Session("Téléphone 📱", ["--serial=ABC", "--window-title=Téléphone"]),
            Session("Tablet", []),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.json"

            export_session_backup(path, sessions)

            self.assertEqual(load_session_backup(path), sessions)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["format"], SESSION_BACKUP_FORMAT)
            self.assertEqual(data["version"], SESSION_BACKUP_VERSION)
            self.assertNotIn("scrcpy_path", data)
            self.assertNotIn("scrcpy_mode", data)
            self.assertNotIn("schema_version", data)

    def test_empty_session_backup_is_valid(self) -> None:
        data = {
            "format": SESSION_BACKUP_FORMAT,
            "version": SESSION_BACKUP_VERSION,
            "sessions": [],
        }

        self.assertEqual(parse_session_backup(data), ())

    def test_rejects_wrong_format_invalid_sessions_and_duplicate_names(self) -> None:
        invalid = (
            {},
            {"format": "other", "version": 1, "sessions": []},
            {"format": SESSION_BACKUP_FORMAT, "version": 1, "sessions": {}},
            {
                "format": SESSION_BACKUP_FORMAT,
                "version": 1,
                "sessions": [
                    {"name": "Phone", "args": []},
                    {"name": "phone", "args": []},
                ],
            },
        )
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(SessionBackupValidationError):
                parse_session_backup(data)

    def test_rejects_malformed_json_with_location(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.json"
            path.write_text('{"sessions": [}', encoding="utf-8")

            with self.assertRaisesRegex(SessionBackupValidationError, r"line 1, column"):
                load_session_backup(path)

    def test_rejects_future_backup_version(self) -> None:
        data = {
            "format": SESSION_BACKUP_FORMAT,
            "version": SESSION_BACKUP_VERSION + 1,
            "sessions": [],
        }

        with self.assertRaisesRegex(UnsupportedSessionBackupVersionError, "newer"):
            parse_session_backup(data)

    def test_failed_export_does_not_replace_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.json"
            path.write_text("original", encoding="utf-8")

            with patch("src.safe_io.os.replace", side_effect=OSError("blocked")):
                with self.assertRaises(SessionBackupWriteError):
                    export_session_backup(path, [Session("Phone", [])])

            self.assertEqual(path.read_text(encoding="utf-8"), "original")
            self.assertFalse(Path(f"{path}.tmp").exists())

    def test_export_does_not_touch_predictable_adjacent_temp_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.json"
            predictable = Path(f"{path}.tmp")
            predictable.write_text("unrelated", encoding="utf-8")

            export_session_backup(path, [Session("Phone", [])])

            self.assertEqual(predictable.read_text(encoding="utf-8"), "unrelated")

    def test_import_rejects_oversized_json_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.json"
            path.write_bytes(b" " * (MAX_JSON_FILE_BYTES + 1))

            with self.assertRaisesRegex(SessionBackupReadError, "too large"):
                load_session_backup(path)

    def test_invalid_export_does_not_touch_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.json"
            path.write_text("original", encoding="utf-8")

            with self.assertRaises(SessionBackupValidationError):
                export_session_backup(path, [Session("Phone", [""])])

            self.assertEqual(path.read_text(encoding="utf-8"), "original")


if __name__ == "__main__":
    unittest.main()
