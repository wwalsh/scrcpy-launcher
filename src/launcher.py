# SPDX-License-Identifier: GPL-3.0-only

"""Launch and monitor scrcpy sessions without showing a console window."""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from collections.abc import Callable, Sequence

logger = logging.getLogger(__name__)


class SessionLaunchError(Exception):
    """A scrcpy process could not start or exited with an error."""


ErrorCallback = Callable[[SessionLaunchError], None]

STARTUP_WINDOW_TIMEOUT_SECONDS = 10.0
STARTUP_POLL_INTERVAL_SECONDS = 0.1


def _process_has_visible_window(process_id: int) -> bool:
    """Return whether a process owns a visible top-level Windows window."""
    import win32gui
    import win32con
    import win32process

    found = False

    def inspect_window(hwnd: int, _extra: object) -> None:
        nonlocal found
        if found or not win32gui.IsWindowVisible(hwnd):
            return
        if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
            return
        _thread_id, owner_process_id = win32process.GetWindowThreadProcessId(hwnd)
        if owner_process_id == process_id:
            found = True

    win32gui.EnumWindows(inspect_window, None)
    return found


class _StartupState:
    """Share startup completion state between the monitor threads."""

    def __init__(self) -> None:
        self.suppress_errors = threading.Event()


class _ProcessManager:
    """Retain and asynchronously monitor launched scrcpy processes."""

    def __init__(self) -> None:
        self._processes: list[subprocess.Popen[str]] = []
        self._lock = threading.Lock()

    def launch(
        self,
        scrcpy_path: str,
        args: Sequence[str],
        on_error: ErrorCallback | None = None,
    ) -> subprocess.Popen[str]:
        command = [scrcpy_path, *args]
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except FileNotFoundError as exc:
            raise SessionLaunchError(f"scrcpy executable not found: {scrcpy_path}") from exc
        except PermissionError as exc:
            raise SessionLaunchError(f"Permission denied when starting: {scrcpy_path}") from exc
        except OSError as exc:
            raise SessionLaunchError(f"Windows could not start scrcpy: {exc}") from exc

        with self._lock:
            self._processes.append(process)
        startup_state = _StartupState()
        threading.Thread(
            target=self._monitor,
            args=(process, on_error, startup_state),
            daemon=True,
        ).start()
        threading.Thread(
            target=self._watch_startup,
            args=(process, startup_state),
            daemon=True,
        ).start()
        return process

    def _watch_startup(
        self,
        process: subprocess.Popen[str],
        startup_state: _StartupState,
    ) -> None:
        deadline = time.monotonic() + STARTUP_WINDOW_TIMEOUT_SECONDS
        while process.poll() is None:
            try:
                if _process_has_visible_window(process.pid):
                    startup_state.suppress_errors.set()
                    return
            except (ImportError, OSError):
                logger.exception("Could not inspect scrcpy windows")
                return
            if time.monotonic() >= deadline:
                logger.debug("scrcpy startup window expired for process %s", process.pid)
                startup_state.suppress_errors.set()
                return
            time.sleep(STARTUP_POLL_INTERVAL_SECONDS)

    def _monitor(
        self,
        process: subprocess.Popen[str],
        on_error: ErrorCallback | None,
        startup_state: _StartupState | None = None,
    ) -> None:
        try:
            _stdout, stderr = process.communicate()
            returncode = process.returncode
        except OSError as exc:
            stderr = f"Could not monitor scrcpy: {exc}"
            returncode = process.poll()
        finally:
            with self._lock:
                try:
                    self._processes.remove(process)
                except ValueError:
                    pass

        if returncode == 0:
            return
        detail = (stderr or "").strip()
        if len(detail) > 2000:
            detail = f"{detail[:2000]}\n…"
        code = returncode if returncode is not None else "unknown"
        message = f"scrcpy exited with code {code}."
        if detail:
            message = f"{message}\n\n{detail}"
        error = SessionLaunchError(message)
        logger.error("scrcpy exited with code %s", code)
        if startup_state is not None and startup_state.suppress_errors.is_set():
            logger.info("Suppressing post-startup scrcpy error for process %s", process.pid)
            return
        if on_error is not None:
            try:
                on_error(error)
            except Exception:
                logger.exception("scrcpy error callback failed")


_manager = _ProcessManager()


def launch_session(
    scrcpy_path: str,
    args: Sequence[str],
    on_error: ErrorCallback | None = None,
) -> subprocess.Popen[str]:
    return _manager.launch(scrcpy_path, args, on_error)
