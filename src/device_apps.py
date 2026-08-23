# SPDX-License-Identifier: GPL-3.0-only

"""Discover applications through scrcpy 4.1 ``--list-apps``."""

from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .scrcpy_runtime import ScrcpyResolutionError, resolve_scrcpy


logger = logging.getLogger(__name__)
DEFAULT_APP_DISCOVERY_TIMEOUT = 20.0


class AppListParseError(ValueError):
    """scrcpy output does not match the supported app-list format."""


class AppDiscoveryError(RuntimeError):
    """Applications could not be retrieved from the selected Android device."""


@dataclass(frozen=True)
class DeviceApp:
    name: str
    package_name: str
    is_system: bool


_PACKAGE_PATTERN = r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+"
_APP_LINE = re.compile(rf"^ ([*-]) (.+?)[ \t]+({_PACKAGE_PATTERN})[ \t]*$")
_CONTINUATION_LINE = re.compile(rf"^[ \t]+({_PACKAGE_PATTERN})[ \t]*$")
_LOG_PREFIXES = ("scrcpy ", "INFO:", "WARN:", "ERROR:", "[server]")


def discover_device_apps(
    mode: str,
    custom_path: str,
    serial: str,
    *,
    timeout: float = DEFAULT_APP_DISCOVERY_TIMEOUT,
    root: Path | str | None = None,
) -> list[DeviceApp]:
    """Resolve the selected scrcpy mode and list apps for an explicit device."""
    try:
        resolution = resolve_scrcpy(mode, custom_path, root=root)
    except ScrcpyResolutionError as exc:
        raise AppDiscoveryError(str(exc)) from exc
    logger.info("Discovering applications using the configured scrcpy runtime")
    return list_device_apps(resolution.path, serial, timeout=timeout)


def list_device_apps(
    scrcpy_path: Path | str,
    serial: str,
    *,
    timeout: float = DEFAULT_APP_DISCOVERY_TIMEOUT,
) -> list[DeviceApp]:
    """Run scrcpy without a console and parse its application list."""
    normalized_serial = serial.strip()
    if not normalized_serial:
        raise AppDiscoveryError("Select a connected Android device before listing apps.")
    if timeout <= 0:
        raise AppDiscoveryError("The app discovery timeout must be greater than zero.")

    executable = Path(scrcpy_path)
    command = [str(executable), "--serial", normalized_serial, "--list-apps"]
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.warning("scrcpy app discovery timed out after %g seconds", timeout)
        raise AppDiscoveryError(
            f"App discovery timed out after {timeout:g} seconds for device "
            f"{normalized_serial}. Reconnect the device and try Refresh apps again."
        ) from exc
    except OSError as exc:
        logger.warning("Could not start scrcpy app discovery: %s", exc)
        raise AppDiscoveryError(f"Could not run scrcpy to list applications: {exc}") from exc

    elapsed = time.monotonic() - started
    logger.info(
        "scrcpy app discovery finished with exit code %d in %.2f seconds",
        completed.returncode,
        elapsed,
    )
    if completed.stderr.strip():
        logger.debug(
            "scrcpy app discovery returned %d diagnostic characters",
            len(completed.stderr.strip()),
        )
    if completed.returncode != 0:
        raise AppDiscoveryError(
            _failure_message(normalized_serial, completed.stdout, completed.stderr)
        )

    try:
        apps = parse_scrcpy_app_list(completed.stdout)
    except AppListParseError as exc:
        logger.warning("Could not parse scrcpy app list: %s", exc)
        raise AppDiscoveryError(
            "The selected scrcpy executable returned an unsupported application list "
            f"format: {exc}. Use bundled scrcpy 4.1 or a compatible newer custom version."
        ) from exc
    logger.info("Discovered %d launchable applications", len(apps))
    return apps


def _failure_detail(stdout: str, stderr: str) -> str:
    """Return useful diagnostics without copying a partial app inventory."""
    if stderr.strip():
        return stderr.strip()[:2000]
    diagnostic_lines = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped or line.startswith((" * ", " - ")):
            continue
        if stripped.startswith(("INFO:", "WARN:", "ERROR:", "[server]", "scrcpy ")):
            diagnostic_lines.append(stripped)
    if diagnostic_lines:
        return "\n".join(diagnostic_lines[-10:])[:2000]
    return "scrcpy exited without an error message."


def _failure_message(serial: str, stdout: str, stderr: str) -> str:
    """Turn common scrcpy/ADB failures into actionable, inventory-safe messages."""
    detail = _failure_detail(stdout, stderr)
    normalized = detail.casefold()
    unsupported_markers = (
        "unknown option",
        "unrecognized option",
        "unrecognised option",
        "invalid option",
        "option --list-apps not found",
    )
    if "list-apps" in normalized and any(marker in normalized for marker in unsupported_markers):
        return (
            "The selected scrcpy executable does not support --list-apps. "
            "Use bundled scrcpy 4.1 or a compatible newer custom version."
        )
    if "unauthorized" in normalized:
        return (
            f"Device {serial} is unauthorized. Unlock the device, accept its USB debugging "
            "prompt, then refresh devices and try again."
        )
    if "offline" in normalized:
        return (
            f"Device {serial} is offline. Reconnect it, refresh devices, and try again."
        )
    if any(
        marker in normalized
        for marker in ("device not found", "no device", "not found", "could not find")
    ):
        return (
            f"Device {serial} is no longer available. Reconnect it, refresh devices, "
            "and try again."
        )
    return f"scrcpy could not list applications for device {serial}:\n\n{detail}"


def parse_scrcpy_app_list(output: str) -> list[DeviceApp]:
    """Return launchable apps from captured scrcpy 4.1 stdout.

    The parser intentionally requires the ``List of apps:`` header so ordinary
    scrcpy logs or a future incompatible format cannot silently become an empty
    app list. Exact duplicate package names retain their first record.
    """
    header_seen = False
    pending: tuple[bool, str] | None = None
    apps: list[DeviceApp] = []
    packages: set[str] = set()

    def append_app(name: str, package_name: str, is_system: bool) -> None:
        normalized_name = name.strip()
        if not normalized_name:
            raise AppListParseError("scrcpy app list contains an empty app name")
        if package_name not in packages:
            apps.append(DeviceApp(normalized_name, package_name, is_system))
            packages.add(package_name)

    for line_number, raw_line in enumerate(output.splitlines(), start=1):
        line = raw_line.rstrip("\r")
        if not header_seen:
            if line.endswith("List of apps:"):
                header_seen = True
            continue

        if pending is not None:
            continuation = _CONTINUATION_LINE.fullmatch(line)
            if continuation is None:
                raise AppListParseError(
                    f"Expected a wrapped package name on line {line_number}"
                )
            is_system, name = pending
            append_app(name, continuation.group(1), is_system)
            pending = None
            continue

        if not line.strip():
            continue

        app_match = _APP_LINE.fullmatch(line)
        if app_match is not None:
            append_app(
                app_match.group(2),
                app_match.group(3),
                app_match.group(1) == "*",
            )
            continue

        if line.startswith((" * ", " - ")):
            name = line[3:].strip()
            if not name:
                raise AppListParseError(
                    f"scrcpy app list contains an empty app name on line {line_number}"
                )
            pending = (line[1] == "*", name)
            continue

        if line.startswith(_LOG_PREFIXES):
            continue

        raise AppListParseError(
            f"Unsupported scrcpy app-list output on line {line_number}: {line.strip()}"
        )

    if not header_seen:
        raise AppListParseError("scrcpy output does not contain a 'List of apps:' header")
    if pending is not None:
        raise AppListParseError("scrcpy app list ended before a wrapped package name")
    return apps
