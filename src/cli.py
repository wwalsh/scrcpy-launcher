# SPDX-License-Identifier: GPL-3.0-only

"""Command-line parsing for source and packaged entry points."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class LaunchMode(Enum):
    TRAY = "tray"
    SETTINGS = "settings"
    PACKAGE_SMOKE_TEST = "package-smoke-test"


class InvocationError(ValueError):
    pass


@dataclass(frozen=True)
class Invocation:
    mode: LaunchMode
    config_path: str | None = None
    allow_missing_bundled_tools: bool = False


def parse_invocation(arguments: Sequence[str]) -> Invocation:
    """Parse launcher arguments while retaining the legacy positional config path."""
    args = list(arguments)
    if not args:
        return Invocation(LaunchMode.TRAY)

    if args == ["--package-smoke-test"]:
        return Invocation(LaunchMode.PACKAGE_SMOKE_TEST)
    if args == ["--package-smoke-test", "--allow-missing-bundled-tools"]:
        return Invocation(LaunchMode.PACKAGE_SMOKE_TEST, allow_missing_bundled_tools=True)

    if args[0] == "--settings":
        if len(args) == 2 and not args[1].startswith("--"):
            return Invocation(LaunchMode.SETTINGS, args[1])
        if len(args) == 3 and args[1] == "--config":
            return Invocation(LaunchMode.SETTINGS, args[2])
        raise InvocationError("Usage: scrcpy-launcher --settings <config_path>")

    if args[0] == "--config":
        if len(args) == 2:
            return Invocation(LaunchMode.TRAY, args[1])
        raise InvocationError("Usage: scrcpy-launcher --config <config_path>")

    if len(args) == 1 and not args[0].startswith("--"):
        return Invocation(LaunchMode.TRAY, args[0])

    raise InvocationError(
        "Usage: scrcpy-launcher [--config <config_path>] | "
        "scrcpy-launcher --settings <config_path>"
    )
