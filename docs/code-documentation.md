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

## Documentation changes

Changes to public APIs, configuration, packaging, security behavior, or
user-visible tray behavior should update the relevant docstring and one of the
user or maintainer guides. Release changes should also update the changelog,
site metadata, and packaging version fields.

The documentation coverage test checks public API docstrings in the source
tree. It is intentionally lightweight and does not require a documentation
generation toolchain.
