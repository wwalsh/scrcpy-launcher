# SPDX-License-Identifier: GPL-3.0-only

"""Verify installed and portable release layouts before publishing artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import CURRENT_SCHEMA_VERSION, SCRCPY_MODE_BUNDLED
from src.scrcpy_runtime import validate_bundled_installation


class ReleaseVerificationError(RuntimeError):
    """A release artifact violates the packaging lifecycle contract."""


PACKAGE_REQUIRED_PATHS = (
    "scrcpy-launcher.exe",
    "_internal",
    "LICENSE",
    "THIRD-PARTY-NOTICES.md",
    "licenses",
)
PORTABLE_MARKER = "portable.marker"
PORTABLE_DEFAULT_CONFIG = "default-config.json"
USER_CONFIG_NAMES = (
    "config.json",
    "config.json.bak",
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_default_config(data: bytes, description: str) -> None:
    try:
        config = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseVerificationError(
            f"{description} is not valid UTF-8 JSON: {exc}"
        ) from exc
    expected = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "scrcpy_mode": SCRCPY_MODE_BUNDLED,
        "scrcpy_path": "scrcpy.exe",
        "sessions": [],
    }
    if config != expected:
        raise ReleaseVerificationError(
            f"{description} does not match the fresh-install configuration contract"
        )


def verify_package_directory(
    package_dir: Path, *, require_bundled_tools: bool = True
) -> None:
    """Verify the installer staging tree contains no portable or user state."""
    package_dir = package_dir.resolve()
    if not package_dir.is_dir():
        raise ReleaseVerificationError(f"Package directory is missing: {package_dir}")
    for relative in PACKAGE_REQUIRED_PATHS:
        if not (package_dir / relative).exists():
            raise ReleaseVerificationError(f"Package file is missing: {relative}")
    for forbidden in (*USER_CONFIG_NAMES, PORTABLE_MARKER, PORTABLE_DEFAULT_CONFIG):
        if (package_dir / forbidden).exists():
            raise ReleaseVerificationError(
                f"Installer package must not contain portable/user state: {forbidden}"
            )
    if require_bundled_tools:
        try:
            validate_bundled_installation(root=package_dir)
        except Exception as exc:
            raise ReleaseVerificationError(str(exc)) from exc


def _safe_portable_member(member: zipfile.ZipInfo) -> tuple[str, str] | None:
    name = member.filename.replace("\\", "/")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ReleaseVerificationError(f"Unsafe portable ZIP member: {member.filename}")
    if path.parts[0] != "scrcpy-launcher":
        raise ReleaseVerificationError(
            f"Unexpected portable ZIP root: {member.filename}"
        )
    if member.is_dir() or len(path.parts) == 1:
        return None
    return "/".join(path.parts[1:]), name


def verify_portable_archive(
    archive_path: Path,
    package_dir: Path,
    *,
    require_bundled_tools: bool = True,
) -> None:
    """Verify portable isolation and that the ZIP exactly wraps the staged package."""
    archive_path = archive_path.resolve()
    package_dir = package_dir.resolve()
    if not archive_path.is_file():
        raise ReleaseVerificationError(f"Portable archive is missing: {archive_path}")

    try:
        with zipfile.ZipFile(archive_path) as archive:
            members: dict[str, zipfile.ZipInfo] = {}
            for member in archive.infolist():
                parsed = _safe_portable_member(member)
                if parsed is None:
                    continue
                relative, _ = parsed
                if relative in members:
                    raise ReleaseVerificationError(
                        f"Duplicate portable ZIP member: {relative}"
                    )
                members[relative] = member

            for required in (*PACKAGE_REQUIRED_PATHS, PORTABLE_MARKER, PORTABLE_DEFAULT_CONFIG):
                if required not in members and not any(
                    name.startswith(required.rstrip("/") + "/") for name in members
                ):
                    raise ReleaseVerificationError(
                        f"Portable archive is missing: {required}"
                    )
            for forbidden in USER_CONFIG_NAMES:
                if forbidden in members:
                    raise ReleaseVerificationError(
                        f"Portable archive would overwrite user configuration: {forbidden}"
                    )

            marker = archive.read(members[PORTABLE_MARKER]).decode("ascii").strip()
            if marker != "portable":
                raise ReleaseVerificationError("Portable marker is invalid")
            _validate_default_config(
                archive.read(members[PORTABLE_DEFAULT_CONFIG]),
                "Portable default configuration",
            )

            expected_files = {
                path.relative_to(package_dir).as_posix(): path
                for path in package_dir.rglob("*")
                if path.is_file()
            }
            archive_package_files = set(members) - {
                PORTABLE_MARKER,
                PORTABLE_DEFAULT_CONFIG,
            }
            if archive_package_files != set(expected_files):
                missing = sorted(set(expected_files) - archive_package_files)
                unexpected = sorted(archive_package_files - set(expected_files))
                raise ReleaseVerificationError(
                    "Portable package inventory differs from installer staging "
                    f"(missing={missing}, unexpected={unexpected})"
                )
            for relative, source in expected_files.items():
                if _sha256_bytes(archive.read(members[relative])) != _sha256_file(source):
                    raise ReleaseVerificationError(
                        f"Portable package file differs from staging: {relative}"
                    )
    except zipfile.BadZipFile as exc:
        raise ReleaseVerificationError(
            f"Portable archive is not a valid ZIP: {archive_path}"
        ) from exc

    if require_bundled_tools and "tools/scrcpy/scrcpy.exe" not in members:
        raise ReleaseVerificationError("Portable archive has no bundled scrcpy executable")


def verify_installer(installer_path: Path) -> None:
    """Perform basic checks that NSIS produced a Windows executable."""
    if not installer_path.is_file():
        raise ReleaseVerificationError(f"Installer is missing: {installer_path}")
    if installer_path.stat().st_size < 1024 or installer_path.read_bytes()[:2] != b"MZ":
        raise ReleaseVerificationError(f"Installer is not a valid Windows executable: {installer_path}")


def verify_portableapps_installer(installer_path: Path) -> None:
    """Check the official PortableApps installer artifact identity and executable header."""
    if not installer_path.name.endswith(".paf.exe"):
        raise ReleaseVerificationError(
            f"PortableApps installer must end in .paf.exe: {installer_path}"
        )
    verify_installer(installer_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--portable-archive", type=Path, required=True)
    parser.add_argument("--installer", type=Path)
    parser.add_argument("--portableapps-installer", type=Path)
    parser.add_argument("--allow-missing-bundled-tools", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    require_tools = not args.allow_missing_bundled_tools
    try:
        verify_package_directory(args.package_dir, require_bundled_tools=require_tools)
        verify_portable_archive(
            args.portable_archive,
            args.package_dir,
            require_bundled_tools=require_tools,
        )
        if args.installer is not None:
            verify_installer(args.installer)
        if args.portableapps_installer is not None:
            verify_portableapps_installer(args.portableapps_installer)
    except ReleaseVerificationError as exc:
        print(f"Release verification failed: {exc}")
        return 1
    print("Release lifecycle verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
