# SPDX-License-Identifier: GPL-3.0-only

"""Discover Android devices through the adb bundled with scrcpy."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class DeviceDiscoveryError(Exception):
    """Raised when ADB device discovery cannot complete."""
    pass


@dataclass(frozen=True)
class Device:
    """A connected Android device identified by its ADB serial and state."""
    serial: str
    state: str
    model: str = ""
    product: str = ""
    transport_id: str = ""

    @property
    def label(self) -> str:
        """Return the serial and connection state shown in device selectors."""
        raw_name = (self.model or self.product or "Android device").replace("_", " ")
        name = " ".join(raw_name.split())
        return f"{name} — {self.serial}"


def find_adb(scrcpy_path: str, *, allow_path_fallback: bool = True) -> Path:
    """Find adb beside scrcpy first, then on PATH."""
    bundled = Path(scrcpy_path).expanduser().parent / "adb.exe"
    if bundled.is_file():
        return bundled
    if allow_path_fallback:
        discovered = shutil.which("adb.exe") or shutil.which("adb")
        if discovered:
            return Path(discovered)
    else:
        raise DeviceDiscoveryError(f"Bundled adb.exe was not found beside scrcpy.exe: {bundled}")
    raise DeviceDiscoveryError("adb.exe was not found beside scrcpy.exe or on PATH")


def detect_devices(
    scrcpy_path: str,
    timeout: float = 5.0,
    *,
    allow_path_fallback: bool = True,
) -> list[Device]:
    """Return devices reported by ``adb devices -l``."""
    adb_path = find_adb(scrcpy_path, allow_path_fallback=allow_path_fallback)
    try:
        completed = subprocess.run(
            [str(adb_path), "devices", "-l"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise DeviceDiscoveryError(f"Device detection timed out after {timeout:g} seconds") from exc
    except OSError as exc:
        raise DeviceDiscoveryError(f"Could not run adb: {exc}") from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown adb error"
        raise DeviceDiscoveryError(f"adb device detection failed: {detail}")
    return parse_adb_devices(completed.stdout)


def parse_adb_devices(output: str) -> list[Device]:
    """Parse the output from ``adb devices -l``."""
    devices: list[Device] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("List of devices attached") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[:2]
        metadata: dict[str, str] = {}
        for field in parts[2:]:
            key, separator, value = field.partition(":")
            if separator:
                metadata[key] = value
        devices.append(
            Device(
                serial=serial,
                state=state,
                model=metadata.get("model", ""),
                product=metadata.get("product", ""),
                transport_id=metadata.get("transport_id", ""),
            )
        )
    return devices
