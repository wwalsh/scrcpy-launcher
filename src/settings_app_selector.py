# SPDX-License-Identifier: GPL-3.0-only

"""Searchable tkinter dialog for selecting an Android application."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .device_apps import DeviceApp


def _filter_device_apps(apps: list[DeviceApp], query: str) -> list[DeviceApp]:
    """Sort apps predictably and filter by friendly name or package."""
    needle = query.strip().casefold()
    filtered = (
        app
        for app in apps
        if not needle
        or needle in app.name.casefold()
        or needle in app.package_name.casefold()
    )
    return sorted(filtered, key=lambda app: (app.name.casefold(), app.package_name.casefold()))


class _AppSelectionDialog:
    """Modal searchable application browser that returns a selected DeviceApp."""

    def __init__(self, parent, apps: list[DeviceApp]) -> None:
        self.selected: DeviceApp | None = None
        self._parent = parent
        self._apps = apps
        self._app_by_item: dict[str, DeviceApp] = {}

        self._dialog = tk.Toplevel(parent)
        self._dialog.title("Select Android application")
        self._dialog.minsize(720, 440)
        self._dialog.transient(parent)
        self._dialog.protocol("WM_DELETE_WINDOW", self._cancel)
        self._dialog.bind("<Escape>", lambda _event: self._cancel())
        self._dialog.bind("<Return>", self._choose_event)
        self._dialog.rowconfigure(1, weight=1)
        self._dialog.columnconfigure(0, weight=1)

        search_frame = ttk.Frame(self._dialog, padding=(12, 12, 12, 8))
        search_frame.grid(row=0, column=0, sticky="ew")
        search_frame.columnconfigure(1, weight=1)
        ttk.Label(search_frame, text="Search").grid(row=0, column=0, padx=(0, 8))
        self._search_var = tk.StringVar()
        self._search_entry = ttk.Entry(search_frame, textvariable=self._search_var)
        self._search_entry.grid(row=0, column=1, sticky="ew")
        self._search_entry.bind("<Down>", self._focus_first_result)
        self._search_var.trace_add("write", self._on_search_changed)

        list_frame = ttk.Frame(self._dialog, padding=(12, 0, 12, 8))
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        self._tree = ttk.Treeview(
            list_frame,
            columns=("name", "package", "type"),
            show="headings",
            selectmode="browse",
        )
        self._tree.heading("name", text="Application")
        self._tree.heading("package", text="Package")
        self._tree.heading("type", text="Type")
        self._tree.column("name", width=220, minwidth=140)
        self._tree.column("package", width=360, minwidth=220)
        self._tree.column("type", width=70, minwidth=60, stretch=False)
        self._tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_selected)
        self._tree.bind("<Double-1>", self._choose_event)

        footer = ttk.Frame(self._dialog, padding=(12, 0, 12, 12))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self._status_var = tk.StringVar()
        ttk.Label(footer, textvariable=self._status_var).grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="Cancel", command=self._cancel).grid(row=0, column=2)
        self._select_button = ttk.Button(footer, text="Select", command=self._choose)
        self._select_button.grid(row=0, column=1, padx=(0, 8))

        self._populate("")
        self._center_over_parent()
        self._dialog.grab_set()
        self._search_entry.focus_set()
        self._dialog.wait_window()

    def _populate(self, query: str) -> None:
        self._tree.delete(*self._tree.get_children())
        self._app_by_item.clear()
        matches = _filter_device_apps(self._apps, query)
        for index, app in enumerate(matches):
            item = f"app-{index}"
            self._app_by_item[item] = app
            self._tree.insert(
                "",
                tk.END,
                iid=item,
                values=(app.name, app.package_name, "System" if app.is_system else "User"),
            )
        children = self._tree.get_children()
        if children:
            first = children[0]
            self._tree.selection_set(first)
            self._tree.focus(first)
            self._tree.see(first)
        self._status_var.set(
            f"{len(matches)} application{'s' if len(matches) != 1 else ''}"
            if matches
            else "No applications match this search"
        )
        self._update_select_button()

    def _on_search_changed(self, *_event) -> None:
        self._populate(self._search_var.get())

    def _on_tree_selected(self, _event=None) -> None:
        self._update_select_button()

    def _update_select_button(self) -> None:
        state = tk.NORMAL if self._tree.selection() else tk.DISABLED
        self._select_button.configure(state=state)

    def _focus_first_result(self, _event=None) -> str:
        children = self._tree.get_children()
        if children:
            first = children[0]
            self._tree.selection_set(first)
            self._tree.focus(first)
            self._tree.focus_set()
        return "break"

    def _choose_event(self, _event=None) -> str:
        self._choose()
        return "break"

    def _choose(self) -> None:
        selection = self._tree.selection()
        if not selection:
            return
        self.selected = self._app_by_item.get(selection[0])
        if self.selected is not None:
            self._close()

    def _cancel(self) -> None:
        self.selected = None
        self._close()

    def _close(self) -> None:
        if self._dialog.winfo_exists():
            self._dialog.grab_release()
            self._dialog.destroy()
        if self._parent.winfo_exists():
            self._parent.grab_set()

    def _center_over_parent(self) -> None:
        self._dialog.update_idletasks()
        width = max(self._dialog.winfo_reqwidth(), 720)
        height = max(self._dialog.winfo_reqheight(), 440)
        x = self._parent.winfo_rootx() + max((self._parent.winfo_width() - width) // 2, 0)
        y = self._parent.winfo_rooty() + max((self._parent.winfo_height() - height) // 2, 0)
        self._dialog.geometry(f"{width}x{height}+{x}+{y}")
