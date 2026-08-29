# SPDX-License-Identifier: GPL-3.0-only

"""Bounded reads and collision-resistant atomic file replacement."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

MAX_JSON_FILE_BYTES = 5 * 1024 * 1024


class InputTooLargeError(ValueError):
    """Raised when a bounded input exceeds the allowed byte limit."""
    pass


def read_limited_utf8(path: Path, *, max_bytes: int = MAX_JSON_FILE_BYTES) -> str:
    """Read at most ``max_bytes`` from a UTF-8 file, detecting concurrent growth."""
    if path.stat().st_size > max_bytes:
        raise InputTooLargeError(
            f"{path.name} is larger than the {max_bytes // (1024 * 1024)} MiB limit"
        )
    with path.open("rb") as stream:
        data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise InputTooLargeError(
            f"{path.name} is larger than the {max_bytes // (1024 * 1024)} MiB limit"
        )
    return data.decode("utf-8")


def _temporary_path(destination: Path) -> tuple[Path, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        delete=False,
    )
    return Path(temporary.name), temporary


def atomic_write_bytes(
    destination: Path,
    data: bytes,
    *,
    validate: Callable[[Path], object] | None = None,
) -> None:
    """Write bytes to a private adjacent file and atomically replace destination."""
    temporary_path, temporary = _temporary_path(destination)
    try:
        with temporary:
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
        if validate is not None:
            validate(temporary_path)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def atomic_copy(
    source: Path,
    destination: Path,
    *,
    validate: Callable[[Path], object] | None = None,
) -> None:
    """Copy a file through a private adjacent file and atomically replace destination."""
    temporary_path, temporary = _temporary_path(destination)
    try:
        with source.open("rb") as source_stream, temporary:
            shutil.copyfileobj(source_stream, temporary)
            temporary.flush()
            os.fsync(temporary.fileno())
        shutil.copystat(source, temporary_path)
        if validate is not None:
            validate(temporary_path)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)
