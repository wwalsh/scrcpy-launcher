# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.config import (
    CURRENT_SCHEMA_VERSION,
    SCRCPY_MODE_BUNDLED,
    SCRCPY_MODE_CUSTOM,
    Config,
    ConfigError,
    ConfigValidationError,
    MAX_ARGS_PER_SESSION,
    MAX_ARG_CHARS,
    MAX_SESSIONS,
    MAX_SESSION_NAME_CHARS,
    MAX_SCRCPY_PATH_CHARS,
    Session,
    UnsupportedSchemaVersionError,
)
from src.safe_io import MAX_JSON_FILE_BYTES


class ConfigTests(unittest.TestCase):
    def _write_config(self, directory: str, data: object) -> Path:
        path = Path(directory) / "config.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_loads_and_normalizes_valid_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(
                directory,
                {
                    "scrcpy_path": "  scrcpy.exe  ",
                    "sessions": [{"name": "  Phone  ", "args": ["  --no-audio  "]}],
                },
            )

            config = Config(path)

            self.assertEqual(config.scrcpy_path, "scrcpy.exe")
            self.assertEqual(config.scrcpy_mode, SCRCPY_MODE_CUSTOM)
            self.assertEqual(config.sessions[0].name, "Phone")
            self.assertEqual(config.sessions[0].args, ["--no-audio"])
            self.assertEqual(config.source_schema_version, 0)
            self.assertTrue(config.needs_migration_save)

    def test_loads_current_schema_without_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(
                directory,
                {
                    "schema_version": CURRENT_SCHEMA_VERSION,
                    "scrcpy_mode": SCRCPY_MODE_BUNDLED,
                    "scrcpy_path": "scrcpy.exe",
                    "sessions": [],
                },
            )

            config = Config(path)

            self.assertEqual(config.source_schema_version, CURRENT_SCHEMA_VERSION)
            self.assertEqual(config.scrcpy_mode, SCRCPY_MODE_BUNDLED)
            self.assertFalse(config.needs_migration_save)

    def test_schema_v1_migration_preserves_external_scrcpy_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(
                directory,
                {
                    "schema_version": 1,
                    "scrcpy_path": "C:/tools/scrcpy.exe",
                    "sessions": [],
                },
            )

            config = Config(path)

            self.assertEqual(config.scrcpy_mode, SCRCPY_MODE_CUSTOM)
            self.assertEqual(config.scrcpy_path, "C:/tools/scrcpy.exe")
            self.assertTrue(config.needs_migration_save)

    def test_rejects_future_schema_without_changing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(
                directory,
                {"schema_version": 99, "scrcpy_path": "scrcpy.exe", "sessions": []},
            )
            original = path.read_bytes()

            with self.assertRaises(UnsupportedSchemaVersionError):
                Config(path)

            self.assertEqual(path.read_bytes(), original)

    def test_rejects_invalid_schema_version_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(
                directory,
                {"schema_version": True, "scrcpy_path": "scrcpy.exe", "sessions": []},
            )

            with self.assertRaises(ConfigValidationError):
                Config(path)

    def test_reports_invalid_json_location(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"sessions": [}', encoding="utf-8")

            with self.assertRaisesRegex(ConfigError, r"line 1, column"):
                Config(path)

    def test_requires_object_at_top_level(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(directory, [])

            with self.assertRaisesRegex(ConfigError, "JSON object"):
                Config(path)

    def test_requires_sessions_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(
                directory,
                {"scrcpy_path": "scrcpy.exe", "sessions": {}},
            )

            with self.assertRaisesRegex(ConfigError, "'sessions' must be a list"):
                Config(path)

    def test_rejects_duplicate_session_names_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(
                directory,
                {
                    "scrcpy_path": "scrcpy.exe",
                    "sessions": [
                        {"name": "Phone", "args": []},
                        {"name": "phone", "args": []},
                    ],
                },
            )

            with self.assertRaisesRegex(ConfigError, "Duplicate session name"):
                Config(path)

    def test_rejects_multiline_names_and_empty_arguments(self) -> None:
        invalid_sessions = [
            {"name": "Phone\nTwo", "args": []},
            {"name": "Phone", "args": ["  "]},
        ]
        for session in invalid_sessions:
            with self.subTest(session=session), tempfile.TemporaryDirectory() as directory:
                path = self._write_config(
                    directory,
                    {"scrcpy_path": "scrcpy.exe", "sessions": [session]},
                )
                with self.assertRaises(ConfigError):
                    Config(path)

    def test_rejects_session_resource_limits(self) -> None:
        cases = (
            [{"name": "x" * (MAX_SESSION_NAME_CHARS + 1), "args": []}],
            [{"name": "Phone", "args": ["--x"] * (MAX_ARGS_PER_SESSION + 1)}],
            [{"name": "Phone", "args": ["x" * (MAX_ARG_CHARS + 1)]}],
            [{"name": f"Phone {index}", "args": []} for index in range(MAX_SESSIONS + 1)],
        )
        for sessions in cases:
            with self.subTest(size=len(sessions)), tempfile.TemporaryDirectory() as directory:
                path = self._write_config(
                    directory,
                    {"scrcpy_path": "scrcpy.exe", "sessions": sessions},
                )
                with self.assertRaises(ConfigValidationError):
                    Config(path)

    def test_rejects_oversized_config_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_bytes(b" " * (MAX_JSON_FILE_BYTES + 1))

            with self.assertRaisesRegex(ConfigError, "too large"):
                Config(path)

    def test_set_scrcpy_path_rejects_empty_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(
                directory,
                {"scrcpy_path": "scrcpy.exe", "sessions": []},
            )
            config = Config(path)

            with self.assertRaisesRegex(ConfigError, "non-empty string"):
                config.set_scrcpy_path("  ")

            with self.assertRaisesRegex(ConfigError, "exceeds"):
                config.set_scrcpy_path("x" * (MAX_SCRCPY_PATH_CHARS + 1))

    def test_set_scrcpy_mode_rejects_unknown_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(
                directory,
                {"scrcpy_path": "scrcpy.exe", "sessions": []},
            )
            config = Config(path)

            with self.assertRaisesRegex(ConfigError, "must be one of"):
                config.set_scrcpy_mode("automatic")

    def test_duplicate_session_inserts_unique_independent_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(
                directory,
                {
                    "scrcpy_path": "scrcpy.exe",
                    "sessions": [
                        {"name": "Phone", "args": ["--serial=ABC"]},
                        {"name": "Phone copy", "args": []},
                    ],
                },
            )
            config = Config(path)

            duplicate_index = config.duplicate_session(0)

            self.assertEqual(duplicate_index, 1)
            self.assertEqual(config.sessions[1].name, "Phone copy 2")
            self.assertEqual(config.sessions[1].args, ["--serial=ABC"])
            config.sessions[1].args.append("--no-audio")
            self.assertEqual(config.sessions[0].args, ["--serial=ABC"])

    def test_duplicate_session_rejects_invalid_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(
                directory,
                {"scrcpy_path": "scrcpy.exe", "sessions": []},
            )
            config = Config(path)

            with self.assertRaisesRegex(ConfigError, "out of range"):
                config.duplicate_session(0)

    def test_move_session_reorders_without_changing_session_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(
                directory,
                {
                    "scrcpy_path": "scrcpy.exe",
                    "sessions": [
                        {"name": "One", "args": ["--serial=1"]},
                        {"name": "Two", "args": ["--serial=2"]},
                        {"name": "Three", "args": ["--serial=3"]},
                    ],
                },
            )
            config = Config(path)

            new_index = config.move_session(2, 0)

            self.assertEqual(new_index, 0)
            self.assertEqual([session.name for session in config.sessions], ["Three", "One", "Two"])
            self.assertEqual(config.sessions[0].args, ["--serial=3"])

    def test_move_session_validates_source_and_target_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(
                directory,
                {
                    "scrcpy_path": "scrcpy.exe",
                    "sessions": [{"name": "One", "args": []}],
                },
            )
            config = Config(path)

            for source, target in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                with self.subTest(source=source, target=target):
                    with self.assertRaisesRegex(ConfigError, "out of range"):
                        config.move_session(source, target)

    def test_replace_sessions_validates_everything_before_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(
                directory,
                {"scrcpy_path": "scrcpy.exe", "sessions": [{"name": "Original", "args": []}]},
            )
            config = Config(path)
            replacement = Session("Imported", ["--serial=ABC"])

            config.replace_sessions([replacement])
            replacement.args.append("--no-audio")

            self.assertEqual(config.sessions, (Session("Imported", ["--serial=ABC"]),))
            with self.assertRaisesRegex(ConfigError, "Duplicate session name"):
                config.replace_sessions([Session("One", []), Session("one", [])])
            self.assertEqual(config.sessions, (Session("Imported", ["--serial=ABC"]),))

    def test_merge_sessions_preserves_order_and_renames_case_insensitive_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(
                directory,
                {
                    "scrcpy_path": "scrcpy.exe",
                    "sessions": [
                        {"name": "Phone", "args": []},
                        {"name": "phone (2)", "args": []},
                    ],
                },
            )
            config = Config(path)

            result = config.merge_sessions(
                [Session("PHONE", ["--serial=ABC"]), Session("Tablet", [])]
            )

            self.assertEqual(
                [session.name for session in config.sessions],
                ["Phone", "phone (2)", "PHONE (3)", "Tablet"],
            )
            self.assertEqual(result.imported_count, 2)
            self.assertEqual(result.renamed, (("PHONE", "PHONE (3)"),))

    def test_failed_merge_does_not_partially_mutate_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(
                directory,
                {"scrcpy_path": "scrcpy.exe", "sessions": [{"name": "Original", "args": []}]},
            )
            config = Config(path)

            with self.assertRaisesRegex(ConfigError, "Duplicate session name"):
                config.merge_sessions([Session("Imported", []), Session("imported", [])])

            self.assertEqual([session.name for session in config.sessions], ["Original"])

    def test_save_preserves_previous_file_as_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(
                directory,
                {"scrcpy_path": "old.exe", "sessions": []},
            )
            config = Config(path)
            config.set_scrcpy_path("new.exe")

            with self.assertLogs("src.config", level="WARNING"):
                config.save()

            backup = json.loads(Path(f"{path}.bak").read_text(encoding="utf-8"))
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(backup["scrcpy_path"], "old.exe")
            self.assertEqual(saved["scrcpy_path"], "new.exe")
            self.assertEqual(saved["scrcpy_mode"], SCRCPY_MODE_CUSTOM)
            self.assertEqual(saved["schema_version"], CURRENT_SCHEMA_VERSION)
            self.assertFalse(config.needs_migration_save)

    def test_save_does_not_touch_predictable_adjacent_temp_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(
                directory,
                {"scrcpy_path": "old.exe", "sessions": []},
            )
            predictable_primary = Path(f"{path}.tmp")
            predictable_backup = Path(f"{path}.bak.tmp")
            predictable_primary.write_text("primary sentinel", encoding="utf-8")
            predictable_backup.write_text("backup sentinel", encoding="utf-8")
            config = Config(path)
            config.set_scrcpy_path("new.exe")

            with self.assertLogs("src.config", level="WARNING"):
                config.save()

            self.assertEqual(predictable_primary.read_text(), "primary sentinel")
            self.assertEqual(predictable_backup.read_text(), "backup sentinel")

    def test_save_does_not_replace_good_backup_with_corrupt_primary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(
                directory,
                {"scrcpy_path": "original.exe", "sessions": []},
            )
            config = Config(path)
            backup_path = Path(f"{path}.bak")
            backup_data = {"schema_version": 1, "scrcpy_path": "safe.exe", "sessions": []}
            backup_path.write_text(json.dumps(backup_data), encoding="utf-8")
            path.write_text("{broken", encoding="utf-8")
            config.set_scrcpy_path("replacement.exe")

            with self.assertLogs("src.config", level="WARNING"):
                config.save()

            self.assertEqual(json.loads(backup_path.read_text(encoding="utf-8")), backup_data)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["scrcpy_path"],
                "replacement.exe",
            )


if __name__ == "__main__":
    unittest.main()
