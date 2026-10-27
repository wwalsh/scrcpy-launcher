# SPDX-License-Identifier: GPL-3.0-only

"""Shared Windows subprocess configuration for external Android tools."""

from __future__ import annotations

import io
import subprocess
import threading
from collections.abc import Sequence
from typing import IO, Any


DEFAULT_MAX_CAPTURE_CHARS = 256 * 1024
PROCESS_DIAGNOSTIC_MAX_CHARS = 32 * 1024


def hidden_process_kwargs() -> dict[str, Any]:
    """Return subprocess options that prevent a console window on Windows."""
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }


def run_hidden(
    command: Sequence[str],
    *,
    timeout: float | None = None,
    capture_output: bool = True,
    stdout: int | IO[str] | None = None,
    stderr: int | IO[str] | None = None,
    max_capture_chars: int = DEFAULT_MAX_CAPTURE_CHARS,
) -> subprocess.CompletedProcess[str]:
    """Run a bounded external command without opening a Windows console.

    Output is decoded as UTF-8 with replacement for malformed bytes. The
    caller remains responsible for interpreting exit codes and translating
    ``OSError`` or ``TimeoutExpired`` into application-specific errors.

    Captured output is drained continuously and retained only up to
    ``max_capture_chars`` per stream so a noisy external tool cannot grow the
    launcher's memory usage without bound.
    """
    if max_capture_chars <= 0:
        raise ValueError("max_capture_chars must be positive")

    options: dict[str, Any] = {
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "check": False,
        **hidden_process_kwargs(),
    }
    capture_stdout = capture_output or stdout == subprocess.PIPE
    capture_stderr = capture_output or stderr == subprocess.PIPE
    if not capture_stdout and not capture_stderr:
        options["stdout"] = stdout
        options["stderr"] = stderr
        return subprocess.run(list(command), **options)

    popen_options = dict(options)
    popen_options.pop("timeout", None)
    popen_options.pop("check", None)
    popen_options["stdout"] = subprocess.PIPE if capture_stdout else stdout
    popen_options["stderr"] = subprocess.PIPE if capture_stderr else stderr
    process = subprocess.Popen(
        list(command),
        **popen_options,
    )
    output: list[str | None] = [None, None]

    def read_stream(index: int, stream: IO[str] | None) -> None:
        output[index] = read_bounded_text(stream, max_capture_chars)

    threads: list[threading.Thread] = []
    if capture_stdout:
        threads.append(
            threading.Thread(
                target=read_stream,
                args=(0, process.stdout),
                daemon=True,
            )
        )
    if capture_stderr:
        threads.append(
            threading.Thread(
                target=read_stream,
                args=(1, process.stderr),
                daemon=True,
            )
        )
    for thread in threads:
        thread.start()

    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait()
        for thread in threads:
            thread.join()
        raise subprocess.TimeoutExpired(
            list(command),
            timeout if timeout is not None else 0.0,
            output=output[0] or "",
            stderr=output[1] or "",
        ) from exc

    for thread in threads:
        thread.join()
    return subprocess.CompletedProcess(
        list(command),
        returncode,
        output[0] or "",
        output[1] or "",
    )


def read_bounded_text(stream: IO[str] | None, max_chars: int) -> str:
    """Drain a text stream while retaining only a bounded diagnostic prefix."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if stream is None:
        return ""

    chunks: list[str] = []
    retained = 0
    truncated = False
    while True:
        chunk = stream.read(8192)
        if not chunk:
            break
        available = max_chars - retained
        if available > 0:
            chunks.append(chunk[:available])
            retained += min(len(chunk), available)
        if len(chunk) > available:
            truncated = True
    result = "".join(chunks)
    return f"{result}\n…[output truncated]" if truncated else result
