# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.bundled_manifest import BUNDLED_FILE_HASHES
from src.config import SCRCPY_MODE_BUNDLED, SCRCPY_MODE_CUSTOM
from src.scrcpy_runtime import (
    BUNDLED_SCRCPY_VERSION,
    ScrcpyResolutionError,
    application_root,
    bundled_scrcpy_path,
    clear_bundled_validation_cache,
    resolve_scrcpy,
    validate_bundled_installation,
)


class ScrcpyRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_bundled_validation_cache()

    def tearDown(self) -> None:
        clear_bundled_validation_cache()

    @staticmethod
    def _write_bundle(root: Path, files: dict[str, bytes]) -> Path:
        bundle = root / "tools" / "scrcpy"
        bundle.mkdir(parents=True)
        inventory = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
        for filename, data in files.items():
            path = bundle / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (bundle / "BUNDLE-METADATA.json").write_text(
            json.dumps(
                {
                    "bundle": {"version": BUNDLED_SCRCPY_VERSION},
                    "files": inventory,
                }
            ),
            encoding="utf-8",
        )
        return bundle

    def test_frozen_application_root_follows_launcher_executable(self) -> None:
        root = application_root(frozen=True, executable="D:/Portable/scrcpy-launcher.exe")

        self.assertEqual(root, Path("D:/Portable").resolve())
        self.assertEqual(
            bundled_scrcpy_path(root=root),
            root / "tools" / "scrcpy" / "scrcpy.exe",
        )

    def test_bundled_resolution_is_relocatable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {"scrcpy.exe": b"scrcpy"}
            executable = self._write_bundle(root, files) / "scrcpy.exe"

            with patch.dict(
                "src.scrcpy_runtime.BUNDLED_FILE_HASHES",
                {"scrcpy.exe": hashlib.sha256(b"scrcpy").hexdigest()},
                clear=True,
            ):
                result = resolve_scrcpy(SCRCPY_MODE_BUNDLED, "ignored.exe", root=root)

            self.assertEqual(result.path, executable.resolve())
            self.assertEqual(result.mode, SCRCPY_MODE_BUNDLED)

    def test_missing_bundled_executable_does_not_fall_back_to_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "src.scrcpy_runtime.shutil.which"
        ) as which:
            with self.assertRaisesRegex(ScrcpyResolutionError, "Repair or reinstall"):
                resolve_scrcpy(SCRCPY_MODE_BUNDLED, "scrcpy.exe", root=directory)

        which.assert_not_called()

    def test_custom_resolution_accepts_file_and_path_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "scrcpy.exe"
            executable.write_bytes(b"scrcpy")
            direct = resolve_scrcpy(SCRCPY_MODE_CUSTOM, str(executable))
            self.assertEqual(direct.path, executable.resolve())

            with patch("src.scrcpy_runtime.shutil.which", return_value=str(executable)):
                discovered = resolve_scrcpy(SCRCPY_MODE_CUSTOM, "scrcpy.exe")
            self.assertEqual(discovered.path, executable.resolve())

    def test_invalid_custom_path_is_reported_without_bundled_fallback(self) -> None:
        with patch("src.scrcpy_runtime.shutil.which", return_value=None):
            with self.assertRaisesRegex(ScrcpyResolutionError, "was not found"):
                resolve_scrcpy(SCRCPY_MODE_CUSTOM, "missing-scrcpy.exe")

    def test_package_validation_checks_version_required_files_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                "scrcpy.exe": b"scrcpy",
                "adb.exe": b"adb",
                "runtime.dll": b"dll",
            }
            bundle = self._write_bundle(root, files)
            inventory = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}

            with patch.dict(
                "src.scrcpy_runtime.BUNDLED_FILE_HASHES", inventory, clear=True
            ):
                self.assertEqual(
                    validate_bundled_installation(root=root),
                    (bundle / "scrcpy.exe").resolve(),
                )
                (bundle / "runtime.dll").write_bytes(b"tampered")
                with self.assertRaisesRegex(ScrcpyResolutionError, "failed verification"):
                    validate_bundled_installation(root=root)

    def test_package_validation_rejects_metadata_and_inventory_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {"scrcpy.exe": b"scrcpy", "runtime.dll": b"dll"}
            bundle = self._write_bundle(root, files)
            inventory = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}

            with patch.dict(
                "src.scrcpy_runtime.BUNDLED_FILE_HASHES", inventory, clear=True
            ):
                metadata_path = bundle / "BUNDLE-METADATA.json"
                metadata = json.loads(metadata_path.read_text())
                metadata["files"]["runtime.dll"] = "0" * 64
                metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
                with self.assertRaisesRegex(ScrcpyResolutionError, "metadata does not match"):
                    validate_bundled_installation(root=root)

                metadata["files"] = inventory
                metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
                (bundle / "unexpected.dll").write_bytes(b"unexpected")
                with self.assertRaisesRegex(ScrcpyResolutionError, "unexpected"):
                    validate_bundled_installation(root=root)

    def test_bundled_resolution_caches_successful_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            executable = root / "tools" / "scrcpy" / "scrcpy.exe"
            with patch(
                "src.scrcpy_runtime.validate_bundled_installation",
                return_value=executable,
            ) as validate:
                first = resolve_scrcpy(SCRCPY_MODE_BUNDLED, "ignored", root=root)
                second = resolve_scrcpy(SCRCPY_MODE_BUNDLED, "ignored", root=root)

            self.assertEqual(first.path, executable)
            self.assertEqual(second.path, executable)
            validate.assert_called_once_with(root=str(root))

    def test_trusted_inventory_matches_packaging_manifest(self) -> None:
        project_root = Path(__file__).resolve().parent.parent
        manifest = json.loads(
            (project_root / "packaging/dependencies/scrcpy-win64-v4.1.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(manifest["bundle"]["version"], BUNDLED_SCRCPY_VERSION)
        self.assertEqual(manifest["bundle"]["files"], BUNDLED_FILE_HASHES)


if __name__ == "__main__":
    unittest.main()
