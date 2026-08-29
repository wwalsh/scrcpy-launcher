# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import configparser
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.paths import PORTABLEAPPS_DATA_ENV
from src.version import APP_VERSION


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_ROOT = PROJECT_ROOT / "packaging" / "portableapps"
APPINFO_ROOT = TEMPLATE_ROOT / "App" / "AppInfo"


def read_ini(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(path, encoding="utf-8")
    return parser


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise AssertionError(f"Not a PNG file: {path}")
    return struct.unpack(">II", data[16:24])


def ico_frames(path: Path) -> list[tuple[int, int, int]]:
    data = path.read_bytes()
    reserved, image_type, count = struct.unpack_from("<HHH", data)
    if reserved != 0 or image_type != 1:
        raise AssertionError(f"Not a Windows icon file: {path}")
    frames = []
    for index in range(count):
        width, height, _colors, _reserved, _planes, bits, size, offset = (
            struct.unpack_from("<BBBBHHII", data, 6 + (index * 16))
        )
        if offset + size > len(data):
            raise AssertionError(f"Invalid icon directory entry: {path}")
        frames.append((width or 256, height or 256, bits))
    return frames


class PortableAppsPackagingTests(unittest.TestCase):
    def test_template_contains_required_format_files(self) -> None:
        required = (
            "help.html",
            "App/AppInfo/appinfo.ini",
            "App/AppInfo/appicon.ico",
            "App/AppInfo/appicon_16.png",
            "App/AppInfo/appicon_32.png",
            "App/AppInfo/appicon_75.png",
            "App/AppInfo/appicon_128.png",
            "App/AppInfo/appicon_256.png",
            "App/AppInfo/Launcher/scrcpy-launcherPortable.ini",
            "App/DefaultData/config.json",
            "Other/Help/Images/appicon.png",
            "Other/Source/readme.txt",
            "Other/Source/launcher-license.txt",
        )

        for relative_path in required:
            with self.subTest(path=relative_path):
                self.assertTrue((TEMPLATE_ROOT / relative_path).is_file())

    def test_appinfo_uses_current_format_identity_and_version(self) -> None:
        appinfo = read_ini(APPINFO_ROOT / "appinfo.ini")
        version_parts = APP_VERSION.split(".")
        package_version = ".".join(version_parts + (["0"] * (4 - len(version_parts))))

        self.assertEqual(appinfo["Format"]["Type"], "PortableApps.comFormat")
        self.assertEqual(appinfo["Format"]["Version"], "3.9")
        self.assertEqual(appinfo["Details"]["Name"], "scrcpy-launcher Portable")
        self.assertEqual(appinfo["Details"]["AppID"], "scrcpy-launcherPortable")
        self.assertEqual(appinfo["Details"]["BaseAppName"], "scrcpy-launcher")
        self.assertEqual(
            appinfo["Details"]["Homepage"], "https://scrcpy-launcher.link"
        )
        self.assertEqual(appinfo["Details"]["Language"], "English")
        self.assertEqual(appinfo["Version"]["PackageVersion"], package_version)
        self.assertEqual(appinfo["Version"]["DisplayVersion"], APP_VERSION)
        self.assertEqual(appinfo["Dependencies"]["Requires64bitOS"], "yes")
        self.assertEqual(appinfo["Dependencies"]["RequiresAdmin"], "no")
        self.assertEqual(
            appinfo["Control"]["Start"], "scrcpy-launcherPortable.exe"
        )
        self.assertEqual(appinfo["Control"]["BaseAppID"], "NOT-NEEDED")

    def test_appinfo_declares_correct_license_permissions(self) -> None:
        license_metadata = read_ini(APPINFO_ROOT / "appinfo.ini")["License"]

        for field in ("Shareable", "OpenSource", "Freeware", "CommercialUse"):
            with self.subTest(field=field):
                self.assertEqual(license_metadata[field], "true")

    def test_launcher_routes_all_owned_data_to_portable_data(self) -> None:
        launcher = read_ini(
            APPINFO_ROOT / "Launcher" / "scrcpy-launcherPortable.ini"
        )

        self.assertEqual(
            launcher["Launch"]["ProgramExecutable"],
            r"scrcpy-launcher\scrcpy-launcher.exe",
        )
        self.assertIn(r'%PAL:DataDir%\config.json', launcher["Launch"]["CommandLineArguments"])
        self.assertEqual(launcher["Launch"]["CleanTemp"], "true")
        self.assertEqual(launcher["Launch"]["SinglePortableAppInstance"], "true")
        self.assertEqual(launcher["Launch"]["DirectoryMoveOK"], "yes")
        self.assertEqual(launcher["Launch"]["SupportsUNC"], "warn")
        self.assertNotIn("WaitForEXE1", launcher["Launch"])
        self.assertEqual(
            launcher["Environment"][PORTABLEAPPS_DATA_ENV],
            "%PAL:DataDir%",
        )

    def test_default_data_matches_canonical_fresh_configuration(self) -> None:
        canonical_path = PROJECT_ROOT / "packaging" / "default-config.json"
        portable_path = TEMPLATE_ROOT / "App" / "DefaultData" / "config.json"

        self.assertEqual(
            portable_path.read_text(encoding="utf-8"),
            canonical_path.read_text(encoding="utf-8"),
        )
        configuration = json.loads(portable_path.read_text(encoding="utf-8"))
        self.assertEqual(configuration["scrcpy_mode"], "bundled")
        self.assertEqual(configuration["scrcpy_path"], "scrcpy.exe")
        self.assertEqual(configuration["sessions"], [])

    def test_png_icons_have_required_dimensions(self) -> None:
        for size in (16, 32, 75, 128, 256):
            with self.subTest(size=size):
                self.assertEqual(
                    png_dimensions(APPINFO_ROOT / f"appicon_{size}.png"),
                    (size, size),
                )
        self.assertEqual(
            png_dimensions(TEMPLATE_ROOT / "Other" / "Help" / "Images" / "appicon.png"),
            (75, 75),
        )

    def test_windows_icon_contains_portableapps_required_frames(self) -> None:
        frames = ico_frames(APPINFO_ROOT / "appicon.ico")

        self.assertEqual(
            frames,
            [
                (16, 16, 8),
                (32, 32, 8),
                (48, 48, 8),
                (16, 16, 32),
                (32, 32, 32),
                (48, 48, 32),
                (256, 256, 32),
            ],
        )

    def test_help_and_source_notices_reference_public_project_materials(self) -> None:
        help_text = (TEMPLATE_ROOT / "help.html").read_text(encoding="utf-8")
        source_text = (TEMPLATE_ROOT / "Other" / "Source" / "readme.txt").read_text(
            encoding="utf-8"
        )
        launcher_license = (
            TEMPLATE_ROOT / "Other" / "Source" / "launcher-license.txt"
        ).read_text(encoding="utf-8")

        for expected in (
            "https://scrcpy-launcher.link",
            "https://github.com/wwalsh/scrcpy-launcher",
            "GPL-3.0-only",
            "Data",
        ):
            with self.subTest(text=expected):
                self.assertIn(expected, help_text + source_text)
        self.assertIn("GNU GENERAL PUBLIC LICENSE", launcher_license)
        self.assertIn("Version 2", launcher_license)

    def test_template_does_not_track_generated_payload_or_user_data(self) -> None:
        self.assertFalse((TEMPLATE_ROOT / "Data").exists())
        self.assertFalse((TEMPLATE_ROOT / "App" / "scrcpy-launcher").exists())
        self.assertFalse((TEMPLATE_ROOT / "scrcpy-launcherPortable.exe").exists())
        self.assertEqual(list(TEMPLATE_ROOT.rglob("*.exe")), [])

    def test_staging_script_uses_official_generator_and_safe_dist_output(self) -> None:
        script = (
            PROJECT_ROOT / "packaging" / "build_portableapps_launcher.ps1"
        ).read_text(encoding="utf-8")

        for expected in (
            "PortableApps.comLauncherGenerator.exe",
            "PortableApps.com Launcher 2.2.9 or newer is required",
            "PortableApps.comInstaller.exe",
            "PortableApps.com Installer 3.9.18 or newer is required",
            "Assert-SafeOutputPath",
            "Start-Process",
            'Wait = $true',
            'WindowStyle = "Hidden"',
            "dist\\portableapps-stage\\scrcpy-launcherPortable",
            "--portableapps-smoke-test",
            "Path With Spaces",
            "Get-FileSnapshot",
            "scrcpy-launcherPortable_${appVersion}_English.paf.exe",
            'App\\7zip\\7z.exe',
            "PortableApps installer payload integrity test",
            "PortableApps installer payload unexpectedly contains user Data",
        ):
            with self.subTest(text=expected):
                self.assertIn(expected, script)
        self.assertNotIn("RMDir /r", script)

    def test_staged_launcher_and_smoke_verification_phases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "scrcpy-launcherPortable"
            shutil.copytree(TEMPLATE_ROOT, package)
            payload = package / "App" / "scrcpy-launcher"
            (payload / "_internal").mkdir(parents=True)
            (payload / "licenses").mkdir()
            for filename in (
                "scrcpy-launcher.exe",
                "LICENSE",
                "THIRD-PARTY-NOTICES.md",
            ):
                (payload / filename).write_bytes(b"test")

            command = [
                sys.executable,
                str(PROJECT_ROOT / "packaging" / "verify_portableapps.py"),
                "--package-dir",
                str(package),
                "--allow-missing-bundled-tools",
            ]
            staged = subprocess.run(
                [*command, "--phase", "staged"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(staged.returncode, 0, staged.stdout + staged.stderr)

            (package / "scrcpy-launcherPortable.exe").write_bytes(b"MZ" + (b"\0" * 2048))
            launcher = subprocess.run(
                [*command, "--phase", "launcher"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(launcher.returncode, 0, launcher.stdout + launcher.stderr)

            data_dir = package / "Data"
            (data_dir / "logs").mkdir(parents=True)
            shutil.copy2(
                package / "App" / "DefaultData" / "config.json",
                data_dir / "config.json",
            )
            (data_dir / "logs" / "portableapps-smoke.log").write_text(
                "PortableApps launcher integration smoke test passed",
                encoding="utf-8",
            )
            smoke = subprocess.run(
                [*command, "--phase", "smoke"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(smoke.returncode, 0, smoke.stdout + smoke.stderr)


if __name__ == "__main__":
    unittest.main()
