# scrcpy 4.1 application-list discovery

Milestone 5.41 established the parser contract for future device app selection.
Milestone 5.42 added the standalone process backend. Settings controls remain
deferred.

## Observed command

The verified bundled scrcpy 4.1 executable was run with an explicit device:

```text
scrcpy.exe --serial=<serial> --list-apps
```

Tests used authorized Android 14 and Android 15 devices from different vendors.
Both commands returned exit code `0`. Observed durations were approximately 3.6
and 5.6 seconds.

## Stream behavior

- stdout contains the scrcpy banner, device diagnostics, the
  `[server] INFO: List of apps:` header, and app records.
- stderr contains the ADB `scrcpy-server` push-progress line even on success.
- An invalid serial or ambiguous selection returns exit code `1`, prints only the
  banner to stdout, and reports the device-selection error on stderr.
- UTF-8 output preserves non-ASCII app labels, including non-breaking spaces.

The future backend must therefore use the exit code to determine success and
must not interpret nonempty stderr alone as failure.

## Record format

scrcpy sorts system apps first, followed by non-system apps, then by app name and
package. Each normal record has this shape:

```text
 * Settings                       com.android.settings
 - Example App                    com.example.app
```

`*` identifies a system app and `-` identifies a non-system app. The package is
the exact value accepted by `--start-app`.

scrcpy 4.1 wraps names longer than its 30-character display column:

```text
 - Application Name Longer Than Thirty Characters
                                com.example.long_application_name
```

Only enabled applications with a standard or Leanback launch intent appear in
the list. Duplicate friendly names are possible and must remain separate;
package name is the stable selection key.

## Parser policy

`src/device_apps.py`:

- requires the explicit list header;
- preserves Unicode labels and duplicate friendly names;
- records the system-app marker;
- supports normal and wrapped records;
- validates package-name shape conservatively;
- keeps the first occurrence of an exact duplicate package;
- rejects malformed records or unsupported format changes.

Sanitized fixtures are under `tests/fixtures`. They contain no real serials or
complete device app inventories.

## Milestone 5.42 backend

`discover_device_apps()` resolves the explicitly selected bundled or custom
scrcpy executable without mode fallback. It requires an explicit device serial,
runs `--list-apps` without a console, uses a 20-second default timeout, and
returns parsed `DeviceApp` records. Exit code determines success because normal
ADB push progress is written to stderr.

Process launch, timeout, device-selection, nonzero exit, and parser failures are
converted to `AppDiscoveryError`. Diagnostics avoid including a partial app
inventory, and normal logging records counts rather than application names.

## Milestone 5.43 application browser

Settings now retrieves applications on a daemon worker and transfers results to
the tkinter thread through a queue. Request generations discard results after a
device, session, scrcpy mode, or custom path change, and when Settings closes.

The modal application browser:

- searches friendly names and package names as the user types;
- sorts by friendly name and package while preserving duplicate names;
- displays system/user classification;
- supports mouse, Enter, double-click, arrow-key navigation, and Escape;
- returns a temporary preview selection only.

The selected package is shown as **Preview only** in Settings. It does not alter
the Start app field, arguments, sessions, or saved configuration in this
milestone.

## Milestone 5.44 session integration

Selecting an application now applies its package to the Start app field and the
session edit buffer. Existing `--start-app` occurrences are replaced and
deduplicated while unrelated arguments retain their order. A leading `+`
(scrcpy's force-stop modifier) is preserved; a leading `?` name-search modifier
is removed because the selected value is an exact package name. Selecting an app
does not save the configuration automatically.

Application lists are cached by scrcpy mode, resolved runtime path, and device
serial for the lifetime of the Settings process. **Select app…** opens a cached
list immediately. **Refresh apps** always queries the device; a successful result
replaces that cache entry, while a failed refresh retains the previous list.
Request generations and cache keys together prevent results from a previous
device, session, mode, or executable path from being applied to the current UI.

## Milestone 5.45 hardening

The complete edit lifecycle now has explicit automated coverage: application
selection changes only the current edit buffer, **Apply changes** updates only the
Settings process's in-memory configuration, **Save** persists the package, and
Cancel leaves the existing file unchanged. Reloaded session arguments are passed
to scrcpy without reordering or rewriting unrelated options. Switching sessions
reloads only the newly selected session's arguments.

Application discovery converts common failures into recovery guidance:

- unsupported `--list-apps` directs the user to bundled scrcpy 4.1 or a compatible
  newer custom version;
- unauthorized devices direct the user to accept Android's USB debugging prompt;
- offline or missing devices direct the user to reconnect and refresh devices;
- timeouts suggest reconnecting and trying **Refresh apps** again;
- unsupported output formats identify the custom-runtime compatibility problem.

Changing the custom scrcpy path invalidates pending discovery requests and the
previous device inventory. App selection remains disabled until device detection
is refreshed. Failed app refreshes retain the last successful cache entry, and
neither discovery errors nor stale results alter the session edit buffer.
