# SPDX-License-Identifier: GPL-3.0-only

"""Import and export portable scrcpy-launcher session collections."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .config import Config, ConfigError, Session
from .safe_io import InputTooLargeError, atomic_write_bytes, read_limited_utf8

SESSION_BACKUP_FORMAT = "scrcpy-launcher-sessions"
SESSION_BACKUP_VERSION = 1


class SessionTransferError(Exception):
    pass


class SessionBackupReadError(SessionTransferError):
    pass


class SessionBackupValidationError(SessionTransferError):
    pass


class UnsupportedSessionBackupVersionError(SessionBackupValidationError):
    pass


class SessionBackupWriteError(SessionTransferError):
    pass


def load_session_backup(path: Path | str) -> tuple[Session, ...]:
    """Load and fully validate a session backup without changing configuration."""
    backup_path = Path(path)
    try:
        data = json.loads(read_limited_utf8(backup_path))
    except FileNotFoundError as exc:
        raise SessionBackupReadError(f"Session backup not found: {backup_path}") from exc
    except json.JSONDecodeError as exc:
        raise SessionBackupValidationError(
            f"Invalid JSON in {backup_path.name} "
            f"(line {exc.lineno}, column {exc.colno}): {exc.msg}"
        ) from exc
    except UnicodeDecodeError as exc:
        raise SessionBackupValidationError(
            f"Invalid UTF-8 in {backup_path.name}: {exc}"
        ) from exc
    except InputTooLargeError as exc:
        raise SessionBackupReadError(f"Session backup is too large: {exc}") from exc
    except OSError as exc:
        raise SessionBackupReadError(f"Could not read {backup_path}: {exc}") from exc

    return parse_session_backup(data)


def parse_session_backup(data: Any) -> tuple[Session, ...]:
    """Validate decoded backup data and return normalized sessions."""
    if not isinstance(data, dict):
        raise SessionBackupValidationError("Session backup must be a JSON object")
    if data.get("format") != SESSION_BACKUP_FORMAT:
        raise SessionBackupValidationError(
            f"Not a {SESSION_BACKUP_FORMAT} backup"
        )

    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise SessionBackupValidationError("'version' must be a positive integer")
    if version > SESSION_BACKUP_VERSION:
        raise UnsupportedSessionBackupVersionError(
            f"Session backup version {version} is newer than this launcher supports "
            f"(version {SESSION_BACKUP_VERSION})"
        )
    if version != SESSION_BACKUP_VERSION:
        raise UnsupportedSessionBackupVersionError(
            f"Session backup version {version} is not supported"
        )

    try:
        return Config.validate_session_list(data.get("sessions"))
    except ConfigError as exc:
        raise SessionBackupValidationError(f"Invalid session backup: {exc}") from exc


def export_session_backup(path: Path | str, sessions: Sequence[Session]) -> None:
    """Validate and atomically write a portable session backup."""
    try:
        validated = Config.validate_session_objects(sessions)
    except ConfigError as exc:
        raise SessionBackupValidationError(f"Cannot export invalid sessions: {exc}") from exc

    destination = Path(path)
    data = {
        "format": SESSION_BACKUP_FORMAT,
        "version": SESSION_BACKUP_VERSION,
        "sessions": [
            {"name": session.name, "args": list(session.args)}
            for session in validated
        ],
    }
    try:
        encoded = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        atomic_write_bytes(destination, encoded, validate=load_session_backup)
    except SessionTransferError:
        raise
    except OSError as exc:
        raise SessionBackupWriteError(f"Could not write {destination}: {exc}") from exc
