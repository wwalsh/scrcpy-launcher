# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import json
import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.config import CURRENT_SCHEMA_VERSION, SCRCPY_MODE_BUNDLED


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "scrcpy_launcher_verify_release",
    PROJECT_ROOT / "packaging" / "verify_release.py",
)
assert SPEC is not None and SPEC.loader is not None
VERIFY_RELEASE = importlib.util.module_from_spec(SPEC)
sys_modules_name = SPEC.name
sys.modules[sys_modules_name] = VERIFY_RELEASE
SPEC.loader.exec_module(VERIFY_RELEASE)

PORTABLE_DEFAULT_CONFIG = VERIFY_RELEASE.PORTABLE_DEFAULT_CONFIG
PORTABLE_MARKER = VERIFY_RELEASE.PORTABLE_MARKER
ReleaseVerificationError = VERIFY_RELEASE.ReleaseVerificationError
verify_package_directory = VERIFY_RELEASE.verify_package_directory
verify_portable_archive = VERIFY_RELEASE.verify_portable_archive


class ReleaseVerificationTests(unittest.TestCase):
    def _create_package(self, root: Path) -> Path:
        package = root / "package"
        (package / "_internal").mkdir(parents=True)
        (package / "licenses").mkdir()
        (package / "scrcpy-launcher.exe").write_bytes(b"MZ launcher")
        (package / "_internal" / "runtime.dll").write_bytes(b"runtime")
        (package / "LICENSE").write_text("GPL", encoding="utf-8")
        (package / "THIRD-PARTY-NOTICES.md").write_text("notices", encoding="utf-8")
        (package / "licenses" / "GPL-3.0-only.txt").write_text("GPL", encoding="utf-8")
        return package

    def _default_config(self) -> bytes:
        return (
            json.dumps(
                {
                    "schema_version": CURRENT_SCHEMA_VERSION,
                    "scrcpy_mode": SCRCPY_MODE_BUNDLED,
                    "scrcpy_path": "scrcpy.exe",
                    "sessions": [],
                },
                indent=2,
            )
            + "\n"
        ).encode("utf-8")

    def _create_portable_zip(
        self, root: Path, package: Path, *, include_config: bool = False
    ) -> Path:
        archive_path = root / "portable.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            for path in package.rglob("*"):
                if path.is_file():
                    relative = path.relative_to(package).as_posix()
                    archive.write(path, f"scrcpy-launcher/{relative}")
            archive.writestr(f"scrcpy-launcher/{PORTABLE_MARKER}", "portable\n")
            archive.writestr(
                f"scrcpy-launcher/{PORTABLE_DEFAULT_CONFIG}", self._default_config()
            )
            if include_config:
                archive.writestr("scrcpy-launcher/config.json", "user data")
        return archive_path

    def test_valid_unbundled_installer_and_portable_layouts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = self._create_package(root)
            archive = self._create_portable_zip(root, package)

            verify_package_directory(package, require_bundled_tools=False)
            verify_portable_archive(
                archive, package, require_bundled_tools=False
            )

    def test_installer_staging_rejects_portable_or_user_state(self) -> None:
        for forbidden in (PORTABLE_MARKER, PORTABLE_DEFAULT_CONFIG, "config.json"):
            with self.subTest(forbidden=forbidden), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                package = self._create_package(root)
                (package / forbidden).write_text("unexpected", encoding="utf-8")

                with self.assertRaisesRegex(ReleaseVerificationError, "must not contain"):
                    verify_package_directory(package, require_bundled_tools=False)

    def test_portable_archive_rejects_embedded_user_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = self._create_package(root)
            archive = self._create_portable_zip(root, package, include_config=True)

            with self.assertRaisesRegex(ReleaseVerificationError, "overwrite user"):
                verify_portable_archive(
                    archive, package, require_bundled_tools=False
                )

    def test_verified_portable_upgrade_preserves_existing_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = self._create_package(root)
            archive = self._create_portable_zip(root, package)
            destination = root / "upgrade"
            portable_root = destination / "scrcpy-launcher"
            portable_root.mkdir(parents=True)
            config = portable_root / "config.json"
            original = b'{"sessions":[{"name":"keep me"}]}\n'
            config.write_bytes(original)

            verify_portable_archive(
                archive, package, require_bundled_tools=False
            )
            with zipfile.ZipFile(archive) as package_archive:
                package_archive.extractall(destination)

            self.assertEqual(config.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
