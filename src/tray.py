# SPDX-License-Identifier: GPL-3.0-only

"""Build and run the system tray icon with a scrcpy session menu."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import logging
import shutil
import subprocess
import threading
from pathlib import Path
import win32con
import win32gui

from .bundled_manifest import BUNDLED_SCRCPY_VERSION
from .config import Config, ConfigError, Session, load_config
from .launcher import (
    SessionLaunchError,
    active_session_count,
    launch_session,
    stop_adb_server,
    stop_all_sessions,
)
from .project_links import LATEST_RELEASE_URL, REPOSITORY_URL
from .runtime import resource_path, settings_launch_spec
from .scrcpy_runtime import ScrcpyResolutionError, resolve_scrcpy
from .version import APP_VERSION
from .winui import (
    DialogChoice,
    ask_yes_no_information,
    open_url,
    show_error,
    show_info,
)

logger = logging.getLogger(__name__)

ICON_PATH = str(resource_path("icon.ico"))

_WINDOW_CLASS = "ScrcpyTrayWindow"

# Win32 constants
NIM_ADD = 0
NIM_DELETE = 2
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
WM_NOTIFY = 0x400 + 11
WM_RBUTTONUP = 0x0205
WM_LBUTTONUP = 0x0202
WM_DESTROY = 0x0002


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", w.ULONG),
        ("Data2", w.WORD),
        ("Data3", w.WORD),
        ("Data4", w.BYTE * 8),
    ]


class _NOTIFYICONDATAW(ctypes.Structure):
    class _VERSION_OR_TIMEOUT(ctypes.Union):
        _fields_ = [
            ("uTimeout", w.UINT),
            ("uVersion", w.UINT),
        ]

    _fields_ = [
        ("cbSize", w.DWORD),
        ("hWnd", w.HWND),
        ("uID", w.UINT),
        ("uFlags", w.UINT),
        ("uCallbackMessage", w.UINT),
        ("hIcon", w.HICON),
        ("szTip", w.WCHAR * 128),
        ("dwState", w.DWORD),
        ("dwStateMask", w.DWORD),
        ("szInfo", w.WCHAR * 256),
        ("version_or_timeout", _VERSION_OR_TIMEOUT),
        ("szInfoTitle", w.WCHAR * 64),
        ("dwInfoFlags", w.DWORD),
        ("guidItem", _GUID),
        ("hBalloonIcon", w.HICON),
    ]
    _anonymous_ = ["version_or_timeout"]


_shell32 = ctypes.windll.shell32
_user32 = ctypes.windll.user32


def _register_window_class() -> int:
    wc = win32gui.WNDCLASS()
    wc.hInstance = win32gui.GetModuleHandle(None)
    wc.lpszClassName = _WINDOW_CLASS
    wc.style = win32con.CS_VREDRAW | win32con.CS_HREDRAW
    wc.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)
    wc.hbrBackground = win32con.COLOR_WINDOW + 1
    wc.lpfnWndProc = _wnd_proc
    return win32gui.RegisterClass(wc)


def _create_window(class_atom: int) -> int:
    return win32gui.CreateWindow(
        class_atom,
        _WINDOW_CLASS,
        win32con.WS_POPUP,
        0, 0, 0, 0,
        0, 0,
        win32gui.GetModuleHandle(None),
        None,
    )


def _load_icon() -> int:
    """Load and return the tray icon handle."""
    return _user32.LoadImageW(
        None,
        ICON_PATH,
        win32con.IMAGE_ICON,
        0, 0,
        win32con.LR_DEFAULTSIZE | win32con.LR_LOADFROMFILE,
    )


def _add_icon(hwnd: int, title: str, hicon: int) -> bool:
    """Register an already-loaded icon with the current Explorer shell."""
    nid = _NOTIFYICONDATAW()
    nid.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
    nid.hWnd = hwnd
    nid.uID = 0
    nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
    nid.uCallbackMessage = WM_NOTIFY
    nid.hIcon = hicon
    nid.szTip = title

    return bool(_shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)))


def _hide_icon(hwnd: int) -> None:
    nid = _NOTIFYICONDATAW()
    nid.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
    nid.hWnd = hwnd
    nid.uID = 0
    _shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))


def _restore_icon(hwnd: int) -> bool:
    """Restore the tray icon after Windows Explorer recreates its taskbar."""
    if not _tray_icon_handle:
        logger.warning("Cannot restore tray icon because no icon handle is loaded")
        return False
    try:
        restored = _add_icon(hwnd, _tray_title, _tray_icon_handle)
    except Exception:
        logger.exception("Could not restore tray icon after Explorer restart")
        return False
    if restored:
        logger.info("Restored tray icon after Explorer restart")
    else:
        logger.error("Explorer rejected tray icon restoration")
    return restored


def _show_menu(hwnd: int) -> None:
    global _state
    try:
        _state = load_config(_state.config_path)
    except ConfigError as exc:
        logger.exception("Could not reload configuration; retaining last good state")
        show_error(
            "scrcpy-launcher Configuration Error",
            f"Could not reload the configuration:\n\n{exc}\n\n"
            "The last successfully loaded sessions will remain available.",
        )
    else:
        _log_scrcpy_selection(_state)
    x, y = win32gui.GetCursorPos()
    hmenu = win32gui.CreatePopupMenu()

    for i, session in enumerate(_state.sessions, start=1):
        win32gui.AppendMenu(hmenu, win32con.MF_STRING, i, session.name)

    win32gui.AppendMenu(hmenu, win32con.MF_SEPARATOR, 0, "")
    session_count = len(_state.sessions)
    stop_sessions_id = session_count + 1
    stop_adb_id = session_count + 2
    settings_id = session_count + 3
    update_id = session_count + 4
    about_id = session_count + 5
    quit_id = session_count + 6
    settings_flags, settings_label, quit_flags, quit_label = _settings_menu_state()
    update_flags, update_label = _update_menu_state()
    stop_sessions_flags = (
        win32con.MF_STRING
        if active_session_count()
        else win32con.MF_STRING | win32con.MF_GRAYED
    )
    stop_adb_flags = (
        win32con.MF_STRING
        if _resolve_adb_path(_state) is not None
        else win32con.MF_STRING | win32con.MF_GRAYED
    )
    win32gui.AppendMenu(hmenu, stop_sessions_flags, stop_sessions_id, "Stop all scrcpy sessions")
    win32gui.AppendMenu(hmenu, stop_adb_flags, stop_adb_id, "Stop ADB server")
    win32gui.AppendMenu(hmenu, win32con.MF_SEPARATOR, 0, "")
    win32gui.AppendMenu(hmenu, settings_flags, settings_id, settings_label)
    win32gui.AppendMenu(hmenu, update_flags, update_id, update_label)
    win32gui.AppendMenu(hmenu, win32con.MF_STRING, about_id, "About scrcpy-launcher")
    win32gui.AppendMenu(hmenu, win32con.MF_SEPARATOR, 0, "")
    win32gui.AppendMenu(hmenu, quit_flags, quit_id, quit_label)

    win32gui.SetForegroundWindow(hwnd)
    cmd = win32gui.TrackPopupMenu(
        hmenu,
        win32con.TPM_RIGHTBUTTON | win32con.TPM_RETURNCMD,
        x, y, 0, hwnd, None,
    )
    win32gui.DestroyMenu(hmenu)

    if cmd == quit_id:
        if _settings_is_open():
            return
        win32gui.PostQuitMessage(0)
        return
    elif cmd == stop_sessions_id:
        _stop_all_sessions()
        return
    elif cmd == stop_adb_id:
        _stop_adb_server(_state)
        return
    elif cmd == settings_id:
        _spawn_settings_process(str(_state.config_path))
        return
    elif cmd == update_id:
        _start_update_check()
        return
    elif cmd == about_id:
        _show_about()
        return
    elif cmd:
        session = _state.sessions[cmd - 1] if cmd <= len(_state.sessions) else None
        if session:
            _launch_configured_session(_state, session)


def _resolve_configured_scrcpy(config: Config, *, report_error: bool) -> str | None:
    try:
        resolution = resolve_scrcpy(config.scrcpy_mode, config.scrcpy_path)
    except ScrcpyResolutionError as exc:
        logger.error("Could not resolve configured scrcpy: %s", exc)
        if report_error:
            show_error("scrcpy Configuration Error", str(exc))
        return None
    logger.info("Using %s", resolution.description)
    return str(resolution.path)


def _log_scrcpy_selection(config: Config) -> None:
    _resolve_configured_scrcpy(config, report_error=False)


def _resolve_adb_path(config: Config) -> str | None:
    """Resolve ADB beside the selected scrcpy executable or from PATH."""
    scrcpy_path = _resolve_configured_scrcpy(config, report_error=False)
    if scrcpy_path:
        adjacent = Path(scrcpy_path).with_name("adb.exe")
        if adjacent.is_file():
            return str(adjacent)
    return shutil.which("adb.exe")


def _stop_all_sessions() -> None:
    stopped = stop_all_sessions()
    logger.info("Stopped %s launcher-managed scrcpy session(s)", stopped)


def _stop_adb_server(config: Config) -> None:
    choice = ask_yes_no_information(
        "Stop ADB server",
        "Stop the ADB server? Other Android tools using ADB may be interrupted.",
    )
    if choice is not DialogChoice.YES:
        return
    adb_path = _resolve_adb_path(config)
    if adb_path is None:
        show_error("ADB Shutdown Failed", "Could not find the configured ADB executable.")
    elif not stop_adb_server(adb_path):
        show_error("ADB Shutdown Failed", f"Could not stop the ADB server using:\n\n{adb_path}")


def _launch_configured_session(config: Config, session: Session) -> None:
    scrcpy_path = _resolve_configured_scrcpy(config, report_error=True)
    if scrcpy_path is not None:
        _launch_session(scrcpy_path, session)


def _launch_session(scrcpy_path: str, session: Session) -> None:
    def report_process_error(exc: SessionLaunchError) -> None:
        logger.error("A configured session failed")
        show_error(
            "scrcpy Session Failed",
            f"Session '{session.name}' failed:\n\n{exc}",
        )

    try:
        launch_session(scrcpy_path, session.args, report_process_error)
    except SessionLaunchError as exc:
        report_process_error(exc)


def _launch_first_session(config: Config) -> None:
    if config.sessions:
        _launch_configured_session(config, config.sessions[0])


def _settings_is_open() -> bool:
    """Return whether the tray-launched Settings process is still running."""
    global _settings_process
    if _settings_process is None:
        return False
    if _settings_process.poll() is None:
        return True
    _settings_process = None
    return False


def _settings_menu_state() -> tuple[int, str, int, str]:
    """Return flags and labels for Settings and Quit menu items."""
    if _settings_is_open():
        disabled = win32con.MF_STRING | win32con.MF_GRAYED
        return disabled, "Settings (open)", disabled, "Quit (close Settings first)"
    return win32con.MF_STRING, "Settings", win32con.MF_STRING, "Quit"


def _update_is_running() -> bool:
    """Return whether a user-requested update check is still running."""
    global _update_check_thread
    if _update_check_thread is None:
        return False
    if _update_check_thread.is_alive():
        return True
    _update_check_thread = None
    return False


def _update_menu_state() -> tuple[int, str]:
    if _update_is_running():
        return (
            win32con.MF_STRING | win32con.MF_GRAYED,
            "Check for updates… (in progress)",
        )
    return win32con.MF_STRING, "Check for updates…"


def _open_project_url(url: str) -> None:
    if not open_url(url):
        show_error(
            "scrcpy-launcher Link Error",
            f"Windows could not open the project page.\n\n{url}",
        )


def _show_about() -> None:
    message = (
        f"scrcpy-launcher {APP_VERSION}\n\n"
        "Windows system-tray launcher for reusable scrcpy sessions.\n\n"
        "License: GPL-3.0-only\n"
        f"Bundled scrcpy: {BUNDLED_SCRCPY_VERSION}\n"
        "Third-party components retain their original licenses.\n\n"
        f"Project: {REPOSITORY_URL}\n\n"
        "Open the project page?"
    )
    if (
        ask_yes_no_information("About scrcpy-launcher", message)
        is DialogChoice.YES
    ):
        _open_project_url(REPOSITORY_URL)


def _run_update_check() -> None:
    global _update_check_thread
    from .update_check import UpdateCheckError, check_latest_release

    try:
        result = check_latest_release(APP_VERSION)
        if result.update_available:
            choice = ask_yes_no_information(
                "scrcpy-launcher Update Available",
                f"Installed version: {result.current_version}\n"
                f"Latest version: {result.latest_version}\n\n"
                "Open the GitHub release page?",
            )
            if choice is DialogChoice.YES:
                _open_project_url(LATEST_RELEASE_URL)
        else:
            show_info(
                "scrcpy-launcher Updates",
                f"scrcpy-launcher {APP_VERSION} is up to date.\n\n"
                f"Latest public release: {result.latest_version}",
            )
    except UpdateCheckError as exc:
        logger.warning("Update check failed: %s", exc)
        show_error(
            "scrcpy-launcher Update Check Failed",
            f"Could not check for updates.\n\n{exc}",
        )
    except Exception as exc:
        logger.exception("Unexpected update check failure")
        show_error(
            "scrcpy-launcher Update Check Failed",
            f"Could not check for updates.\n\n{exc}",
        )
    finally:
        _update_check_thread = None


def _start_update_check() -> bool:
    """Start one background update check, returning whether it was started."""
    global _update_check_thread
    if _update_is_running():
        return False
    _update_check_thread = threading.Thread(
        target=_run_update_check,
        name="scrcpy-launcher-update-check",
        daemon=True,
    )
    _update_check_thread.start()
    return True


def _spawn_settings_process(config_path: str) -> bool:
    """Launch one settings UI process, returning whether a process was started."""
    global _settings_process
    if _settings_is_open():
        return False
    launch_spec = settings_launch_spec(config_path)
    try:
        _settings_process = subprocess.Popen(
            launch_spec.command,
            cwd=launch_spec.cwd,
        )
    except OSError as exc:
        logger.error("Could not launch Settings: %s", exc)
        show_error("scrcpy-launcher Settings Error", f"Could not launch Settings:\n\n{exc}")
        _settings_process = None
        return False
    return True


def _wnd_proc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
    global _state
    if _taskbar_created_message is not None and msg == _taskbar_created_message:
        _restore_icon(hwnd)
        return 0
    if msg == WM_DESTROY:
        win32gui.PostQuitMessage(0)
        return 0
    if msg == WM_NOTIFY:
        return _on_notify(hwnd, wparam, lparam)
    return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)


def _on_notify(hwnd: int, uid: int, mouse_event: int) -> int:
    if mouse_event == WM_RBUTTONUP:
        _show_menu(hwnd)
    elif mouse_event == WM_LBUTTONUP:
        _launch_first_session(_state)
    return 0


# Module-level state
_state: Config = None  # type: ignore
_settings_process: subprocess.Popen[bytes] | None = None
_update_check_thread: threading.Thread | None = None
_taskbar_created_message: int | None = None
_tray_title = ""
_tray_icon_handle = 0


def run_tray(config: Config) -> None:
    """Run the native notification-area loop for the supplied configuration."""
    """Create a pywin32 tray icon and run the message loop."""
    global _state, _taskbar_created_message, _tray_title, _tray_icon_handle

    _state = config
    _log_scrcpy_selection(config)

    class_atom = 0
    hwnd = 0
    try:
        _taskbar_created_message = win32gui.RegisterWindowMessage("TaskbarCreated")
        _tray_title = config.sessions[0].name if config.sessions else "scrcpy"
        class_atom = _register_window_class()
        hwnd = _create_window(class_atom)
        _tray_icon_handle = _load_icon()
        if not _add_icon(hwnd, _tray_title, _tray_icon_handle):
            logger.error("Explorer rejected the initial tray icon registration")
        win32gui.PumpMessages()
    finally:
        if hwnd:
            try:
                _hide_icon(hwnd)
            except Exception:
                logger.exception("Could not remove tray icon during shutdown")
        if _tray_icon_handle:
            try:
                win32gui.DestroyIcon(_tray_icon_handle)
            except Exception:
                logger.exception("Could not destroy tray icon handle during shutdown")
        if hwnd:
            try:
                win32gui.DestroyWindow(hwnd)
            except Exception:
                pass
        if class_atom:
            try:
                win32gui.UnregisterClass(_WINDOW_CLASS, win32gui.GetModuleHandle(None))
            except Exception:
                logger.exception("Could not unregister tray window class during shutdown")
        _taskbar_created_message = None
        _tray_title = ""
        _tray_icon_handle = 0
