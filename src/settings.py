# SPDX-License-Identifier: GPL-3.0-only

"""Modal settings dialog for managing scrcpy sessions."""

from __future__ import annotations

import logging
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .autostart import (
    AutostartError,
    AutostartManager,
    AutostartStatus,
    AutostartUnavailableError,
    create_autostart_manager,
)
from .config import (
    SCRCPY_MODE_BUNDLED,
    SCRCPY_MODE_CUSTOM,
    Config,
    ConfigError,
)
from .device_apps import AppDiscoveryError, DeviceApp, discover_device_apps
from .devices import Device, DeviceDiscoveryError, detect_devices
from .scrcpy_runtime import (
    BUNDLED_SCRCPY_VERSION,
    ScrcpyResolutionError,
    bundled_scrcpy_path,
    resolve_scrcpy,
)
from .scrcpy_options import get_value, has_flag, set_flag, set_value
from .session_transfer import (
    SessionTransferError,
    export_session_backup,
    load_session_backup,
)

logger = logging.getLogger(__name__)

IMPORT_MODE_MERGE = "merge"
IMPORT_MODE_REPLACE = "replace"


def _detect_devices_for_selection(mode: str, custom_path: str) -> list[Device]:
    resolution = resolve_scrcpy(mode, custom_path)
    return detect_devices(
        str(resolution.path),
        allow_path_fallback=mode == SCRCPY_MODE_CUSTOM,
    )


def _connected_serial_for_selection(
    label: str,
    device_by_label: dict[str, str],
    devices: list[Device],
) -> str:
    """Return a serial only when the selected label is currently connected."""
    serial = device_by_label.get(label, "")
    if not serial:
        return ""
    return serial if any(device.serial == serial and device.state == "device" for device in devices) else ""


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


def _is_current_app_result(
    request: int,
    current_request: int,
    result_key: tuple[str, str, str],
    current_key: tuple[str, str, str] | None,
) -> bool:
    return request == current_request and result_key == current_key


def _app_cache_key(mode: str, custom_path: str, serial: str) -> tuple[str, str, str]:
    """Return a stable per-runtime, per-device application cache key."""
    if mode == SCRCPY_MODE_BUNDLED:
        runtime_path = str(bundled_scrcpy_path())
    else:
        runtime_path = os.path.abspath(os.path.expanduser(custom_path.strip()))
    return mode, os.path.normcase(runtime_path), serial


def _selected_start_app_value(current_value: str, package_name: str) -> str:
    """Apply a package while retaining scrcpy's optional force-stop prefix."""
    force_stop = current_value.strip().startswith("+")
    return f"+{package_name}" if force_stop else package_name


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


class _SettingsDialog:
    """Modal tkinter dialog for editing scrcpy-launcher configuration."""

    def __init__(self, parent, config: Config) -> None:
        self._parent = parent
        self._config = config
        self._syncing_controls = False
        self._args_sync_job: str | None = None
        self._device_request = 0
        self._device_loading = False
        self._detected_devices: list[Device] = []
        self._device_by_label: dict[str, str] = {}
        self._device_results: queue.Queue[tuple[int, list[Device] | None, str]] = queue.Queue()
        self._app_request = 0
        self._app_loading = False
        self._app_cache: dict[tuple[str, str, str], list[DeviceApp]] = {}
        self._app_results: queue.Queue[
            tuple[int, tuple[str, str, str], list[DeviceApp] | None, str, bool]
        ] = queue.Queue()
        self._autostart_manager: AutostartManager | None = None
        self._autostart_initial = False
        self._autostart_needs_repair = False
        self._autostart_status_text = ""
        try:
            manager = create_autostart_manager(config.config_path)
            state = manager.state()
            self._autostart_manager = manager
            self._autostart_initial = state.status is not AutostartStatus.DISABLED
            if state.status is AutostartStatus.ENABLED:
                self._autostart_status_text = "Enabled for this Windows account"
            elif state.status is AutostartStatus.STALE:
                self._autostart_needs_repair = True
                self._autostart_status_text = (
                    "Existing registration is stale; Save to repair it or clear this option"
                )
            else:
                self._autostart_status_text = "Disabled for this Windows account"
        except AutostartUnavailableError as exc:
            self._autostart_status_text = str(exc)
        except AutostartError as exc:
            logger.warning("Could not inspect autostart registration: %s", exc)
            self._autostart_status_text = str(exc)

        self._dialog = tk.Toplevel(parent)
        self._dialog.title("scrcpy-launcher Settings")
        self._dialog.minsize(820, 660)
        self._dialog.grab_set()
        self._dialog.protocol("WM_DELETE_WINDOW", self._cancel)
        self._dialog.bind("<Escape>", lambda _event: self._cancel())
        self._dialog.bind("<Control-s>", lambda _event: self._save())
        self._dialog.bind("<Alt-Up>", self._move_up_shortcut)
        self._dialog.bind("<Alt-Down>", self._move_down_shortcut)

        self._build_ui()
        self._path_var.trace_add("write", self._on_scrcpy_path_changed)
        self._load_state()
        self._center_dialog()
        self._refresh_devices()
        self._poll_device_results()
        self._poll_app_results()

        self._dialog.wait_window()

    def _build_ui(self) -> None:
        self._dialog.rowconfigure(0, weight=1)
        self._dialog.columnconfigure(0, weight=1)

        outer = ttk.Frame(self._dialog, padding=12)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.rowconfigure(2, weight=1)
        outer.columnconfigure(1, weight=1)

        path_frame = ttk.LabelFrame(outer, text="scrcpy executable", padding=10)
        path_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        path_frame.columnconfigure(1, weight=1)
        self._mode_var = tk.StringVar(value=SCRCPY_MODE_BUNDLED)
        ttk.Radiobutton(
            path_frame,
            text=f"Use bundled scrcpy {BUNDLED_SCRCPY_VERSION} (recommended)",
            variable=self._mode_var,
            value=SCRCPY_MODE_BUNDLED,
            command=self._on_scrcpy_mode_changed,
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        self._bundled_status_var = tk.StringVar()
        ttk.Label(path_frame, textvariable=self._bundled_status_var).grid(
            row=1, column=1, columnspan=2, sticky="w", pady=(2, 6)
        )
        ttk.Radiobutton(
            path_frame,
            text="Use a custom scrcpy executable",
            variable=self._mode_var,
            value=SCRCPY_MODE_CUSTOM,
            command=self._on_scrcpy_mode_changed,
        ).grid(row=2, column=0, columnspan=3, sticky="w")
        self._path_var = tk.StringVar()
        self._path_entry = ttk.Entry(path_frame, textvariable=self._path_var)
        self._path_entry.grid(row=3, column=1, sticky="ew", padx=(0, 8), pady=(4, 0))
        self._browse_button = ttk.Button(path_frame, text="Browse…", command=self._browse_path)
        self._browse_button.grid(row=3, column=2, pady=(4, 0))

        windows_frame = ttk.LabelFrame(outer, text="Windows", padding=10)
        windows_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self._autostart_var = tk.BooleanVar(value=self._autostart_initial)
        self._autostart_check = ttk.Checkbutton(
            windows_frame,
            text="Start scrcpy-launcher when I sign in",
            variable=self._autostart_var,
        )
        self._autostart_check.grid(row=0, column=0, sticky="w")
        if self._autostart_manager is None:
            self._autostart_check.configure(state=tk.DISABLED)
        ttk.Label(windows_frame, text=self._autostart_status_text).grid(
            row=1, column=0, sticky="w", pady=(2, 0)
        )

        list_frame = ttk.LabelFrame(outer, text="Sessions", padding=10)
        list_frame.grid(row=2, column=0, sticky="nsew", padx=(0, 10))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        self._listbox = tk.Listbox(
            list_frame,
            height=14,
            width=26,
            selectmode=tk.SINGLE,
            exportselection=False,
        )
        self._listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._listbox.config(yscrollcommand=scrollbar.set)
        self._listbox.bind("<<ListboxSelect>>", self._on_select)

        list_buttons = ttk.Frame(list_frame)
        list_buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(list_buttons, text="New", command=self._new_session).pack(side=tk.LEFT)
        ttk.Button(list_buttons, text="Duplicate", command=self._duplicate_session).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(list_buttons, text="Remove", command=self._remove_session).pack(side=tk.RIGHT)

        order_buttons = ttk.Frame(list_frame)
        order_buttons.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        order_buttons.columnconfigure((0, 1), weight=1)
        self._move_up_button = ttk.Button(
            order_buttons,
            text="Move up",
            command=lambda: self._move_selected(-1),
        )
        self._move_up_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self._move_down_button = ttk.Button(
            order_buttons,
            text="Move down",
            command=lambda: self._move_selected(1),
        )
        self._move_down_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        transfer_buttons = ttk.Frame(list_frame)
        transfer_buttons.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        transfer_buttons.columnconfigure((0, 1), weight=1)
        ttk.Button(
            transfer_buttons,
            text="Import…",
            command=self._import_sessions,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(
            transfer_buttons,
            text="Export…",
            command=self._export_sessions,
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        edit_frame = ttk.LabelFrame(outer, text="Session details", padding=10)
        edit_frame.grid(row=2, column=1, sticky="nsew")
        edit_frame.rowconfigure(5, weight=1)
        edit_frame.columnconfigure(0, weight=1)

        ttk.Label(edit_frame, text="Name").grid(row=0, column=0, sticky="w")
        self._name_var = tk.StringVar()
        self._name_entry = ttk.Entry(edit_frame, textvariable=self._name_var)
        self._name_entry.grid(row=1, column=0, sticky="ew", pady=(2, 10))

        quick_frame = ttk.LabelFrame(edit_frame, text="Quick options", padding=8)
        quick_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        quick_frame.columnconfigure(1, weight=1)

        ttk.Label(quick_frame, text="Device").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._device_var = tk.StringVar(value="Automatic")
        self._device_combo = ttk.Combobox(
            quick_frame,
            textvariable=self._device_var,
            values=("Automatic",),
            state="readonly",
        )
        self._device_combo.grid(row=0, column=1, sticky="ew")
        self._device_combo.bind("<<ComboboxSelected>>", self._on_device_selected)
        self._refresh_button = ttk.Button(
            quick_frame,
            text="Refresh",
            command=self._refresh_devices,
        )
        self._refresh_button.grid(row=0, column=2, padx=(8, 0))

        self._device_status_var = tk.StringVar(value="Devices not checked")
        ttk.Label(quick_frame, textvariable=self._device_status_var).grid(
            row=1, column=1, columnspan=2, sticky="w", pady=(2, 8)
        )

        ttk.Label(quick_frame, text="Window title").grid(
            row=2, column=0, sticky="w", padx=(0, 8), pady=2
        )
        self._window_title_var = tk.StringVar()
        window_title_entry = ttk.Entry(quick_frame, textvariable=self._window_title_var)
        window_title_entry.grid(row=2, column=1, columnspan=2, sticky="ew", pady=2)
        self._window_title_var.trace_add("write", self._on_quick_options_changed)

        ttk.Label(quick_frame, text="Start app").grid(
            row=3, column=0, sticky="w", padx=(0, 8), pady=2
        )
        self._start_app_var = tk.StringVar()
        start_app_entry = ttk.Entry(quick_frame, textvariable=self._start_app_var)
        start_app_entry.grid(row=3, column=1, sticky="ew", pady=2)
        self._start_app_var.trace_add("write", self._on_quick_options_changed)
        self._select_app_button = ttk.Button(
            quick_frame,
            text="Select app…",
            command=self._select_device_app,
            state=tk.DISABLED,
        )
        self._select_app_button.grid(row=3, column=2, padx=(8, 0), pady=2)

        self._refresh_apps_button = ttk.Button(
            quick_frame,
            text="Refresh apps",
            command=self._refresh_device_apps,
            state=tk.DISABLED,
        )
        self._refresh_apps_button.grid(row=4, column=2, padx=(8, 0), pady=(0, 4))

        self._app_status_var = tk.StringVar(
            value="Select a connected device to browse applications"
        )
        ttk.Label(
            quick_frame,
            textvariable=self._app_status_var,
            wraplength=390,
            justify=tk.LEFT,
        ).grid(
            row=4, column=1, sticky="w", pady=(0, 4)
        )

        flags_frame = ttk.Frame(quick_frame)
        flags_frame.grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self._turn_screen_off_var = tk.BooleanVar()
        self._no_audio_var = tk.BooleanVar()
        self._new_display_var = tk.BooleanVar()
        ttk.Checkbutton(
            flags_frame,
            text="Turn screen off",
            variable=self._turn_screen_off_var,
            command=self._on_quick_options_changed,
        ).pack(side=tk.LEFT)
        ttk.Checkbutton(
            flags_frame,
            text="No audio",
            variable=self._no_audio_var,
            command=self._on_quick_options_changed,
        ).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Checkbutton(
            flags_frame,
            text="New display",
            variable=self._new_display_var,
            command=self._on_quick_options_changed,
        ).pack(side=tk.LEFT, padx=(12, 0))

        ttk.Label(edit_frame, text="Arguments (one per line)").grid(row=4, column=0, sticky="w")

        args_frame = ttk.Frame(edit_frame)
        args_frame.grid(row=5, column=0, sticky="nsew", pady=(2, 10))
        args_frame.rowconfigure(0, weight=1)
        args_frame.columnconfigure(0, weight=1)
        self._args_text = tk.Text(args_frame, height=12, width=48, wrap=tk.NONE, undo=True)
        self._args_text.grid(row=0, column=0, sticky="nsew")
        self._args_text.bind("<<Modified>>", self._on_args_modified)
        args_scrollbar = ttk.Scrollbar(args_frame, orient=tk.VERTICAL, command=self._args_text.yview)
        args_scrollbar.grid(row=0, column=1, sticky="ns")
        self._args_text.config(yscrollcommand=args_scrollbar.set)

        edit_buttons = ttk.Frame(edit_frame)
        edit_buttons.grid(row=6, column=0, sticky="e")
        ttk.Button(edit_buttons, text="Add session", command=self._add_session).pack(side=tk.LEFT)
        ttk.Button(edit_buttons, text="Apply changes", command=self._update_session).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        footer = ttk.Frame(outer)
        footer.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Label(footer, text="Ctrl+S to save  •  Esc to cancel").pack(side=tk.LEFT)
        ttk.Button(footer, text="Cancel", command=self._cancel).pack(side=tk.RIGHT)
        ttk.Button(footer, text="Save", command=self._save).pack(side=tk.RIGHT, padx=(0, 8))

    def _center_dialog(self) -> None:
        self._dialog.update_idletasks()
        width = max(self._dialog.winfo_reqwidth(), 820)
        height = max(self._dialog.winfo_reqheight(), 660)
        x = max((self._dialog.winfo_screenwidth() - width) // 2, 0)
        y = max((self._dialog.winfo_screenheight() - height) // 2, 0)
        self._dialog.geometry(f"{width}x{height}+{x}+{y}")

    def _load_state(self) -> None:
        self._mode_var.set(self._config.scrcpy_mode)
        self._path_var.set(self._config.scrcpy_path)
        self._update_scrcpy_controls()
        for session in self._config.sessions:
            self._listbox.insert(tk.END, session.name)
        if self._config.sessions:
            self._listbox.selection_set(0)
            self._on_select()

    def _browse_path(self) -> None:
        path = filedialog.askopenfilename(
            parent=self._dialog,
            title="Select scrcpy.exe",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
        )
        if path:
            self._mode_var.set(SCRCPY_MODE_CUSTOM)
            self._path_var.set(path)
            self._update_scrcpy_controls()
            self._refresh_devices()

    def _on_scrcpy_path_changed(self, *_event) -> None:
        self._device_request += 1
        self._device_loading = False
        self._detected_devices = []
        self._invalidate_app_discovery()
        was_syncing = self._syncing_controls
        self._syncing_controls = True
        self._apply_device_choices()
        self._syncing_controls = was_syncing
        self._device_status_var.set("scrcpy path changed — refresh devices")
        self._refresh_button.configure(state=tk.NORMAL)

    def _update_scrcpy_controls(self) -> None:
        custom = self._mode_var.get() == SCRCPY_MODE_CUSTOM
        state = tk.NORMAL if custom else tk.DISABLED
        self._path_entry.configure(state=state)
        self._browse_button.configure(state=state)
        path = bundled_scrcpy_path()
        status = f"Bundled location: {path}"
        if not path.is_file():
            status += " (missing — repair or reinstall)"
        self._bundled_status_var.set(status)

    def _on_scrcpy_mode_changed(self) -> None:
        self._device_request += 1
        self._invalidate_app_discovery()
        self._detected_devices = []
        self._update_scrcpy_controls()
        self._syncing_controls = True
        self._apply_device_choices()
        self._syncing_controls = False
        self._device_status_var.set("Devices not checked")
        self._refresh_devices()

    def _on_select(self, event=None) -> None:
        sel = self._listbox.curselection()
        if not sel:
            self._update_move_buttons()
            return
        self._invalidate_app_discovery()
        idx = sel[0]
        session = self._config.sessions[idx]
        self._name_var.set(session.name)
        self._write_args(session.args)
        self._update_move_buttons()

    def _write_args(self, args: list[str] | tuple[str, ...]) -> None:
        self._syncing_controls = True
        self._args_text.delete(1.0, tk.END)
        self._args_text.insert(1.0, "\n".join(args))
        self._args_text.edit_modified(False)
        self._syncing_controls = False
        self._sync_controls_from_args()

    def _get_args(self) -> list[str]:
        text = self._args_text.get(1.0, tk.END).strip()
        if not text:
            return []
        return [line.strip() for line in text.splitlines() if line.strip()]

    def _on_args_modified(self, _event=None) -> None:
        self._args_text.edit_modified(False)
        if self._syncing_controls:
            return
        if self._args_sync_job is not None:
            self._dialog.after_cancel(self._args_sync_job)
        self._args_sync_job = self._dialog.after(120, self._sync_controls_from_args)

    def _sync_controls_from_args(self) -> None:
        self._args_sync_job = None
        args = self._get_args()
        self._syncing_controls = True
        self._window_title_var.set(get_value(args, "--window-title"))
        self._start_app_var.set(get_value(args, "--start-app"))
        self._turn_screen_off_var.set(has_flag(args, "--turn-screen-off"))
        self._no_audio_var.set(has_flag(args, "--no-audio"))
        self._new_display_var.set(has_flag(args, "--new-display", allow_value=True))
        self._apply_device_choices()
        self._syncing_controls = False

    def _on_quick_options_changed(self, *_event) -> None:
        if self._syncing_controls:
            return
        args = self._get_args()
        args = set_value(args, "--window-title", self._window_title_var.get())
        args = set_value(args, "--start-app", self._start_app_var.get())
        args = set_flag(args, "--turn-screen-off", self._turn_screen_off_var.get())
        args = set_flag(args, "--no-audio", self._no_audio_var.get())
        args = set_flag(
            args,
            "--new-display",
            self._new_display_var.get(),
            allow_value=True,
        )
        self._write_args(args)

    def _on_device_selected(self, _event=None) -> None:
        if self._syncing_controls:
            return
        self._invalidate_app_discovery()
        serial = self._device_by_label.get(self._device_var.get(), "")
        self._write_args(set_value(self._get_args(), "--serial", serial))

    def _apply_device_choices(self) -> None:
        previous_serial = _connected_serial_for_selection(
            self._device_var.get(), self._device_by_label, self._detected_devices
        )
        current_serial = get_value(self._get_args(), "--serial")
        values = ["Automatic"]
        device_by_label: dict[str, str] = {"Automatic": ""}
        selected_label = "Automatic"

        for device in self._detected_devices:
            if device.state != "device":
                continue
            values.append(device.label)
            device_by_label[device.label] = device.serial
            if device.serial == current_serial:
                selected_label = device.label

        if current_serial and selected_label == "Automatic":
            selected_label = f"Configured: {current_serial} — not connected"
            values.append(selected_label)
            device_by_label[selected_label] = current_serial

        self._device_by_label = device_by_label
        self._device_combo.configure(values=values)
        self._device_var.set(selected_label)
        current_connected_serial = _connected_serial_for_selection(
            selected_label, self._device_by_label, self._detected_devices
        )
        if current_connected_serial != previous_serial:
            self._invalidate_app_discovery()
        else:
            self._app_status_var.set(self._default_app_status())
            self._update_app_button_state()

    def _refresh_devices(self) -> None:
        self._device_request += 1
        self._device_loading = True
        self._invalidate_app_discovery()
        request = self._device_request
        mode = self._mode_var.get()
        custom_path = self._path_var.get().strip()
        self._refresh_button.configure(state=tk.DISABLED)
        self._device_status_var.set("Detecting devices…")

        def worker() -> None:
            try:
                devices = _detect_devices_for_selection(mode, custom_path)
                self._device_results.put((request, devices, ""))
            except (DeviceDiscoveryError, ScrcpyResolutionError) as exc:
                self._device_results.put((request, None, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_device_results(self) -> None:
        try:
            while True:
                request, devices, error = self._device_results.get_nowait()
                if request != self._device_request:
                    continue
                self._device_loading = False
                self._refresh_button.configure(state=tk.NORMAL)
                if error:
                    self._detected_devices = []
                    self._device_status_var.set(error)
                    logger.warning("Device detection failed: %s", error)
                else:
                    self._detected_devices = devices or []
                    self._device_status_var.set(self._device_status_text(self._detected_devices))
                self._syncing_controls = True
                self._apply_device_choices()
                self._syncing_controls = False
        except queue.Empty:
            pass
        if self._dialog.winfo_exists():
            self._dialog.after(100, self._poll_device_results)

    def _selected_connected_serial(self) -> str:
        return _connected_serial_for_selection(
            self._device_var.get(), self._device_by_label, self._detected_devices
        )

    def _default_app_status(self) -> str:
        key = self._current_app_cache_key()
        if key is not None and key in self._app_cache:
            count = len(self._app_cache[key])
            return f"{count} application{'s' if count != 1 else ''} cached for this device"
        if key is not None:
            return "Select app to load applications from this device"
        return "Select a connected device to browse applications"

    def _current_app_cache_key(self) -> tuple[str, str, str] | None:
        serial = self._selected_connected_serial()
        if not serial:
            return None
        return _app_cache_key(
            self._mode_var.get(),
            self._path_var.get().strip(),
            serial,
        )

    def _invalidate_app_discovery(self) -> None:
        self._app_request += 1
        self._app_loading = False
        self._app_status_var.set(self._default_app_status())
        self._update_app_button_state()

    def _update_app_button_state(self) -> None:
        enabled = (
            bool(self._selected_connected_serial())
            and not self._device_loading
            and not self._app_loading
        )
        state = tk.NORMAL if enabled else tk.DISABLED
        self._select_app_button.configure(state=state)
        self._refresh_apps_button.configure(state=state)

    def _select_device_app(self) -> None:
        key = self._current_app_cache_key()
        if key is None:
            messagebox.showwarning(
                "Select a Device",
                "Select a connected Android device before browsing applications.",
                parent=self._dialog,
            )
            self._update_app_button_state()
            return

        if key in self._app_cache:
            self._open_app_chooser(self._app_cache[key])
            return

        self._load_device_apps(key, open_after_load=True)

    def _refresh_device_apps(self) -> None:
        key = self._current_app_cache_key()
        if key is None:
            self._update_app_button_state()
            return
        self._load_device_apps(key, open_after_load=False)

    def _load_device_apps(
        self,
        key: tuple[str, str, str],
        *,
        open_after_load: bool,
    ) -> None:
        mode = self._mode_var.get()
        custom_path = self._path_var.get().strip()
        serial = key[2]

        self._app_request += 1
        request = self._app_request
        self._app_loading = True
        self._app_status_var.set(
            "Loading applications…" if open_after_load else "Refreshing applications…"
        )
        self._update_app_button_state()

        def worker() -> None:
            try:
                apps = discover_device_apps(mode, custom_path, serial)
                self._app_results.put((request, key, apps, "", open_after_load))
            except AppDiscoveryError as exc:
                self._app_results.put((request, key, None, str(exc), open_after_load))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_app_results(self) -> None:
        try:
            while True:
                request, key, apps, error, open_after_load = self._app_results.get_nowait()
                if not _is_current_app_result(
                    request,
                    self._app_request,
                    key,
                    self._current_app_cache_key(),
                ):
                    continue
                self._app_loading = False
                self._update_app_button_state()
                if error:
                    retained = key in self._app_cache
                    self._app_status_var.set(
                        "Refresh failed; previous application list retained"
                        if retained
                        else "Could not load applications"
                    )
                    logger.warning("Application discovery failed: %s", error)
                    messagebox.showerror(
                        "Application Discovery Failed",
                        error,
                        parent=self._dialog,
                    )
                    continue
                self._app_cache[key] = apps or []
                if not apps:
                    self._app_status_var.set("No launchable applications found")
                    messagebox.showinfo(
                        "No Applications",
                        "No launchable applications were reported for this device.",
                        parent=self._dialog,
                    )
                    continue
                if open_after_load:
                    self._open_app_chooser(apps)
                else:
                    count = len(apps)
                    self._app_status_var.set(
                        f"Refreshed {count} application{'s' if count != 1 else ''}"
                    )
        except queue.Empty:
            pass
        if self._dialog.winfo_exists():
            self._dialog.after(100, self._poll_app_results)

    def _open_app_chooser(self, apps: list[DeviceApp]) -> None:
        if not apps:
            self._app_status_var.set("No launchable applications found")
            messagebox.showinfo(
                "No Applications",
                "No launchable applications were reported for this device.",
                parent=self._dialog,
            )
            return
        chooser = _AppSelectionDialog(self._dialog, apps)
        if chooser.selected is None:
            self._app_status_var.set(self._default_app_status())
            return
        value = _selected_start_app_value(
            self._start_app_var.get(),
            chooser.selected.package_name,
        )
        self._start_app_var.set(value)
        app_type = "system" if chooser.selected.is_system else "user"
        self._app_status_var.set(
            f"Selected {chooser.selected.name} — {chooser.selected.package_name} ({app_type})"
        )

    @staticmethod
    def _device_status_text(devices: list[Device]) -> str:
        counts: dict[str, int] = {}
        for device in devices:
            counts[device.state] = counts.get(device.state, 0) + 1
        connected = counts.pop("device", 0)
        parts = [f"{connected} connected" if connected else "No connected devices"]
        parts.extend(f"{count} {state}" for state, count in sorted(counts.items()))
        return " • ".join(parts)

    def _new_session(self) -> None:
        self._listbox.selection_clear(0, tk.END)
        self._clear_edit_fields()
        self._update_move_buttons()
        self._name_entry.focus_set()

    def _duplicate_session(self) -> None:
        sel = self._listbox.curselection()
        if not sel:
            messagebox.showwarning(
                "No Session Selected",
                "Select a session to duplicate.",
                parent=self._dialog,
            )
            return
        try:
            duplicate_index = self._config.duplicate_session(sel[0])
        except ConfigError as exc:
            messagebox.showerror("Duplicate failed", str(exc), parent=self._dialog)
            return

        duplicate = self._config.sessions[duplicate_index]
        self._listbox.insert(duplicate_index, duplicate.name)
        self._listbox.selection_clear(0, tk.END)
        self._listbox.selection_set(duplicate_index)
        self._listbox.see(duplicate_index)
        self._on_select()
        self._name_entry.focus_set()
        self._name_entry.selection_range(0, tk.END)

    def _add_session(self) -> None:
        name = self._name_var.get().strip()
        args = self._get_args()
        if not name:
            messagebox.showwarning("Invalid", "Session name cannot be empty.", parent=self._dialog)
            return
        try:
            self._config.add_session(name, args)
            self._listbox.insert(tk.END, name)
            idx = self._listbox.size() - 1
            self._listbox.selection_set(idx)
            self._listbox.see(idx)
            self._update_move_buttons()
        except ConfigError as exc:
            messagebox.showerror("Error", str(exc), parent=self._dialog)

    def _update_session(self) -> bool:
        sel = self._listbox.curselection()
        if not sel:
            messagebox.showwarning("Invalid", "Select a session to update.", parent=self._dialog)
            return False
        idx = sel[0]
        name = self._name_var.get().strip()
        args = self._get_args()
        if not name:
            messagebox.showwarning("Invalid", "Session name cannot be empty.", parent=self._dialog)
            return False
        try:
            self._config.update_session(idx, name, args)
            self._listbox.delete(idx)
            self._listbox.insert(idx, name)
            self._listbox.selection_set(idx)
            self._listbox.see(idx)
            self._update_move_buttons()
        except ConfigError as exc:
            messagebox.showerror("Error", str(exc), parent=self._dialog)
            return False
        return True

    def _remove_session(self) -> None:
        sel = self._listbox.curselection()
        if not sel:
            messagebox.showwarning("Invalid", "Select a session to remove.", parent=self._dialog)
            return
        idx = sel[0]
        name = self._config.sessions[idx].name
        if messagebox.askyesno("Confirm", f"Remove session '{name}'?", parent=self._dialog):
            self._config.remove_session(idx)
            self._listbox.delete(idx)
            if self._listbox.size():
                next_idx = min(idx, self._listbox.size() - 1)
                self._listbox.selection_set(next_idx)
                self._on_select()
            else:
                self._clear_edit_fields()
            self._update_move_buttons()

    def _move_selected(self, offset: int) -> None:
        sel = self._listbox.curselection()
        if not sel:
            return
        index = sel[0]
        target = index + offset
        if target < 0 or target >= self._listbox.size():
            self._update_move_buttons()
            return

        if not self._update_session():
            return
        try:
            new_index = self._config.move_session(index, target)
        except ConfigError as exc:
            messagebox.showerror("Move failed", str(exc), parent=self._dialog)
            return

        name = self._listbox.get(index)
        self._listbox.delete(index)
        self._listbox.insert(new_index, name)
        self._listbox.selection_clear(0, tk.END)
        self._listbox.selection_set(new_index)
        self._listbox.see(new_index)
        self._on_select()

    def _move_up_shortcut(self, _event=None) -> str:
        self._move_selected(-1)
        return "break"

    def _move_down_shortcut(self, _event=None) -> str:
        self._move_selected(1)
        return "break"

    def _update_move_buttons(self) -> None:
        sel = self._listbox.curselection()
        index = sel[0] if sel else -1
        last_index = self._listbox.size() - 1
        self._move_up_button.configure(state=tk.NORMAL if index > 0 else tk.DISABLED)
        self._move_down_button.configure(
            state=tk.NORMAL if 0 <= index < last_index else tk.DISABLED
        )

    def _prepare_session_transfer(self) -> bool:
        if self._listbox.curselection():
            return self._update_session()
        if self._name_var.get().strip() or self._get_args():
            messagebox.showwarning(
                "Session not added",
                "Add the session before importing or exporting.",
                parent=self._dialog,
            )
            return False
        return True

    def _reload_session_list(self, selected_index: int | None = None) -> None:
        self._listbox.delete(0, tk.END)
        for session in self._config.sessions:
            self._listbox.insert(tk.END, session.name)
        if self._config.sessions and selected_index is not None:
            index = min(max(selected_index, 0), len(self._config.sessions) - 1)
            self._listbox.selection_set(index)
            self._listbox.see(index)
            self._on_select()
        else:
            self._clear_edit_fields()
            self._update_move_buttons()

    def _import_sessions(self) -> None:
        if not self._prepare_session_transfer():
            return
        path = filedialog.askopenfilename(
            parent=self._dialog,
            title="Import sessions",
            filetypes=[("scrcpy-launcher sessions", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            imported = load_session_backup(path)
        except SessionTransferError as exc:
            messagebox.showerror("Import failed", str(exc), parent=self._dialog)
            return

        current_count = len(self._config.sessions)
        selection = self._listbox.curselection()
        previous_index = selection[0] if selection else None
        mode = _choose_import_mode(self._dialog, current_count, len(imported))
        if mode is None:
            return
        try:
            if mode == IMPORT_MODE_REPLACE:
                self._config.replace_sessions(imported)
                renamed: tuple[tuple[str, str], ...] = ()
                selected_index = 0 if imported else None
            else:
                result = self._config.merge_sessions(imported)
                renamed = result.renamed
                selected_index = current_count if imported else (
                    previous_index if previous_index is not None else (
                        0 if self._config.sessions else None
                    )
                )
        except ConfigError as exc:
            logger.exception("Could not apply imported sessions")
            messagebox.showerror("Import failed", str(exc), parent=self._dialog)
            return

        self._reload_session_list(selected_index)
        messagebox.showinfo(
            "Sessions imported",
            _import_summary_text(mode, len(imported), current_count, renamed),
            parent=self._dialog,
        )

    def _export_sessions(self) -> None:
        if not self._prepare_session_transfer():
            return
        path = filedialog.asksaveasfilename(
            parent=self._dialog,
            title="Export sessions",
            initialfile="scrcpy-launcher-sessions.json",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            export_session_backup(path, self._config.sessions)
        except SessionTransferError as exc:
            logger.exception("Could not export sessions")
            messagebox.showerror("Export failed", str(exc), parent=self._dialog)
            return
        count = len(self._config.sessions)
        messagebox.showinfo(
            "Sessions exported",
            f"Exported {count} session{'s' if count != 1 else ''} to:\n{path}",
            parent=self._dialog,
        )

    def _clear_edit_fields(self) -> None:
        self._name_var.set("")
        self._write_args([])

    def _save(self) -> None:
        new_mode = self._mode_var.get()
        new_path = self._path_var.get().strip()
        if not new_path:
            messagebox.showerror(
                "Invalid Path",
                "Choose a scrcpy executable before saving.",
                parent=self._dialog,
            )
            self._path_entry.focus_set()
            return
        try:
            resolve_scrcpy(new_mode, new_path)
        except ScrcpyResolutionError as exc:
            if new_mode == SCRCPY_MODE_BUNDLED:
                messagebox.showerror("Bundled scrcpy missing", str(exc), parent=self._dialog)
                return
            if not messagebox.askyesno(
                "Confirm scrcpy Path",
                f"{exc}\n\nSave this custom path anyway?",
                parent=self._dialog,
            ):
                self._path_entry.focus_set()
                return
        if self._listbox.curselection() and not self._update_session():
            return
        if not self._listbox.curselection() and (
            self._name_var.get().strip() or self._get_args()
        ):
            messagebox.showwarning(
                "Session Not Added",
                "The session details have not been added. Click 'Add session' first.",
                parent=self._dialog,
            )
            return
        try:
            self._config.set_scrcpy_mode(new_mode)
            self._config.set_scrcpy_path(new_path)
            self._config.save()
        except (ConfigError, OSError) as exc:
            logger.exception("Could not save configuration")
            messagebox.showerror("Save failed", str(exc), parent=self._dialog)
            return
        if (
            self._autostart_manager is not None
            and (
                self._autostart_var.get() != self._autostart_initial
                or (self._autostart_needs_repair and self._autostart_var.get())
            )
        ):
            try:
                self._autostart_manager.apply(self._autostart_var.get())
            except AutostartError as exc:
                logger.exception("Configuration saved but autostart could not be changed")
                messagebox.showerror(
                    "Autostart change failed",
                    "The configuration was saved, but Windows autostart could not be "
                    f"changed:\n\n{exc}",
                    parent=self._dialog,
                )
                return
        self._destroy_dialog()

    def _cancel(self) -> None:
        self._destroy_dialog()

    def _destroy_dialog(self) -> None:
        self._device_request += 1
        self._app_request += 1
        self._app_loading = False
        self._dialog.destroy()


def show_settings(config_path: str) -> None:
    """Open the settings dialog modally. Saves config if the user clicked Save."""
    root = tk.Tk()
    root.withdraw()
    config = Config(config_path)
    _SettingsDialog(root, config)
    root.destroy()
