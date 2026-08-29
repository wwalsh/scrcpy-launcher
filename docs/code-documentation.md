# Code documentation standard

This project treats documentation as part of the public interface. Good
documentation should let a contributor understand a function's contract before
they trace every implementation detail.

## Python API rules

Every public module, class, function, method, and property should have a
concise docstring. Public callables should describe:

- inputs and important normalization rules;
- return values and state changes;
- exceptions callers should handle;
- filesystem, registry, subprocess, thread, dialog, or network side effects.

Docstrings use the Google-style structure already used by the project. Private
helpers need docstrings when they encode security, platform, concurrency, or
process-lifecycle behavior. Comments should explain why a choice is required,
not repeat the statement below the comment.

## Important design boundaries

The following behavior must remain documented near its implementation:

- only scrcpy processes launched by this application may be stopped by the
  session shutdown action;
- stopping ADB is a system-wide operation and can interrupt other Android
  tools, so the tray requires confirmation;
- scrcpy failures are reported during startup but expected post-window
  disconnections are logged without a dialog;
- configuration writes are validated and atomic, with recovery backups kept;
- bundled runtime files are verified before use;
- update checks are user-initiated and do not download or execute releases.
- external Android-tool commands use the shared hidden-process helper; callers
  retain ownership of timeout, exit-code, and user-facing error interpretation.
- Settings device and application discovery runs in single-worker executors;
  request generations discard stale results, and queued work is cancelled when
  a newer request or dialog shutdown supersedes it.
- the tray reloads configuration when its menu opens, but reuses the resolved
  scrcpy path for all decisions made while building that menu.
- bundled validation inventories and hashes expected files in one directory
  walk; configuration backups are copied through an independently validated
  temporary file before replacement.
- each launcher-owned scrcpy session has a blocking exit monitor and an
  independent bounded startup-window watcher; this separation keeps startup
  diagnostics responsive without adding a shared polling coordinator.

## Settings dialog concurrency

The Settings dialog keeps Tkinter work on its UI thread. Device and application
discovery may invoke ADB or scrcpy and therefore run in separate, single-worker
executors. A request generation identifies the latest user intent: an older
running subprocess may finish naturally, but its result must be ignored after
the generation or selected device changes. Work that has not started is
cancelled, and executor shutdown cancels queued work when the dialog closes.

The UI builders are divided by responsibility. Runtime-selection controls are
constructed separately from the main session editor so callbacks can rely on
their documented Tk variables and widgets without requiring contributors to
read one large construction method.

## Validation and recovery efficiency

Bundled runtime validation performs metadata validation, inventory collection,
and expected-file hashing in one filesystem walk. Unexpected files are recorded
for the inventory check but are not hashed because they cannot match the
trusted manifest. The process-local validation cache remains in place.

Configuration saves validate the existing primary while copying it to the
temporary backup, so an invalid primary cannot replace a valid backup without
requiring a separate primary parse. Recovery intentionally validates the
staged backup and then loads the replaced primary again: the first operation
protects the atomic replacement, while the second constructs a configuration
whose path is the real primary file rather than the temporary staging file.

## Scrcpy session lifecycle

The launcher intentionally uses two daemon threads per managed scrcpy
process. The exit monitor blocks in ``communicate()`` to collect diagnostics,
while the startup watcher independently checks for a visible top-level window
for at most the startup interval. Once the window appears—or the interval
expires—the watcher marks startup complete and later nonzero exits are logged
without an error dialog. The separation is appropriate for the small number of
sessions supported by the tray app and avoids introducing a more complex
coordinator without a measured performance benefit.

## Documentation changes

Changes to public APIs, configuration, packaging, security behavior, or
user-visible tray behavior should update the relevant docstring and one of the
user or maintainer guides. Release changes should also update the changelog,
site metadata, and packaging version fields.

The documentation coverage test checks public API docstrings in the source
tree. It is intentionally lightweight and does not require a documentation
generation toolchain.
