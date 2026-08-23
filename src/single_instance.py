# SPDX-License-Identifier: GPL-3.0-only

"""Windows named-mutex ownership for the tray application."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import logging

logger = logging.getLogger(__name__)

MUTEX_NAME = r"Local\scrcpy-launcher-tray"
ERROR_ALREADY_EXISTS = 183

_kernel32 = ctypes.windll.kernel32
_kernel32.CreateMutexW.argtypes = [w.LPVOID, w.BOOL, w.LPCWSTR]
_kernel32.CreateMutexW.restype = w.HANDLE
_kernel32.CloseHandle.argtypes = [w.HANDLE]
_kernel32.CloseHandle.restype = w.BOOL


class SingleInstanceError(Exception):
    """The application could not establish reliable single-instance ownership."""


class SingleInstance:
    """Own a named mutex for the lifetime of one tray process."""

    def __init__(self, name: str = MUTEX_NAME) -> None:
        self._name = name
        self._handle: int | None = None

    def acquire(self) -> bool:
        """Acquire ownership, returning False when another process already owns it."""
        if self._handle is not None:
            return True

        _kernel32.SetLastError(0)
        handle = _kernel32.CreateMutexW(None, False, self._name)
        error_code = _kernel32.GetLastError()
        if not handle:
            raise SingleInstanceError(
                f"Could not create the application mutex (Windows error {error_code})"
            )
        if error_code == ERROR_ALREADY_EXISTS:
            _kernel32.CloseHandle(handle)
            return False

        self._handle = handle
        return True

    def release(self) -> None:
        """Release this process's mutex handle. Repeated calls are safe."""
        if self._handle is None:
            return
        handle = self._handle
        self._handle = None
        if not _kernel32.CloseHandle(handle):
            logger.warning(
                "Could not close application mutex handle (Windows error %s)",
                _kernel32.GetLastError(),
            )
