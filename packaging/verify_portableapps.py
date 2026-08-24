# SPDX-License-Identifier: GPL-3.0-only

"""Verify an unpacked scrcpy-launcher PortableApps.com package."""

from __future__ import annotations

import argparse
import configparser
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import CURRENT_SCHEMA_VERSION, SCRCPY_MODE_BUNDLED
from src.paths import PORTABLEAPPS_DATA_ENV
from src.scrcpy_runtime import validate_bundled_installation
from src.version import APP_VERSION


class PortableAppsVerificationError(RuntimeError):
    """A staged PortableApps package violates its layout contract."""


def _read_ini(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    if not parser.read(path, encoding="utf-8"):
        raise PortableAppsVerificationError(f"Required INI file is missing: {path}")
    return parser


def _expected_package_version() -> str:
    parts = APP_VERSION.split(".")
    return ".".join(parts + (["0"] * (4 - len(parts))))


def _expected_default_config() -> dict[str, object]:
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "scrcpy_mode": SCRCPY_MODE_BUNDLED,
        "scrcpy_path": "scrcpy.exe",
        "sessions": [],
    }


def _read_json(path: Path, description: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PortableAppsVerificationError(
            f"{description} is missing or invalid: {path}: {exc}"
        ) from exc


def verify_portableapps_package(
    package_dir: Path,
    *,
    phase: str,
    require_bundled_tools: bool = True,
) -> None:
    package_dir = package_dir.resolve()
    if package_dir.name != "scrcpy-launcherPortable" or not package_dir.is_dir():
        raise PortableAppsVerificationError(
            f"PortableApps package root must be scrcpy-launcherPortable: {package_dir}"
        )

    appinfo_path = package_dir / "App" / "AppInfo" / "appinfo.ini"
    appinfo = _read_ini(appinfo_path)
    expected_metadata = {
        ("Format", "Type"): "PortableApps.comFormat",
        ("Format", "Version"): "3.9",
        ("Details", "AppID"): "scrcpy-launcherPortable",
        ("Version", "PackageVersion"): _expected_package_version(),
        ("Version", "DisplayVersion"): APP_VERSION,
        ("Control", "Start"): "scrcpy-launcherPortable.exe",
    }
    for (section, key), expected in expected_metadata.items():
        actual = appinfo.get(section, key, fallback=None)
        if actual != expected:
            raise PortableAppsVerificationError(
                f"appinfo.ini {section}.{key} is {actual!r}; expected {expected!r}"
            )

    launcher_ini = _read_ini(
        package_dir
        / "App"
        / "AppInfo"
        / "Launcher"
        / "scrcpy-launcherPortable.ini"
    )
    if launcher_ini.get("Environment", PORTABLEAPPS_DATA_ENV, fallback=None) != "%PAL:DataDir%":
        raise PortableAppsVerificationError(
            f"Launcher does not assign {PORTABLEAPPS_DATA_ENV} to PortableApps Data"
        )
    command_line = launcher_ini.get("Launch", "CommandLineArguments", fallback="")
    if r"%PAL:DataDir%\config.json" not in command_line:
        raise PortableAppsVerificationError(
            "Launcher does not pass the PortableApps configuration path"
        )

    required_template_paths = (
        "help.html",
        "App/AppInfo/appicon.ico",
        "App/AppInfo/appicon_16.png",
        "App/AppInfo/appicon_32.png",
        "App/AppInfo/appicon_75.png",
        "App/AppInfo/appicon_128.png",
        "App/AppInfo/appicon_256.png",
        "Other/Help/Images/appicon.png",
        "Other/Source/readme.txt",
        "Other/Source/launcher-license.txt",
    )
    for relative in required_template_paths:
        if not (package_dir / relative).is_file():
            raise PortableAppsVerificationError(f"Package file is missing: {relative}")

    default_path = package_dir / "App" / "DefaultData" / "config.json"
    if _read_json(default_path, "PortableApps default configuration") != _expected_default_config():
        raise PortableAppsVerificationError(
            "PortableApps default configuration does not match the fresh-install contract"
        )

    payload = package_dir / "App" / "scrcpy-launcher"
    required_payload_paths = (
        "scrcpy-launcher.exe",
        "_internal",
        "LICENSE",
        "THIRD-PARTY-NOTICES.md",
        "licenses",
    )
    for relative in required_payload_paths:
        if not (payload / relative).exists():
            raise PortableAppsVerificationError(f"Application payload is missing: {relative}")
    for forbidden in (
        "portable.marker",
        "default-config.json",
        "config.json",
        "config.json.bak",
    ):
        if (payload / forbidden).exists():
            raise PortableAppsVerificationError(
                f"Application payload contains portable or user state: {forbidden}"
            )
    if require_bundled_tools:
        try:
            validate_bundled_installation(root=payload)
        except Exception as exc:
            raise PortableAppsVerificationError(str(exc)) from exc

    portable_launcher = package_dir / "scrcpy-launcherPortable.exe"
    data_dir = package_dir / "Data"
    if phase == "staged":
        if portable_launcher.exists():
            raise PortableAppsVerificationError("Staged package already contains a launcher")
        if data_dir.exists():
            raise PortableAppsVerificationError("Staged package already contains user Data")
    else:
        if not portable_launcher.is_file():
            raise PortableAppsVerificationError("Generated portable launcher is missing")
        if portable_launcher.stat().st_size < 1024 or portable_launcher.read_bytes()[:2] != b"MZ":
            raise PortableAppsVerificationError("Generated portable launcher is not a Windows EXE")

    if phase == "launcher" and data_dir.exists():
        raise PortableAppsVerificationError("Launcher generation unexpectedly created user Data")
    if phase == "smoke":
        config_path = data_dir / "config.json"
        log_path = data_dir / "logs" / "portableapps-smoke.log"
        if _read_json(config_path, "PortableApps runtime configuration") != _expected_default_config():
            raise PortableAppsVerificationError(
                "PortableApps runtime configuration does not match its seeded default"
            )
        if not log_path.is_file() or "smoke test passed" not in log_path.read_text(
            encoding="utf-8"
        ):
            raise PortableAppsVerificationError("PortableApps smoke-test log is missing")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--phase", choices=("staged", "launcher", "smoke"), required=True)
    parser.add_argument("--allow-missing-bundled-tools", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        verify_portableapps_package(
            args.package_dir,
            phase=args.phase,
            require_bundled_tools=not args.allow_missing_bundled_tools,
        )
    except PortableAppsVerificationError as exc:
        print(f"PortableApps verification failed: {exc}")
        return 1
    print(f"PortableApps {args.phase} verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
