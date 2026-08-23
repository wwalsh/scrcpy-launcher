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
IDYES = 6
IDNO = 7
IDCANCEL = 2


class DialogChoice(Enum):
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


def ask_yes_no_cancel(title: str, message: str) -> DialogChoice:
    """Display a native Yes/No/Cancel prompt."""
    return _ask(title, message, MB_YESNOCANCEL)


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


def _ask(title: str, message: str, buttons: int) -> DialogChoice:
    try:
        result = ctypes.windll.user32.MessageBoxW(
            None,
            message,
            title,
            buttons | MB_ICONERROR | MB_SETFOREGROUND,
        )
    except Exception:
        logger.exception("Could not display Windows prompt: %s: %s", title, message)
        return DialogChoice.CANCEL
    if result == IDYES:
        return DialogChoice.YES
    if result == IDNO:
        return DialogChoice.NO
    return DialogChoice.CANCEL
