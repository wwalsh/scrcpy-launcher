# Security model and accepted risks

## Scope

scrcpy-launcher is a per-user, non-elevated Windows tray application. Its
installer writes beneath the current user's Local AppData directory, and its
configuration and logs are private user data rather than secrets. A process that
already has the same user's file-write privileges can modify that user's
configuration and application files; the launcher is not a privilege boundary
against such a process.

## Implemented controls

- Configuration, recovery, and session-import JSON are size and structure
  limited before use.
- Configuration and exports use unpredictable same-directory temporary files
  and atomic replacement.
- The bundled scrcpy inventory is checked against hashes compiled into the
  launcher before its first use in each process. Missing, changed, and unexpected
  files are rejected.
- Installer upgrade and uninstall cleanup validates fixed app-owned roots and
  traverses only ordinary directories. Reparse points are removed as links and
  are never followed. Optional user-data cleanup removes only known files;
  unknown files prevent their containing directory from being removed.
- Persistent logging applies targeted redaction to Windows user-profile paths,
  `--serial` values, and common device-error serial contexts. Detailed errors
  may still be displayed interactively to the current user.
- Python dependencies are hash locked and automatically audited. Native bundle
  reviews are version matched and expire after 45 days.

## Accepted risk: runtime verification window

**ID:** SEC-RISK-001  
**Severity:** Low  
**Status:** Accepted  
**Accepted:** 2026-08-22  
**Owner:** Project maintainers

The bundled runtime is verified once per launcher or Settings process and the
successful result is cached for that process. There is therefore a window in
which a same-user process with write access could replace a verified runtime
file before scrcpy or ADB subsequently opens it.

This is accepted because exploitation already requires the ability to modify
the current user's installed application files, the application does not run
elevated, and hashing before every subprocess launch would add repeated I/O
without eliminating the final check-to-use race. The control remains useful for
detecting accidental corruption and persistent tampering before first use.

Reassess this acceptance if the application becomes elevated, is installed in a
shared or privileged location, introduces a service or multi-user boundary,
changes its runtime-launch model, receives credible evidence of exploitation,
or adopts a stronger signed/runtime trust mechanism. It must also be reviewed
during the next substantive security audit.

## Logging boundary

Redaction is intentionally targeted, not a general secret scanner. Arbitrary
text returned by Windows, custom executables, or future diagnostics could still
contain identifiers in an unrecognized format. Logs should not be attached to a
public issue without review. This residual diagnostic-privacy risk remains low
because logs are stored in the current user's Local AppData directory and the
highest-risk known fields are either omitted or masked.
