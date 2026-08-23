# SPDX-License-Identifier: GPL-3.0-only

"""Runtime helpers that differ between source and PyInstaller builds."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_path(name: str) -> Path:
    """Return a bundled resource path in frozen mode or the repository path in source mode."""
    if is_frozen():
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return bundle_root / name
    return Path(__file__).resolve().parent.parent / name


@dataclass(frozen=True)
class ProcessLaunchSpec:
    command: list[str]
    cwd: str | None


def settings_launch_spec(config_path: str) -> ProcessLaunchSpec:
    """Build the child command used to open the separate Settings process."""
    if is_frozen():
        return ProcessLaunchSpec(
            [sys.executable, "--settings", config_path],
            None,
        )
    project_root = str(Path(__file__).resolve().parent.parent)
    return ProcessLaunchSpec(
        [sys.executable, "-m", "src.settings_main", config_path],
        project_root,
    )
