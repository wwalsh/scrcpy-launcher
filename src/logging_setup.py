# SPDX-License-Identifier: GPL-3.0-only

"""Persistent logging setup for tray and settings processes."""

from __future__ import annotations

import logging
import os
import re
import sys
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .paths import portableapps_data_dir


_USER_PROFILE_PATTERN = re.compile(
    r"(?i)\b[A-Z]:[\\/]Users[\\/][^\\/\s\"']+"
)
_SERIAL_OPTION_PATTERN = re.compile(
    r"(?i)(--serial(?:=|\s+))(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_DEVICE_SERIAL_PATTERN = re.compile(
    r"(?i)(\bdevice\s+)([A-Za-z0-9][A-Za-z0-9._:-]{2,})(?="
    r"\s+(?:is|was|with|after|for|failed|timed|returned|became|appears)\b)"
)


def redact_log_message(message: str) -> str:
    """Remove common local identifiers from persistent diagnostic text."""
    redacted = _USER_PROFILE_PATTERN.sub("%USERPROFILE%", message)
    redacted = _SERIAL_OPTION_PATTERN.sub(r"\1<redacted>", redacted)
    return _DEVICE_SERIAL_PATTERN.sub(r"\1<redacted>", redacted)


class PrivacyFormatter(logging.Formatter):
    """Apply privacy redaction after formatting, including exception tracebacks."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a record after applying the project's privacy redaction."""
        return redact_log_message(super().format(record))


def log_path_for(component: str) -> Path:
    """Return the preferred per-component log path."""
    portableapps_data = portableapps_data_dir()
    if portableapps_data is not None:
        return portableapps_data / "logs" / f"{component}.log"
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path(tempfile.gettempdir())
    return base / "scrcpy-launcher" / f"{component}.log"


def setup_logging(component: str) -> Path:
    """Configure console and rotating file logs without making startup depend on logging."""
    log_path = log_path_for(component)
    handlers: list[logging.Handler] = []
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_path,
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8",
            )
        )
    except OSError:
        if portableapps_data_dir() is None:
            log_path = Path(tempfile.gettempdir()) / f"scrcpy-launcher-{component}.log"
            try:
                handlers.append(
                    RotatingFileHandler(
                        log_path,
                        maxBytes=1_000_000,
                        backupCount=3,
                        encoding="utf-8",
                    )
                )
            except OSError:
                pass

    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    formatter = PrivacyFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    for handler in handlers:
        handler.setFormatter(formatter)
    logging.basicConfig(
        level=logging.INFO,
        handlers=handlers or None,
        force=True,
    )
    return log_path
