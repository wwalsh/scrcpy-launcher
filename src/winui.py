# SPDX-License-Identifier: GPL-3.0-only

"""Small native Windows UI helpers safe to call outside tkinter's process."""

from __future__ import annotations

import ctypes
import logging
from enum import Enum

logger = logging.getLogger(__name__)

MB_OK = 0x00000000
MB_YESNO = 0x00000004
MB_YESNOCANCEL = 0x00000003
MB_ICONERROR = 0x00000010
MB_ICONINFORMATION = 0x00000040
MB_SETFOREGROUND = 0x00010000
SW_SHOWNORMAL = 1
IDYES = 6
IDNO = 7


class DialogChoice(Enum):
    """Result values returned by native confirmation dialogs."""
    YES = "yes"
    NO = "no"
    CANCEL = "cancel"


def show_error(title: str, message: str) -> None:
    """Display a foreground native Windows error dialog."""
    _show_message(title, message, MB_ICONERROR)


def show_info(title: str, message: str) -> None:
    """Display a foreground native Windows information dialog."""
    _show_message(title, message, MB_ICONINFORMATION)


def ask_yes_no(title: str, message: str) -> DialogChoice:
    """Display a native Yes/No prompt."""
    return _ask(title, message, MB_YESNO)


def ask_yes_no_information(title: str, message: str) -> DialogChoice:
    """Display a native informational Yes/No prompt."""
    return _ask(title, message, MB_YESNO, icon=MB_ICONINFORMATION)


def ask_yes_no_cancel(title: str, message: str) -> DialogChoice:
    """Display a native Yes/No/Cancel prompt."""
    return _ask(title, message, MB_YESNOCANCEL)


def open_url(url: str) -> bool:
    """Open a trusted HTTPS URL with the user's default browser."""
    if not url.startswith("https://"):
        logger.error("Refusing to open a non-HTTPS URL")
        return False
    try:
        shell_execute = ctypes.windll.shell32.ShellExecuteW
        shell_execute.restype = ctypes.c_void_p
        result = shell_execute(
            None,
            "open",
            url,
            None,
            None,
            SW_SHOWNORMAL,
        )
    except Exception:
        logger.exception("Could not open URL: %s", url)
        return False
    if result is None or result <= 32:
        logger.error("Windows could not open URL (ShellExecute result %s): %s", result, url)
        return False
    return True


def _show_message(title: str, message: str, icon: int) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            message,
            title,
            MB_OK | icon | MB_SETFOREGROUND,
        )
    except Exception:
        logger.exception("Could not display Windows dialog: %s: %s", title, message)


def _ask(
    title: str,
    message: str,
    buttons: int,
    *,
    icon: int = MB_ICONERROR,
) -> DialogChoice:
    try:
        result = ctypes.windll.user32.MessageBoxW(
            None,
            message,
            title,
            buttons | icon | MB_SETFOREGROUND,
        )
    except Exception:
        logger.exception("Could not display Windows prompt: %s: %s", title, message)
        return DialogChoice.CANCEL
    if result == IDYES:
        return DialogChoice.YES
    if result == IDNO:
        return DialogChoice.NO
    return DialogChoice.CANCEL
