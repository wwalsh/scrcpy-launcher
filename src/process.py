# SPDX-License-Identifier: GPL-3.0-only

"""Shared Windows subprocess configuration for external Android tools."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from typing import IO, Any


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
) -> subprocess.CompletedProcess[str]:
    """Run a bounded external command without opening a Windows console.

    Output is decoded as UTF-8 with replacement for malformed bytes. The
    caller remains responsible for interpreting exit codes and translating
    ``OSError`` or ``TimeoutExpired`` into application-specific errors.
    """
    options: dict[str, Any] = {
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "check": False,
        **hidden_process_kwargs(),
    }
    if capture_output:
        options["capture_output"] = True
    else:
        options["stdout"] = stdout
        options["stderr"] = stderr
    return subprocess.run(list(command), **options)
