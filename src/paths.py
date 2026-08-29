# SPDX-License-Identifier: GPL-3.0-only

"""Resolve application paths consistently in source and packaged modes."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path


PORTABLE_MARKER = "portable.marker"
PORTABLE_DEFAULT_CONFIG = "default-config.json"
PORTABLEAPPS_DATA_ENV = "SCRCPY_LAUNCHER_PORTABLEAPPS_DATA_DIR"
PORTABLEAPPS_DEFAULT_DATA_DIR = "DefaultData"


class PortableConfigError(RuntimeError):
    """A portable first-run configuration could not be created."""


def portableapps_data_dir(*, frozen: bool | None = None) -> Path | None:
    """Return the PortableApps.com Data directory supplied by its launcher."""
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if not is_frozen:
        return None
    configured = os.environ.get(PORTABLEAPPS_DATA_ENV, "").strip()
    return Path(configured).resolve() if configured else None


def portable_root(
    *,
    frozen: bool | None = None,
    executable: Path | str | None = None,
) -> Path | None:
    """Return the application directory only for a marked portable package."""
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if not is_frozen:
        return None
    executable_path = Path(executable) if executable is not None else Path(sys.executable)
    root = executable_path.resolve().parent
    return root if (root / PORTABLE_MARKER).is_file() else None


def resolve_config_path(
    explicit_path: Path | str | None = None,
    *,
    frozen: bool | None = None,
    executable: Path | str | None = None,
) -> Path:
    """Resolve an explicit config path or the mode-appropriate default path."""
    if explicit_path is not None:
        return Path(explicit_path).resolve()

    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if not is_frozen:
        return Path("config.json").resolve()

    portableapps_data = portableapps_data_dir(frozen=True)
    if portableapps_data is not None:
        return portableapps_data / "config.json"

    portable = portable_root(frozen=True, executable=executable)
    if portable is not None:
        return portable / "config.json"

    app_data = os.environ.get("APPDATA")
    base = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
    return (base / "scrcpy-launcher" / "config.json").resolve()


def seed_portable_config(
    config_path: Path,
    *,
    frozen: bool | None = None,
    executable: Path | str | None = None,
) -> bool:
    """Atomically seed a missing portable config without replacing user data."""
    portableapps_data = portableapps_data_dir(frozen=frozen)
    if portableapps_data is not None:
        if config_path.resolve() != (portableapps_data / "config.json").resolve():
            return False
        executable_path = Path(executable) if executable is not None else Path(sys.executable)
        default_path = (
            executable_path.resolve().parent.parent
            / PORTABLEAPPS_DEFAULT_DATA_DIR
            / "config.json"
        )
        destination_dir = portableapps_data
    else:
        root = portable_root(frozen=frozen, executable=executable)
        if root is None or config_path.resolve() != (root / "config.json").resolve():
            return False
        default_path = root / PORTABLE_DEFAULT_CONFIG
        destination_dir = root

    if config_path.exists():
        return False
    if not default_path.is_file():
        raise PortableConfigError(f"Portable default configuration is missing: {default_path}")

    temporary_path: Path | None = None
    try:
        destination_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=".config.", suffix=".tmp", dir=destination_dir, delete=False
        ) as temporary, default_path.open("rb") as source:
            temporary_path = Path(temporary.name)
            shutil.copyfileobj(source, temporary)
        if config_path.exists():
            temporary_path.unlink(missing_ok=True)
            return False
        temporary_path.replace(config_path)
        temporary_path = None
        return True
    except OSError as exc:
        raise PortableConfigError(
            f"Could not create portable configuration at {config_path}: {exc}"
        ) from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
