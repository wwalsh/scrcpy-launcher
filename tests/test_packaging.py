# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from src.config import Config
from src.config import SCRCPY_MODE_BUNDLED
from src.version import APP_VERSION


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class PackagingTests(unittest.TestCase):
    def test_personal_config_is_ignored_and_example_is_sanitized(self) -> None:
        ignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        example_path = PROJECT_ROOT / "config.example.json"
        example_text = example_path.read_text(encoding="utf-8")
        example = json.loads(example_text)

        self.assertIn("config.json", ignore)
        self.assertNotIn("C:\\Users\\", example_text)
        self.assertNotIn("ZY22KN79XD", example_text)
        self.assertEqual(example["scrcpy_mode"], SCRCPY_MODE_BUNDLED)

    def test_python_dependencies_are_exactly_pinned_and_hashed(self) -> None:
        for filename in ("requirements.txt", "requirements-build.txt"):
            text = (PROJECT_ROOT / filename).read_text(encoding="utf-8")
            with self.subTest(filename=filename):
                self.assertNotIn(">=", text)
                self.assertNotIn("~=", text)
                self.assertIn("==", text)
                self.assertIn("--hash=sha256:", text)

    def test_seeded_installer_config_is_valid(self) -> None:
        config = Config(PROJECT_ROOT / "packaging" / "default-config.json")
        self.assertEqual(config.scrcpy_mode, SCRCPY_MODE_BUNDLED)
        self.assertEqual(config.scrcpy_path, "scrcpy.exe")
        self.assertEqual(config.sessions, ())

    def test_packaging_assets_use_runtime_version(self) -> None:
        installer = (PROJECT_ROOT / "packaging" / "scrcpy-launcher.nsi").read_text(
            encoding="utf-8"
        )
        self.assertIn(f'!define AppVersion "{APP_VERSION}"', installer)

    def test_release_build_inputs_exist(self) -> None:
        for relative_path in (
            "LICENSE",
            "THIRD-PARTY-NOTICES.md",
            "scrcpy_launcher.py",
            "config.example.json",
            "icon.ico",
            "licenses/GPL-3.0-only.txt",
            "licenses/NSIS.txt",
            "licenses/Apache-2.0.txt",
            "licenses/Python-3.14.txt",
            "licenses/PyInstaller.txt",
            "licenses/Tcl-Tk.txt",
            "licenses/Zlib.txt",
            "licenses/pywin32.txt",
            "packaging/scrcpy-launcher.spec",
            "packaging/scrcpy-launcher.nsi",
            "packaging/nsis-safe-delete.nsh",
            "packaging/nsis-safe-delete-test.nsi",
            "packaging/test_installer_cleanup.ps1",
            "packaging/build.ps1",
            "packaging/stage_scrcpy.py",
            "packaging/verify_release.py",
            "packaging/dependencies/scrcpy-win64-v4.1.json",
            "packaging/generate_version_info.py",
            "docs/windows-lifecycle-test.md",
            "docs/security-model.md",
            "docs/user-guide.md",
            "docs/building.md",
            "src/update_check.py",
            "SECURITY.md",
            ".github/dependabot.yml",
            ".github/workflows/security-audit.yml",
            "packaging/security_audit.py",
            "packaging/dependencies/security-review.json",
        ):
            with self.subTest(path=relative_path):
                self.assertTrue((PROJECT_ROOT / relative_path).is_file())

    def test_project_declares_gpl_v3_only(self) -> None:
        license_text = (PROJECT_ROOT / "LICENSE").read_text(encoding="utf-8")
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertTrue(license_text.startswith("GNU GENERAL PUBLIC LICENSE\nVersion 3"))
        self.assertIn("`GPL-3.0-only`", readme)

    def test_authored_code_has_spdx_identifier(self) -> None:
        authored_files = [PROJECT_ROOT / "scrcpy_launcher.py"]
        authored_files.extend((PROJECT_ROOT / "src").glob("*.py"))
        authored_files.extend((PROJECT_ROOT / "tests").glob("*.py"))
        authored_files.extend(
            (
                PROJECT_ROOT / "packaging" / "build.ps1",
                PROJECT_ROOT / "packaging" / "stage_scrcpy.py",
                PROJECT_ROOT / "packaging" / "generate_version_info.py",
                PROJECT_ROOT / "packaging" / "verify_release.py",
                PROJECT_ROOT / "packaging" / "scrcpy-launcher.nsi",
                PROJECT_ROOT / "packaging" / "scrcpy-launcher.spec",
            )
        )

        for path in authored_files:
            with self.subTest(path=path.relative_to(PROJECT_ROOT)):
                first_lines = path.read_text(encoding="utf-8").splitlines()[:3]
                self.assertTrue(
                    any(
                        "SPDX-License-Identifier: GPL-3.0-only" in line
                        for line in first_lines
                    )
                )

    def test_packaging_includes_license_materials(self) -> None:
        build_script = (PROJECT_ROOT / "packaging" / "build.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn('Join-Path $projectRoot "LICENSE"', build_script)
        self.assertIn('Join-Path $projectRoot "THIRD-PARTY-NOTICES.md"', build_script)
        self.assertIn('Join-Path $projectRoot "licenses"', build_script)
        self.assertIn('"--licenses-dir"', build_script)

    def test_third_party_notices_cover_current_and_planned_components(self) -> None:
        notices = (PROJECT_ROOT / "THIRD-PARTY-NOTICES.md").read_text(
            encoding="utf-8"
        )

        for component in (
            "CPython",
            "pywin32",
            "Tcl/Tk",
            "PyInstaller",
            "NSIS",
            "OpenSSL",
            "zlib",
            "scrcpy client",
            "Android SDK Platform-Tools",
            "FFmpeg",
            "SDL",
            "libusb",
        ):
            with self.subTest(component=component):
                self.assertIn(component, notices)
        self.assertIn("SHA-256", notices)
        self.assertIn("corresponding-source", notices)

    def test_nsis_replaces_inno_in_the_build_pipeline(self) -> None:
        build_script = (PROJECT_ROOT / "packaging" / "build.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("Resolve-NsisCompiler", build_script)
        self.assertIn("$NsisCompiler", build_script)
        self.assertIn("NSIS_HOME", build_script)
        self.assertIn("PortableApps\\NSISPortable", build_script)
        self.assertIn("packaging\\scrcpy-launcher.nsi", build_script)
        self.assertNotIn("Inno Setup", build_script)
        self.assertFalse(
            (PROJECT_ROOT / "packaging" / "scrcpy-launcher.iss").exists()
        )

    def test_nsis_installer_preserves_upgrade_and_uninstall_safety(self) -> None:
        installer = (PROJECT_ROOT / "packaging" / "scrcpy-launcher.nsi").read_text(
            encoding="utf-8"
        )

        for required_text in (
            "Local\\scrcpy-launcher-tray",
            "{5A60C3DF-4333-45F0-A876-3DD49A85BE47}_is1",
            "unins000.exe",
            "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART",
            "RemoveOwnedAutostart",
            'IfFileExists "${ConfigPath}"',
            'IfFileExists "${ConfigPath}.bak"',
            "/SD IDNO",
            'Call SafeRemoveTree',
            'Call un.SafeRemoveTree',
            'StrCmp $0 "$LOCALAPPDATA\\Programs\\${AppName}" nsis_path_valid',
            "Also permanently remove",
            "Choose No to preserve all data",
        ):
            with self.subTest(text=required_text):
                self.assertIn(required_text, installer)
        self.assertNotIn("RMDir /r", installer)
        self.assertIn('Delete "${ConfigPath}"', installer)
        self.assertIn('Delete "${ConfigPath}.bak"', installer)
        self.assertIn("Unknown files in these folders are preserved", installer)
        self.assertNotIn("MUI_PAGE_DIRECTORY", installer)

    def test_security_policy_documents_accepted_runtime_window(self) -> None:
        policy = (PROJECT_ROOT / "docs" / "security-model.md").read_text(
            encoding="utf-8"
        )
        security = (PROJECT_ROOT / "SECURITY.md").read_text(encoding="utf-8")

        self.assertIn("SEC-RISK-001", policy)
        self.assertIn("Status:** Accepted", policy)
        self.assertIn("once per launcher or Settings process", policy)
        self.assertIn("same-user process", policy)
        self.assertIn("Reassess this acceptance", policy)
        self.assertIn("expires after 45 days", security)

    def test_user_documentation_covers_first_run(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        guide = (PROJECT_ROOT / "docs" / "user-guide.md").read_text(
            encoding="utf-8"
        )
        documentation_images = (
            "settings-overview-generated.png",
            "app-selector-generated.png",
        )

        for required_text in (
            "Five-minute quick start",
            "Prepare the Android device",
            "Create the first session",
            "Portable quick start",
            "Troubleshooting",
            "Get-FileHash",
            "not currently Authenticode signed",
        ):
            with self.subTest(text=required_text):
                self.assertIn(required_text, readme)
        for required_text in (
            "Application editions and storage",
            "Selecting an application",
            "Session import and export",
            "Configuration and recovery",
            "Updating and uninstalling",
            "Checking for updates",
        ):
            with self.subTest(text=required_text):
                self.assertIn(required_text, guide)
        for image_name in documentation_images:
            with self.subTest(image=image_name):
                image_path = PROJECT_ROOT / "docs" / "images" / image_name
                self.assertTrue(image_path.is_file())
                self.assertIn(image_name, readme + guide)
        self.assertIn("Machine-generated documentation image", readme)
        self.assertIn("Machine-generated documentation image", guide)
        self.assertIn("makes no automatic internet requests", readme)
        self.assertIn("No update check runs automatically", guide)

    def test_milestone_does_not_add_scrcpy_or_adb_binaries(self) -> None:
        forbidden_names = {"adb.exe", "scrcpy.exe", "scrcpy-server"}
        excluded_directories = {
            ".cache",
            ".git",
            ".venv",
            "build",
            "dist",
            "__pycache__",
        }
        found: list[Path] = []

        for current_root, directories, files in os.walk(PROJECT_ROOT):
            directories[:] = [
                name for name in directories if name not in excluded_directories
            ]
            for filename in files:
                if filename.lower() in forbidden_names:
                    found.append(Path(current_root, filename).relative_to(PROJECT_ROOT))

        self.assertEqual(found, [])

    def test_release_build_stages_verified_scrcpy_before_packaging(self) -> None:
        build_script = (PROJECT_ROOT / "packaging" / "build.ps1").read_text(
            encoding="utf-8"
        )

        stage_position = build_script.index('"packaging\\stage_scrcpy.py"')
        smoke_position = build_script.index("--package-smoke-test")
        archive_position = build_script.index("Compress-Archive")
        self.assertLess(stage_position, smoke_position)
        self.assertLess(smoke_position, archive_position)
        self.assertIn("$OfflineDependencies", build_script)
        self.assertIn("$SkipBundledTools", build_script)
        self.assertIn('"-unbundled"', build_script)
        self.assertIn('"--allow-missing-bundled-tools"', build_script)
        self.assertIn('"portable.marker"', build_script)
        self.assertIn('"default-config.json"', build_script)
        self.assertIn("$portableStageParent", build_script)
        self.assertIn('"packaging\\verify_release.py"', build_script)
        verification_position = build_script.index('"packaging\\verify_release.py"')
        hash_position = build_script.index("Get-FileHash")
        self.assertLess(archive_position, verification_position)
        self.assertLess(verification_position, hash_position)


if __name__ == "__main__":
    unittest.main()
