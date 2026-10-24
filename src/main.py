# SPDX-License-Identifier: GPL-3.0-only

"""scrcpy-launcher — lightweight Windows tray utility."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .cli import InvocationError, LaunchMode, parse_invocation

if TYPE_CHECKING:
    from .config import Config

logger = logging.getLogger(__name__)


def setup_logging(mode: str):
    """Load logging setup only when a command mode needs it."""
    from .logging_setup import setup_logging as _setup_logging

    return _setup_logging(mode)


def load_config(config_path: Path | str = "config.json"):
    """Load configuration lazily while preserving the entrypoint seam for tests."""
    from .config import load_config as _load_config

    return _load_config(config_path)


def resolve_config_path(explicit_config_path: str | None = None) -> Path:
    """Resolve the configuration path without importing path helpers at startup."""
    from .paths import resolve_config_path as _resolve_config_path

    return _resolve_config_path(explicit_config_path)


def seed_portable_config(config_path: Path) -> bool:
    """Create a portable first-run configuration when the selected path needs it."""
    from .paths import seed_portable_config as _seed_portable_config

    return _seed_portable_config(config_path)


def inspect_recovery(config_path: Path):
    """Inspect configuration recovery candidates on demand."""
    from .config_recovery import inspect_recovery as _inspect_recovery

    return _inspect_recovery(config_path)


def restore_backup(inspection):
    """Restore a validated configuration backup on demand."""
    from .config_recovery import restore_backup as _restore_backup

    return _restore_backup(inspection)


def open_config_folder(config_path: Path) -> None:
    """Open the configuration folder using the recovery helper on demand."""
    from .config_recovery import open_config_folder as _open_config_folder

    _open_config_folder(config_path)


def SingleInstance():
    """Construct the single-instance guard only for normal tray mode."""
    from .single_instance import SingleInstance as _SingleInstance

    return _SingleInstance()


def show_error(title: str, message: str) -> None:
    """Display a native error dialog without loading Windows UI helpers at import time."""
    from .winui import show_error as _show_error

    _show_error(title, message)


def show_info(title: str, message: str) -> None:
    """Display a native information dialog on demand."""
    from .winui import show_info as _show_info

    _show_info(title, message)


def ask_yes_no(title: str, message: str):
    """Display a native Yes/No dialog on demand."""
    from .winui import ask_yes_no as _ask_yes_no

    return _ask_yes_no(title, message)


def ask_yes_no_cancel(title: str, message: str):
    """Display a native Yes/No/Cancel dialog on demand."""
    from .winui import ask_yes_no_cancel as _ask_yes_no_cancel

    return _ask_yes_no_cancel(title, message)


def main() -> int:
    """Run the selected command-line mode and return its process exit code."""
    try:
        invocation = parse_invocation(sys.argv[1:])
    except InvocationError as exc:
        log_path = setup_logging("tray")
        logger.error("Invalid command line: %s", exc)
        show_error("scrcpy-launcher Command Line Error", f"{exc}\n\nLog: {log_path}")
        return 2

    if invocation.mode is LaunchMode.SETTINGS:
        from .settings_main import run_settings

        return run_settings(invocation.config_path)

    if invocation.mode is LaunchMode.PACKAGE_SMOKE_TEST:
        return _package_smoke_test(
            require_bundled_tools=not invocation.allow_missing_bundled_tools
        )

    if invocation.mode is LaunchMode.PORTABLEAPPS_SMOKE_TEST:
        return _portableapps_smoke_test(invocation.config_path)

    from .single_instance import SingleInstanceError

    log_path = setup_logging("tray")
    instance = SingleInstance()
    try:
        acquired = instance.acquire()
    except SingleInstanceError as exc:
        logger.exception("Could not establish single-instance ownership")
        show_error(
            "scrcpy-launcher Startup Error",
            f"{exc}\n\nThe launcher was not started.\n\nLog: {log_path}",
        )
        return 1
    if not acquired:
        logger.info("A tray instance is already running")
        show_info(
            "scrcpy-launcher",
            "scrcpy-launcher is already running in this Windows session.",
        )
        return 0

    try:
        return _run(log_path, invocation.config_path)
    finally:
        instance.release()


def _run(log_path: Path, explicit_config_path: str | None = None) -> int:
    from .paths import PortableConfigError

    config_path = resolve_config_path(explicit_config_path)
    try:
        if seed_portable_config(config_path):
            logger.info("Created first-run portable configuration")
    except PortableConfigError as exc:
        logger.exception("Could not create portable configuration")
        show_error(
            "scrcpy-launcher Portable Configuration Error",
            f"{exc}\n\nThe launcher was not started.\n\nLog: {log_path}",
        )
        return 1
    config = _load_startup_config(config_path, log_path)
    if config is None:
        return 1
    logger.info("Loaded %d configured sessions", len(config.sessions))

    try:
        _run_tray(config)
    except Exception as exc:
        logger.exception("Fatal tray error")
        show_error(
            "scrcpy-launcher Error",
            f"The tray application stopped unexpectedly:\n\n{exc}\n\nLog: {log_path}",
        )
        return 1
    return 0


def _run_tray(config: Config) -> None:
    """Import and run the Win32 tray only after tray mode is selected."""
    from .tray import run_tray

    run_tray(config)


def _load_startup_config(config_path: Path, log_path: Path) -> Config | None:
    from .config import Config, ConfigError
    from .config_recovery import ConfigRecoveryError
    from .winui import DialogChoice

    try:
        return load_config(config_path)
    except ConfigError as exc:
        logger.exception("Could not load configuration")
        load_error = exc

    inspection = inspect_recovery(config_path)
    if inspection.backup_valid:
        choice = ask_yes_no_cancel(
            "scrcpy-launcher Configuration Recovery",
            f"The configuration could not be loaded:\n\n{load_error}\n\n"
            f"A valid backup is available at:\n{inspection.backup_path}\n\n"
            "Yes: restore the backup and start the launcher\n"
            "No: open the configuration folder and exit\n"
            "Cancel: exit without changing any files",
        )
        if choice is DialogChoice.YES:
            try:
                return restore_backup(inspection)
            except ConfigRecoveryError as recovery_exc:
                logger.exception("Configuration recovery failed")
                show_error(
                    "scrcpy-launcher Recovery Error",
                    f"{recovery_exc}\n\nThe launcher was not started.\n\nLog: {log_path}",
                )
                return None
        if choice is DialogChoice.NO:
            _open_folder_or_report(config_path, log_path)
        return None

    choice = ask_yes_no(
        "scrcpy-launcher Configuration Error",
        f"The configuration could not be loaded:\n\n{load_error}\n\n"
        f"No valid backup is available.\n\n"
        "Yes: open the configuration folder and exit\n"
        "No: exit without changing any files",
    )
    if choice is DialogChoice.YES:
        _open_folder_or_report(config_path, log_path)
    return None


def _open_folder_or_report(config_path: Path, log_path: Path) -> None:
    from .config_recovery import ConfigRecoveryError

    try:
        open_config_folder(config_path)
    except ConfigRecoveryError as exc:
        logger.exception("Could not open configuration folder")
        show_error(
            "scrcpy-launcher Configuration Error",
            f"{exc}\n\nLog: {log_path}",
        )


def _package_smoke_test(*, require_bundled_tools: bool = True) -> int:
    """Exercise frozen-only imports and resources without opening UI or user configuration."""
    try:
        import tkinter  # noqa: F401
        import win32gui  # noqa: F401

        from .runtime import resource_path
        from .scrcpy_runtime import validate_bundled_installation
        from .settings import _SettingsDialog  # noqa: F401

        if not resource_path("icon.ico").is_file():
            return 1
        if require_bundled_tools:
            validate_bundled_installation()
        return 0
    except Exception:
        return 1


def _portableapps_smoke_test(explicit_config_path: str | None) -> int:
    """Verify the frozen app is isolated by the real PortableApps.com launcher."""
    from .autostart import AutostartUnavailableError, create_autostart_manager
    from .paths import portableapps_data_dir
    from .runtime import is_frozen

    log_path = setup_logging("portableapps-smoke")
    try:
        if not is_frozen():
            raise RuntimeError("PortableApps smoke testing requires a frozen build")
        data_dir = portableapps_data_dir()
        if data_dir is None:
            raise RuntimeError("The PortableApps data environment was not supplied")

        package_root = Path(sys.executable).resolve().parent.parent.parent
        if data_dir != (package_root / "Data").resolve():
            raise RuntimeError("The PortableApps data directory escapes the package root")

        config_path = resolve_config_path(explicit_config_path)
        expected_config = data_dir / "config.json"
        if config_path != expected_config:
            raise RuntimeError("The configuration path is outside PortableApps Data")
        if log_path.parent != data_dir / "logs":
            raise RuntimeError("The log path is outside PortableApps Data")

        if seed_portable_config(config_path):
            logger.info("Created PortableApps smoke-test configuration")
        config = load_config(config_path)
        if config.config_path != expected_config:
            raise RuntimeError("The loaded configuration path is not portable")

        try:
            create_autostart_manager(config_path)
        except AutostartUnavailableError:
            pass
        else:
            raise RuntimeError("Windows autostart is available in PortableApps mode")

        logger.info("PortableApps launcher integration smoke test passed")
        return 0
    except Exception:
        logger.exception("PortableApps launcher integration smoke test failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
