# SPDX-License-Identifier: GPL-3.0-only

"""Session-import choices and summary text for the Settings UI."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


IMPORT_MODE_MERGE = "merge"
IMPORT_MODE_REPLACE = "replace"


def _import_summary_text(
    mode: str,
    imported_count: int,
    replaced_count: int,
    renamed: tuple[tuple[str, str], ...] = (),
) -> str:
    noun = "session" if imported_count == 1 else "sessions"
    if mode == IMPORT_MODE_REPLACE:
        replaced_noun = "session" if replaced_count == 1 else "sessions"
        summary = (
            f"Imported {imported_count} {noun} and replaced "
            f"{replaced_count} existing {replaced_noun}."
        )
    else:
        summary = f"Merged {imported_count} {noun}."
    if renamed:
        rename_lines = [f"{old} → {new}" for old, new in renamed[:10]]
        if len(renamed) > 10:
            rename_lines.append(f"…and {len(renamed) - 10} more")
        summary += "\n\nRenamed conflicts:\n" + "\n".join(rename_lines)
    return summary + "\n\nClick Save to persist these changes."


class _ImportModeDialog:
    """Small modal dialog that returns merge, replace, or cancellation."""

    def __init__(self, parent, current_count: int, imported_count: int) -> None:
        self.choice: str | None = None
        self._parent = parent
        self._dialog = tk.Toplevel(parent)
        self._dialog.title("Import sessions")
        self._dialog.resizable(False, False)
        self._dialog.transient(parent)
        self._dialog.protocol("WM_DELETE_WINDOW", self._cancel)
        self._dialog.bind("<Escape>", lambda _event: self._cancel())

        frame = ttk.Frame(self._dialog, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        message = (
            f"The backup contains {imported_count} session"
            f"{'s' if imported_count != 1 else ''}.\n"
            f"The current configuration contains {current_count}.\n\n"
            "Merge appends imported sessions and renames conflicts.\n"
            "Replace removes every current session before importing."
        )
        ttk.Label(frame, text=message, justify=tk.LEFT).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 16)
        )
        merge_button = ttk.Button(frame, text="Merge", command=self._merge)
        merge_button.grid(row=1, column=0)
        ttk.Button(frame, text="Replace", command=self._replace).grid(
            row=1, column=1, padx=8
        )
        ttk.Button(frame, text="Cancel", command=self._cancel).grid(row=1, column=2)

        self._dialog.grab_set()
        self._dialog.update_idletasks()
        width = self._dialog.winfo_reqwidth()
        height = self._dialog.winfo_reqheight()
        x = parent.winfo_rootx() + max((parent.winfo_width() - width) // 2, 0)
        y = parent.winfo_rooty() + max((parent.winfo_height() - height) // 2, 0)
        self._dialog.geometry(f"+{x}+{y}")
        merge_button.focus_set()
        self._dialog.wait_window()

    def _merge(self) -> None:
        self.choice = IMPORT_MODE_MERGE
        self._close()

    def _replace(self) -> None:
        self.choice = IMPORT_MODE_REPLACE
        self._close()

    def _cancel(self) -> None:
        self.choice = None
        self._close()

    def _close(self) -> None:
        if self._dialog.winfo_exists():
            self._dialog.grab_release()
            self._dialog.destroy()
        if self._parent.winfo_exists():
            self._parent.grab_set()


def _choose_import_mode(parent, current_count: int, imported_count: int) -> str | None:
    return _ImportModeDialog(parent, current_count, imported_count).choice
