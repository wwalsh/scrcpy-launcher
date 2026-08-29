# SPDX-License-Identifier: GPL-3.0-only

"""Launch and monitor scrcpy sessions without showing a console window."""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from collections.abc import Callable, Sequence

from .process import hidden_process_kwargs, run_hidden

logger = logging.getLogger(__name__)


class SessionLaunchError(Exception):
    """A scrcpy process could not start or exited with an error."""


ErrorCallback = Callable[[SessionLaunchError], None]

STARTUP_WINDOW_TIMEOUT_SECONDS = 10.0
STARTUP_POLL_INTERVAL_SECONDS = 0.1
SESSION_STOP_TIMEOUT_SECONDS = 3.0
ADB_STOP_TIMEOUT_SECONDS = 5.0


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
    """Share the startup boundary between the monitor and watcher threads.

    The watcher sets ``suppress_errors`` after a visible scrcpy window is
    found or the bounded startup interval expires. The monitor then treats
    later nonzero exits as expected session termination rather than startup
    failures that require a dialog.
    """

    def __init__(self) -> None:
        self.suppress_errors = threading.Event()


class _ProcessManager:
    """Retain and asynchronously monitor launcher-owned scrcpy processes.

    The manager deliberately tracks only processes started through ``launch``;
    shutdown actions must not terminate unrelated scrcpy instances.
    """

    def __init__(self) -> None:
        self._processes: list[subprocess.Popen[str]] = []
        self._lock = threading.Lock()

    def launch(
        self,
        scrcpy_path: str,
        args: Sequence[str],
        on_error: ErrorCallback | None = None,
    ) -> subprocess.Popen[str]:
        """Start scrcpy and attach independent startup and exit monitors.

        Two daemon threads are intentional: the exit monitor may block in
        ``communicate()`` while the startup watcher continues checking for the
        window that marks the end of dialog-worthy startup failures.
        """
        command = [scrcpy_path, *args]
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                **hidden_process_kwargs(),
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

    def active_count(self) -> int:
        """Return the number of scrcpy processes launched by this manager."""
        with self._lock:
            return len(self._processes)

    def stop_all(self) -> int:
        """Stop all scrcpy processes launched by this manager."""
        with self._lock:
            processes = list(self._processes)

        stopped = 0
        for process in processes:
            if process.poll() is not None:
                continue
            try:
                process.terminate()
                process.wait(timeout=SESSION_STOP_TIMEOUT_SECONDS)
                stopped += 1
            except subprocess.TimeoutExpired:
                logger.warning("scrcpy process %s did not stop gracefully; killing it", process.pid)
                try:
                    process.kill()
                    process.wait(timeout=SESSION_STOP_TIMEOUT_SECONDS)
                    stopped += 1
                except (OSError, subprocess.TimeoutExpired):
                    logger.exception("Could not kill scrcpy process %s", process.pid)
            except OSError:
                logger.exception("Could not stop scrcpy process %s", process.pid)

        return stopped

    def _watch_startup(
        self,
        process: subprocess.Popen[str],
        startup_state: _StartupState,
    ) -> None:
        """Watch for the startup window and close the error-reporting period."""
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
        """Collect process diagnostics, remove the process, and report failures.

        Failures are sent to ``on_error`` only while startup is unresolved.
        Once startup completes, a nonzero exit is logged as an expected
        disconnection or session shutdown.
        """
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


def active_session_count() -> int:
    """Return the number of launcher-managed scrcpy sessions still running."""
    return _manager.active_count()


def stop_all_sessions() -> int:
    """Stop all launcher-managed scrcpy sessions."""
    return _manager.stop_all()


def stop_adb_server(adb_path: str) -> bool:
    """Stop the ADB server associated with the selected scrcpy installation.

    ADB's server is shared system-wide, so callers must obtain explicit user
    confirmation before invoking this operation.
    """
    try:
        completed = run_hidden(
            [adb_path, "kill-server"],
            timeout=ADB_STOP_TIMEOUT_SECONDS,
            capture_output=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, PermissionError, OSError, subprocess.TimeoutExpired):
        logger.exception("Could not stop ADB server using %s", adb_path)
        return False
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip()
        logger.warning("ADB server shutdown failed with code %s: %s", completed.returncode, detail)
        return False
    logger.info("Stopped ADB server using %s", adb_path)
    return True


def launch_session(
    scrcpy_path: str,
    args: Sequence[str],
    on_error: ErrorCallback | None = None,
) -> subprocess.Popen[str]:
    """Launch and monitor one scrcpy session without opening a console window.

    Args:
        scrcpy_path: Executable to run.
        args: Argument vector passed to scrcpy without shell interpretation.
        on_error: Optional callback for failures detected during startup.

    Returns:
        The child process object tracked by the launcher.

    Raises:
        SessionLaunchError: If Windows cannot start the executable.
    """
    return _manager.launch(scrcpy_path, args, on_error)
