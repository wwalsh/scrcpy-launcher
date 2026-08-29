# SPDX-License-Identifier: GPL-3.0-only

"""Resolve and validate bundled or user-selected scrcpy executables."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .bundled_manifest import BUNDLED_FILE_HASHES, BUNDLED_SCRCPY_VERSION
from .config import SCRCPY_MODE_BUNDLED, SCRCPY_MODE_CUSTOM
from .runtime import is_frozen
from .safe_io import InputTooLargeError, read_limited_utf8

BUNDLED_RELATIVE_PATH = Path("tools") / "scrcpy" / "scrcpy.exe"


class ScrcpyResolutionError(RuntimeError):
    """The configured scrcpy executable cannot be used."""


@dataclass(frozen=True)
class ScrcpyResolution:
    """Resolved scrcpy executable, selection mode, and user-facing description."""
    path: Path
    mode: str
    description: str


def application_root(
    *, frozen: bool | None = None, executable: Path | str | None = None
) -> Path:
    """Return the relocatable application root, not PyInstaller's internal root."""
    packaged = is_frozen() if frozen is None else frozen
    if packaged:
        executable_path = Path(executable) if executable is not None else Path(sys.executable)
        return executable_path.resolve().parent
    return Path(__file__).resolve().parent.parent


def bundled_scrcpy_path(*, root: Path | str | None = None) -> Path:
    """Return the bundled ``scrcpy.exe`` path under an application root."""
    base = Path(root).resolve() if root is not None else application_root()
    return base / BUNDLED_RELATIVE_PATH


def resolve_scrcpy(
    mode: str,
    custom_path: str,
    *,
    root: Path | str | None = None,
) -> ScrcpyResolution:
    """Resolve the selected executable without silently changing selection modes."""
    if mode == SCRCPY_MODE_BUNDLED:
        validation_root = Path(root).resolve() if root is not None else application_root()
        path = _validate_bundled_installation_cached(str(validation_root))
        return ScrcpyResolution(path, mode, f"bundled scrcpy {BUNDLED_SCRCPY_VERSION}")

    if mode != SCRCPY_MODE_CUSTOM:
        raise ScrcpyResolutionError(f"Unknown scrcpy selection mode: {mode}")

    value = custom_path.strip()
    if not value:
        raise ScrcpyResolutionError("Choose a custom scrcpy executable in Settings.")
    expanded = Path(value).expanduser()
    if expanded.is_file():
        path = expanded.resolve()
    else:
        discovered = shutil.which(value)
        if not discovered:
            raise ScrcpyResolutionError(f"Custom scrcpy executable was not found: {value}")
        path = Path(discovered).resolve()
    return ScrcpyResolution(path, mode, "custom scrcpy executable")


def validate_bundled_installation(*, root: Path | str | None = None) -> Path:
    """Validate the complete packaged inventory against hashes compiled into the launcher."""
    scrcpy_path = bundled_scrcpy_path(root=root)
    bundle_dir = scrcpy_path.parent
    metadata_path = bundle_dir / "BUNDLE-METADATA.json"
    try:
        metadata = json.loads(read_limited_utf8(metadata_path))
    except (OSError, UnicodeDecodeError, InputTooLargeError, json.JSONDecodeError) as exc:
        raise ScrcpyResolutionError(
            f"Bundled scrcpy metadata is invalid: {exc}. Repair or reinstall "
            "scrcpy-launcher."
        ) from exc

    bundle = metadata.get("bundle")
    if not isinstance(bundle, dict) or bundle.get("version") != BUNDLED_SCRCPY_VERSION:
        raise ScrcpyResolutionError(
            f"Bundled scrcpy metadata must report version {BUNDLED_SCRCPY_VERSION}."
        )
    inventory = metadata.get("files")
    if not isinstance(inventory, dict):
        raise ScrcpyResolutionError("Bundled scrcpy metadata has no file inventory.")
    if inventory != BUNDLED_FILE_HASHES:
        raise ScrcpyResolutionError(
            "Bundled scrcpy metadata does not match this launcher. Repair or reinstall "
            "scrcpy-launcher."
        )

    # Inventory and hash files in one walk. The inventory check remains
    # separate from metadata validation, but avoids a second filesystem pass
    # over the packaged runtime.
    actual_files: set[str] = set()
    actual_hashes: dict[str, str] = {}
    for path in bundle_dir.rglob("*"):
        if not path.is_file() or path == metadata_path:
            continue
        filename = path.relative_to(bundle_dir).as_posix()
        actual_files.add(filename)
        if filename not in BUNDLED_FILE_HASHES:
            continue
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise ScrcpyResolutionError(
                f"Could not verify bundled scrcpy file {path}: {exc}"
            ) from exc
        actual_hashes[filename] = digest.hexdigest()

    expected_files = set(BUNDLED_FILE_HASHES)
    if actual_files != expected_files:
        missing = sorted(expected_files - actual_files)
        unexpected = sorted(actual_files - expected_files)
        details: list[str] = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected: {', '.join(unexpected)}")
        raise ScrcpyResolutionError(
            "Bundled scrcpy inventory failed verification (" + "; ".join(details) + "). "
            "Repair or reinstall scrcpy-launcher."
        )

    for filename, expected_hash in BUNDLED_FILE_HASHES.items():
        if actual_hashes.get(filename) != expected_hash:
            raise ScrcpyResolutionError(
                f"Bundled scrcpy file failed verification: {bundle_dir / filename}. "
                "Repair or reinstall "
                "scrcpy-launcher."
            )
    return scrcpy_path


@lru_cache(maxsize=None)
def _validate_bundled_installation_cached(root: str) -> Path:
    """Validate a bundle once per application process."""
    return validate_bundled_installation(root=root)


def clear_bundled_validation_cache() -> None:
    """Clear process-local integrity results (primarily for repair and tests)."""
    _validate_bundled_installation_cached.cache_clear()
