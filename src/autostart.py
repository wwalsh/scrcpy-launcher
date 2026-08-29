# SPDX-License-Identifier: GPL-3.0-only

"""Per-user Windows autostart registration for the installed tray application."""

from __future__ import annotations

import logging
import sys
import winreg
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .paths import portableapps_data_dir
from .runtime import is_frozen

logger = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "scrcpy-launcher"


class AutostartError(Exception):
    """Base error for Windows autostart registration failures."""


class AutostartUnavailableError(AutostartError):
    """Raised when the current runtime cannot manage Windows autostart."""


class AutostartStatus(Enum):
    """States reported for the current-user launcher registration."""
    DISABLED = "disabled"
    ENABLED = "enabled"
    STALE = "stale"


@dataclass(frozen=True)
class AutostartState:
    """Snapshot of the expected and registered autostart commands."""
    status: AutostartStatus
    expected_command: str
    registered_command: str | None


class AutostartManager:
    """Read and update the current user's launcher registration."""

    def __init__(self, executable: Path | str, config_path: Path | str) -> None:
        self._executable = Path(executable).resolve()
        self._config_path = Path(config_path).resolve()

    @property
    def expected_command(self) -> str:
        """Return the command this installation should register at sign-in."""
        return f'"{self._executable}" --config "{self._config_path}"'

    def state(self) -> AutostartState:
        """Inspect the current-user Run entry without modifying the registry."""
        registered = _read_registration()
        if registered is None:
            status = AutostartStatus.DISABLED
        elif registered.casefold() == self.expected_command.casefold():
            status = AutostartStatus.ENABLED
        else:
            status = AutostartStatus.STALE
        return AutostartState(status, self.expected_command, registered)

    def enable(self) -> None:
        """Register this installation to start at the user's Windows sign-in."""
        _write_registration(self.expected_command)
        logger.info("Enabled Windows autostart")

    def disable(self) -> None:
        """Remove only this launcher's current-user autostart registration."""
        _delete_registration()
        logger.info("Disabled Windows autostart")

    def apply(self, enabled: bool) -> None:
        """Enable or disable autostart according to the requested setting."""
        if enabled:
            self.enable()
        else:
            self.disable()


def create_autostart_manager(config_path: Path | str) -> AutostartManager:
    """Create an installed-app manager; source-mode registration is intentionally unsupported."""
    if portableapps_data_dir() is not None:
        raise AutostartUnavailableError(
            "Windows autostart is unavailable in the PortableApps.com edition"
        )
    if not is_frozen():
        raise AutostartUnavailableError(
            "Windows autostart is available only in the installed application"
        )
    return AutostartManager(sys.executable, config_path)


def _read_registration() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, value_type = winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise AutostartError(f"Could not read Windows autostart settings: {exc}") from exc
    if value_type not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) or not isinstance(value, str):
        return ""
    return value


def _write_registration(command: str) -> None:
    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
    except OSError as exc:
        raise AutostartError(f"Could not enable Windows autostart: {exc}") from exc


def _delete_registration() -> None:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise AutostartError(f"Could not disable Windows autostart: {exc}") from exc
