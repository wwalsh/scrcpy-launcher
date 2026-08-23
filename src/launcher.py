# SPDX-License-Identifier: GPL-3.0-only

"""Launch and monitor scrcpy sessions without showing a console window."""

from __future__ import annotations

import logging
import subprocess
import threading
from collections.abc import Callable, Sequence

logger = logging.getLogger(__name__)


class SessionLaunchError(Exception):
    """A scrcpy process could not start or exited with an error."""


ErrorCallback = Callable[[SessionLaunchError], None]


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
        threading.Thread(
            target=self._monitor,
            args=(process, on_error),
            daemon=True,
        ).start()
        return process

    def _monitor(self, process: subprocess.Popen[str], on_error: ErrorCallback | None) -> None:
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
