# SPDX-License-Identifier: GPL-3.0-only

"""Load and cache scrcpy-launcher configuration from config.json."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .safe_io import (
    InputTooLargeError,
    atomic_copy,
    atomic_write_bytes,
    read_limited_utf8,
)

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 2
SCRCPY_MODE_BUNDLED = "bundled"
SCRCPY_MODE_CUSTOM = "custom"
SCRCPY_MODES = frozenset((SCRCPY_MODE_BUNDLED, SCRCPY_MODE_CUSTOM))
MAX_SESSIONS = 500
MAX_SESSION_NAME_CHARS = 200
MAX_ARGS_PER_SESSION = 256
MAX_ARG_CHARS = 4096
MAX_TOTAL_ARG_CHARS = 32768
MAX_SCRCPY_PATH_CHARS = 32767


@dataclass
class Session:
    """A single scrcpy session definition."""

    name: str
    args: list[str]


@dataclass(frozen=True)
class SessionMergeResult:
    """Summary of sessions added to a configuration by a merge."""

    imported_count: int
    renamed: tuple[tuple[str, str], ...]


class ConfigError(Exception):
    """Base error for configuration loading, validation, and persistence."""


class ConfigNotFoundError(ConfigError):
    """Raised when the requested configuration file does not exist."""


class ConfigJSONError(ConfigError):
    """Raised when configuration content is not valid JSON or UTF-8."""


class ConfigReadError(ConfigError):
    """Raised when the configuration cannot be read from disk."""


class ConfigValidationError(ConfigError):
    """Raised when configuration values violate the supported schema."""


class UnsupportedSchemaVersionError(ConfigError):
    """Raised when a configuration uses a newer unsupported schema version."""


class ConfigMigrationError(ConfigError):
    """Raised when a legacy configuration cannot be migrated safely."""


class Config:
    """Reads config.json and exposes session list plus scrcpy executable path."""

    _config_path: Path
    _scrcpy_mode: str
    _scrcpy_path: str
    _sessions: tuple[Session, ...]
    _source_schema_version: int

    def __init__(self, config_path: Path | str = "config.json") -> None:
        self._config_path = Path(config_path).resolve()
        self._load()

    def _load(self) -> None:
        data = self._read_data(self._config_path)
        data, self._source_schema_version = self._migrate_data(data)

        self._scrcpy_mode = self._validate_scrcpy_mode(data.get("scrcpy_mode"))
        self._scrcpy_path = self._validate_scrcpy_path(data.get("scrcpy_path"))

        self._sessions = self.validate_session_list(data.get("sessions", []))

    @staticmethod
    def _read_data(path: Path) -> dict[str, Any]:
        try:
            data = json.loads(read_limited_utf8(path))
        except FileNotFoundError as exc:
            raise ConfigNotFoundError(f"Configuration file not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigJSONError(
                f"Invalid JSON in {path.name} "
                f"(line {exc.lineno}, column {exc.colno}): {exc.msg}"
            ) from exc
        except UnicodeDecodeError as exc:
            raise ConfigJSONError(f"Invalid UTF-8 in {path.name}: {exc}") from exc
        except InputTooLargeError as exc:
            raise ConfigReadError(f"Configuration file is too large: {exc}") from exc
        except OSError as exc:
            raise ConfigReadError(f"Could not read {path}: {exc}") from exc

        if not isinstance(data, dict):
            raise ConfigValidationError("Configuration must be a JSON object")
        return data

    @classmethod
    def _migrate_data(cls, data: dict[str, Any]) -> tuple[dict[str, Any], int]:
        raw_version = data.get("schema_version", 0)
        if isinstance(raw_version, bool) or not isinstance(raw_version, int) or raw_version < 0:
            raise ConfigValidationError("'schema_version' must be a non-negative integer")
        if raw_version > CURRENT_SCHEMA_VERSION:
            raise UnsupportedSchemaVersionError(
                f"Configuration schema version {raw_version} is newer than this launcher "
                f"supports (version {CURRENT_SCHEMA_VERSION})"
            )

        migrated = dict(data)
        version = raw_version
        try:
            while version < CURRENT_SCHEMA_VERSION:
                migration = _MIGRATIONS.get(version)
                if migration is None:
                    raise ConfigMigrationError(
                        f"No configuration migration is available from schema version {version}"
                    )
                migrated = migration(migrated)
                version += 1
        except ConfigError:
            raise
        except Exception as exc:
            raise ConfigMigrationError(
                f"Could not migrate configuration from schema version {raw_version}: {exc}"
            ) from exc

        if raw_version != CURRENT_SCHEMA_VERSION:
            logger.info(
                "Migrated configuration in memory from schema version %s to %s",
                raw_version,
                CURRENT_SCHEMA_VERSION,
            )
        return migrated, raw_version

    @staticmethod
    def _validate_scrcpy_mode(value: Any) -> str:
        if not isinstance(value, str) or value not in SCRCPY_MODES:
            choices = ", ".join(sorted(SCRCPY_MODES))
            raise ConfigValidationError(f"'scrcpy_mode' must be one of: {choices}")
        return value

    @staticmethod
    def _validate_scrcpy_path(value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ConfigValidationError("'scrcpy_path' must be a non-empty string")
        normalized = value.strip()
        if len(normalized) > MAX_SCRCPY_PATH_CHARS:
            raise ConfigValidationError(
                f"'scrcpy_path' exceeds {MAX_SCRCPY_PATH_CHARS} characters"
            )
        return normalized

    @staticmethod
    def _validate_unique_names(sessions: list[Session]) -> None:
        seen: set[str] = set()
        for s in sessions:
            key = s.name.casefold()
            if key in seen:
                raise ConfigValidationError(f"Duplicate session name: '{s.name}'")
            seen.add(key)

    @staticmethod
    def _validate_session(session: Any, index: int) -> Session:
        if not isinstance(session, dict):
            raise ConfigValidationError(f"sessions[{index}] must be an object")

        name = session.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConfigValidationError(f"sessions[{index}].name must be a non-empty string")
        if "\n" in name or "\r" in name:
            raise ConfigValidationError(f"sessions[{index}].name must be a single line")
        normalized_name = name.strip()
        if len(normalized_name) > MAX_SESSION_NAME_CHARS:
            raise ConfigValidationError(
                f"sessions[{index}].name exceeds {MAX_SESSION_NAME_CHARS} characters"
            )

        args = session.get("args")
        if not isinstance(args, list):
            raise ConfigValidationError(f"sessions[{index}].args must be a list")
        if len(args) > MAX_ARGS_PER_SESSION:
            raise ConfigValidationError(
                f"sessions[{index}].args exceeds {MAX_ARGS_PER_SESSION} arguments"
            )

        normalized_args: list[str] = []
        total_arg_chars = 0
        for i, arg in enumerate(args):
            if not isinstance(arg, str):
                raise ConfigValidationError(f"sessions[{index}].args[{i}] must be a string")
            if not arg.strip():
                raise ConfigValidationError(f"sessions[{index}].args[{i}] cannot be empty")
            normalized_arg = arg.strip()
            if len(normalized_arg) > MAX_ARG_CHARS:
                raise ConfigValidationError(
                    f"sessions[{index}].args[{i}] exceeds {MAX_ARG_CHARS} characters"
                )
            normalized_args.append(normalized_arg)
            total_arg_chars += len(normalized_arg)
        if total_arg_chars > MAX_TOTAL_ARG_CHARS:
            raise ConfigValidationError(
                f"sessions[{index}].args exceeds {MAX_TOTAL_ARG_CHARS} total characters"
            )

        return Session(name=normalized_name, args=normalized_args)

    @classmethod
    def validate_session_list(cls, raw_sessions: Any) -> tuple[Session, ...]:
        """Validate raw session data and return normalized independent sessions."""
        if not isinstance(raw_sessions, list):
            raise ConfigValidationError("'sessions' must be a list")
        if len(raw_sessions) > MAX_SESSIONS:
            raise ConfigValidationError(f"'sessions' exceeds the limit of {MAX_SESSIONS}")
        sessions = tuple(
            cls._validate_session(session, index)
            for index, session in enumerate(raw_sessions)
        )
        cls._validate_unique_names(list(sessions))
        return sessions

    @property
    def scrcpy_mode(self) -> str:
        """Return the selected bundled or custom scrcpy mode."""
        return self._scrcpy_mode

    @property
    def scrcpy_path(self) -> str:
        """Return the configured custom scrcpy path."""
        return self._scrcpy_path

    @property
    def sessions(self) -> tuple[Session, ...]:
        """Return saved sessions in their tray-menu order."""
        return self._sessions

    @property
    def config_path(self) -> Path:
        """Return the resolved path of the loaded configuration file."""
        return self._config_path

    @property
    def source_schema_version(self) -> int:
        """Return the on-disk schema version loaded before in-memory migration."""
        return self._source_schema_version

    @property
    def needs_migration_save(self) -> bool:
        """Return whether loading found legacy data that should be rewritten."""
        return self._source_schema_version != CURRENT_SCHEMA_VERSION

    def set_scrcpy_mode(self, value: str) -> None:
        """Validate and update the scrcpy executable selection mode."""
        self._scrcpy_mode = self._validate_scrcpy_mode(value)

    def set_scrcpy_path(self, value: str) -> None:
        """Validate and update the scrcpy executable path."""
        self._scrcpy_path = self._validate_scrcpy_path(value)

    def save(self) -> None:
        """Persist the current configuration to config_path, preserving a .bak backup."""
        self._scrcpy_mode = self._validate_scrcpy_mode(self._scrcpy_mode)
        self._scrcpy_path = self._validate_scrcpy_path(self._scrcpy_path)
        self._sessions = self.validate_session_objects(self._sessions)

        bak_path = backup_path_for(self._config_path)
        if self._config_path.exists():
            try:
                Config(self._config_path)
            except ConfigError as exc:
                logger.warning(
                    "Not replacing %s because the current primary configuration is invalid: %s",
                    bak_path,
                    exc,
                )
            else:
                _atomic_copy(self._config_path, bak_path)

        # Warn on missing scrcpy_path but allow saving (user may have set it intentionally)
        if self._scrcpy_mode == SCRCPY_MODE_CUSTOM and not Path(self._scrcpy_path).exists():
            logger.warning(
                "scrcpy_path '%s' does not exist — sessions will fail to launch",
                self._scrcpy_path,
            )

        data: dict[str, Any] = {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "scrcpy_mode": self._scrcpy_mode,
            "scrcpy_path": self._scrcpy_path,
            "sessions": [
                {"name": s.name, "args": list(s.args)}
                for s in self._sessions
            ],
        }

        encoded = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        atomic_write_bytes(self._config_path, encoded, validate=Config)
        self._source_schema_version = CURRENT_SCHEMA_VERSION

    def add_session(self, name: str, args: list[str]) -> None:
        """Validate and append a new session."""
        raw = self._raw_session_dict(name, args)
        session = self._validate_session(raw, len(self._sessions))
        candidates = list(self._sessions) + [session]
        if len(candidates) > MAX_SESSIONS:
            raise ConfigValidationError(f"'sessions' exceeds the limit of {MAX_SESSIONS}")
        self._validate_unique_names(candidates)
        self._sessions = self._sessions + (session,)

    def remove_session(self, index: int) -> None:
        """Remove the session at the given index."""
        if not isinstance(index, int) or index < 0 or index >= len(self._sessions):
            raise ConfigError(f"session index {index} out of range")
        self._sessions = self._sessions[:index] + self._sessions[index + 1:]

    def duplicate_session(self, index: int) -> int:
        """Insert a uniquely named copy after a session and return its index."""
        if not isinstance(index, int) or index < 0 or index >= len(self._sessions):
            raise ConfigError(f"session index {index} out of range")

        source = self._sessions[index]
        existing_names = {session.name.casefold() for session in self._sessions}
        base_name = f"{source.name} copy"
        copy_name = base_name
        suffix = 2
        while copy_name.casefold() in existing_names:
            copy_name = f"{base_name} {suffix}"
            suffix += 1

        duplicate = self._validate_session(
            self._raw_session_dict(copy_name, list(source.args)),
            index + 1,
        )
        duplicate_index = index + 1
        if len(self._sessions) >= MAX_SESSIONS:
            raise ConfigValidationError(f"'sessions' exceeds the limit of {MAX_SESSIONS}")
        self._sessions = (
            self._sessions[:duplicate_index]
            + (duplicate,)
            + self._sessions[duplicate_index:]
        )
        return duplicate_index

    def move_session(self, index: int, new_index: int) -> int:
        """Move a session to an absolute index and return its new index."""
        session_count = len(self._sessions)
        if not isinstance(index, int) or index < 0 or index >= session_count:
            raise ConfigError(f"session index {index} out of range")
        if not isinstance(new_index, int) or new_index < 0 or new_index >= session_count:
            raise ConfigError(f"target session index {new_index} out of range")
        if index == new_index:
            return index

        sessions = list(self._sessions)
        session = sessions.pop(index)
        sessions.insert(new_index, session)
        self._sessions = tuple(sessions)
        return new_index

    def update_session(self, index: int, name: str, args: list[str]) -> None:
        """Replace the session at the given index with validated values."""
        if not isinstance(index, int) or index < 0 or index >= len(self._sessions):
            raise ConfigError(f"session index {index} out of range")
        raw = self._raw_session_dict(name, args)
        session = self._validate_session(raw, index)
        candidates = list(self._sessions)
        candidates[index] = session
        self._validate_unique_names(candidates)
        self._sessions = self._sessions[:index] + (session,) + self._sessions[index + 1:]

    def replace_sessions(self, sessions: Sequence[Session]) -> None:
        """Replace all sessions after validating the complete candidate collection."""
        self._sessions = self.validate_session_objects(sessions)

    def merge_sessions(self, sessions: Sequence[Session]) -> SessionMergeResult:
        """Append sessions, renaming conflicts predictably and atomically."""
        imported = self.validate_session_objects(sessions)
        if len(self._sessions) + len(imported) > MAX_SESSIONS:
            raise ConfigValidationError(f"'sessions' exceeds the limit of {MAX_SESSIONS}")
        existing_names = {session.name.casefold() for session in self._sessions}
        merged = list(self._sessions)
        renamed: list[tuple[str, str]] = []

        for session in imported:
            original_name = session.name
            candidate_name = original_name
            suffix = 2
            while candidate_name.casefold() in existing_names:
                candidate_name = f"{original_name} ({suffix})"
                suffix += 1
            if candidate_name != original_name:
                renamed.append((original_name, candidate_name))
            merged.append(Session(candidate_name, list(session.args)))
            existing_names.add(candidate_name.casefold())

        self._validate_unique_names(merged)
        self._sessions = tuple(merged)
        return SessionMergeResult(len(imported), tuple(renamed))

    @classmethod
    def validate_session_objects(cls, sessions: Sequence[Session]) -> tuple[Session, ...]:
        """Validate Session objects and return normalized independent copies."""
        if isinstance(sessions, (str, bytes)) or not isinstance(sessions, Sequence):
            raise ConfigValidationError("sessions must be a sequence of Session objects")
        if len(sessions) > MAX_SESSIONS:
            raise ConfigValidationError(f"'sessions' exceeds the limit of {MAX_SESSIONS}")
        raw_sessions: list[dict[str, Any]] = []
        for index, session in enumerate(sessions):
            if not isinstance(session, Session):
                raise ConfigValidationError(f"sessions[{index}] must be a Session")
            raw_sessions.append(cls._raw_session_dict(session.name, list(session.args)))
        return cls.validate_session_list(raw_sessions)

    @staticmethod
    def _raw_session_dict(name: str, args: list[str]) -> dict[str, Any]:
        return {"name": name, "args": args}


def load_config(config_path: Path | str = "config.json") -> Config:
    """Load and validate a configuration from disk.

    Raises:
        ConfigError: A typed subclass describing missing, invalid, or unreadable data.
    """
    return Config(config_path)


def backup_path_for(config_path: Path | str) -> Path:
    """Return the adjacent ``.bak`` path used for configuration recovery."""
    path = Path(config_path)
    return path.parent / f"{path.name}.bak"


def _atomic_copy(source: Path, destination: Path) -> None:
    atomic_copy(source, destination, validate=Config)


def _migrate_v0_to_v1(data: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(data)
    migrated["schema_version"] = 1
    return migrated


def _migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Preserve all existing installations as explicit custom selections."""
    migrated = dict(data)
    migrated["scrcpy_mode"] = SCRCPY_MODE_CUSTOM
    migrated["schema_version"] = 2
    return migrated


_MIGRATIONS = {0: _migrate_v0_to_v1, 1: _migrate_v1_to_v2}
