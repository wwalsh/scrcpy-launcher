# SPDX-License-Identifier: GPL-3.0-only

"""Read-only configuration inspection and explicit startup recovery operations."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .config import Config, ConfigError, backup_path_for, load_config
from .safe_io import atomic_copy

logger = logging.getLogger(__name__)


class ConfigRecoveryError(Exception):
    pass


class BackupInvalidError(ConfigRecoveryError):
    pass


class BackupRestoreError(ConfigRecoveryError):
    pass


@dataclass(frozen=True)
class RecoveryInspection:
    config_path: Path
    primary_error: ConfigError | None
    backup_path: Path
    backup_error: ConfigError | None

    @property
    def primary_valid(self) -> bool:
        return self.primary_error is None

    @property
    def backup_valid(self) -> bool:
        return self.backup_error is None


def inspect_recovery(config_path: Path | str) -> RecoveryInspection:
    """Inspect primary and backup files without changing either one."""
    path = Path(config_path).resolve()
    backup = backup_path_for(path)
    primary_error = _load_error(path)
    backup_error = _load_error(backup)
    return RecoveryInspection(path, primary_error, backup, backup_error)


def _load_error(path: Path) -> ConfigError | None:
    try:
        load_config(path)
    except ConfigError as exc:
        return exc
    return None


def restore_backup(
    inspection: RecoveryInspection,
    *,
    now: Callable[[], datetime] = datetime.now,
) -> Config:
    """Validate and atomically restore a backup, archiving the invalid primary."""
    if not inspection.backup_valid:
        raise BackupInvalidError(f"Backup is not valid: {inspection.backup_error}")

    primary = inspection.config_path
    backup = inspection.backup_path
    archived_path: Path | None = None
    try:
        if primary.exists():
            archived_path = _unique_archive_path(primary, now())
            primary.replace(archived_path)
        def validate_staged(path: Path) -> None:
            try:
                load_config(path)
            except ConfigError as exc:
                raise BackupInvalidError(f"Backup is no longer valid: {exc}") from exc

        atomic_copy(backup, primary, validate=validate_staged)
        restored = load_config(primary)
    except BackupInvalidError:
        if archived_path is not None and archived_path.exists() and not primary.exists():
            try:
                archived_path.replace(primary)
            except OSError:
                logger.exception("Could not roll back invalid configuration restoration")
        raise
    except (OSError, ConfigError) as exc:
        if archived_path is not None and archived_path.exists() and not primary.exists():
            try:
                archived_path.replace(primary)
            except OSError:
                logger.exception("Could not roll back failed configuration restoration")
        raise BackupRestoreError(f"Could not restore {backup}: {exc}") from exc
    if archived_path is not None:
        logger.warning("Archived invalid configuration as %s", archived_path)
    logger.info("Restored configuration from %s", backup)
    return restored


def _unique_archive_path(primary: Path, timestamp: datetime) -> Path:
    stamp = timestamp.strftime("%Y%m%d-%H%M%S")
    candidate = primary.parent / f"{primary.name}.corrupt-{stamp}"
    suffix = 2
    while candidate.exists():
        candidate = primary.parent / f"{primary.name}.corrupt-{stamp}-{suffix}"
        suffix += 1
    return candidate


def open_config_folder(config_path: Path | str) -> None:
    """Create and open the configuration folder after an explicit user choice."""
    folder = Path(config_path).resolve().parent
    try:
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)  # type: ignore[attr-defined]
    except OSError as exc:
        raise ConfigRecoveryError(f"Could not open configuration folder {folder}: {exc}") from exc
