# Building and testing scrcpy-launcher

This document is for source development and release packaging. Installed and
portable users should start with the [README](../README.md).

## Development requirements

- Windows 11
- Python 3.10 or newer
- NSIS 3 for installer builds
- PortableApps.com Launcher 2.2.9 or newer
- PortableApps.com Installer 3.9.18 or newer
- Network access for the first bundled-dependency staging run, or a populated
  offline dependency cache

## Source setup

From PowerShell in the repository:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements.txt
Copy-Item .\config.example.json .\config.json
```

The personal `config.json` is ignored by Git. To use a development scrcpy copy,
change the example to custom mode and set `scrcpy_path` to `scrcpy.exe`.

Start the tray:

```powershell
python -m src.main
```

Explicit configuration paths are also supported:

```powershell
python -m src.main --config "C:\path\to\config.json"
```

Run Settings without the tray:

```powershell
python -m src.settings_main config.json
```

## Tests

```powershell
python -m unittest discover -s tests -v
```

The test suite covers configuration limits and recovery, session transfer,
device and application parsing, tray/settings lifecycle, runtime integrity,
logging redaction, dependency policy, packaging, and release verification.

Run the deterministic dependency-policy gate separately with:

```powershell
python packaging\security_audit.py
```

This validates exact Python locks and the freshness and manifest alignment of
the native dependency review. It does not query live vulnerability services.

## Architecture

The API documentation and comment policy are defined in
[`docs/code-documentation.md`](code-documentation.md). Public callables carry
their contracts in docstrings; this section summarizes the ownership and
process boundaries that are most important when changing the code.

- `src/main.py` handles invocation, logging, single-instance ownership, startup
  recovery, and tray startup.
- `src/tray.py` owns the native Win32 tray and starts Settings separately.
- `src/settings_main.py` and `src/settings.py` own the tkinter Settings process.
- `src/config.py`, `src/config_recovery.py`, and `src/session_transfer.py` handle
  bounded, validated, atomic configuration operations.
- `src/scrcpy_runtime.py` resolves custom/bundled runtimes and verifies the
  bundled inventory once per process.
- `src/devices.py` and `src/device_apps.py` provide background device
  and application discovery.
- `src/launcher.py` starts and monitors scrcpy without a console window.
- `src/autostart.py` manages the current user's installed-app registration.
- `src/logging_setup.py` configures rotating, privacy-redacted logs.
- `src/update_check.py` performs bounded, user-initiated GitHub release checks.
- `packaging/` contains dependency staging, PyInstaller, NSIS, security-policy,
  cleanup-safety, and release-verification tools.

## Build dependencies

Install the complete exact-version, hash-locked build set:

```powershell
python -m pip install --require-hashes -r requirements-build.txt
```

NSIS may be installed normally or through PortableApps. The build searches
`NSIS_HOME`, `PATH`, the current user's standard PortableApps location, and the
standard Program Files locations. An explicit compiler can be supplied.

The PortableApps tools are discovered in the current user's standard
`PortableApps` directory or through `PORTABLEAPPS_LAUNCHER_HOME` and
`PORTABLEAPPS_INSTALLER_HOME`. Explicit executable paths may also be supplied.

The main build switches are:

- `-SkipInstaller` skips NSIS creation.
- `-SkipPortableApps` skips PortableApps.com generation.
- `-OfflineDependencies` uses only the local dependency cache.
- `-DependencyCache <path>` selects a shared dependency cache.
- `-SkipBundledTools` creates a developer-only package and must be combined
  with both packaging skip switches.

The build recreates generated `build/` and `dist/` output beneath the project
root, stages verified bundled tools, runs the test suite, and performs release
verification before reporting success. It does not modify tracked source or
user configuration files.

## Release build

```powershell
.\packaging\build.ps1
```

Or select NSIS explicitly:

```powershell
.\packaging\build.ps1 `
  -NsisCompiler "C:\path\to\makensis.exe"
```

PortableApps tools can also be selected explicitly:

```powershell
.\packaging\build.ps1 `
  -PortableAppsLauncherGenerator "C:\path\to\PortableApps.comLauncherGenerator.exe" `
  -PortableAppsInstaller "C:\path\to\PortableApps.comInstaller.exe"
```

The build:

1. validates dependency policy;
2. runs the automated tests;
3. creates the PyInstaller one-folder application;
4. acquires and verifies the pinned scrcpy bundle and required source artifacts;
5. runs the packaged smoke test;
6. creates the Windows installer, simple portable ZIP, and PortableApps `.paf.exe`;
7. verifies the `.paf.exe` archive integrity, required payload, and absence of user `Data`;
8. verifies package inventories and installed/portable isolation; and
9. writes SHA-256 files under `dist\artifacts`.

Downloads are cached under `.cache\dependencies`. Use an alternate or offline
cache with:

```powershell
.\packaging\build.ps1 `
  -DependencyCache "D:\build-cache" `
  -OfflineDependencies
```

Developer builds may omit the Windows installer or PortableApps package:

```powershell
.\packaging\build.ps1 -SkipInstaller
.\packaging\build.ps1 -SkipPortableApps
```

Create a developer-only unbundled package with:

```powershell
.\packaging\build.ps1 -SkipInstaller -SkipPortableApps -SkipBundledTools
```

An unbundled package is explicitly named `unbundled` and is not a release.

## Dependency monitoring

Python and GitHub Actions monitoring files are present under `.github/`.
Scheduled GitHub Actions and Dependabot provide hosted monitoring. In addition:

- run `python packaging\security_audit.py` before every release;
- review the upstream advisory sources in
  `packaging/dependencies/security-review.json`;
- refresh that review within its 45-day window; and
- use the scheduled `pip-audit` workflow for live Python vulnerability queries.

The release build fails when the native review is stale, incomplete, marked
`update-required`, or no longer exactly matches the bundle manifest.

## Public CI build validation

The public GitHub Actions workflow at
`.github/workflows/build-validation.yml` runs on Windows for pushes to `main`,
pull requests, and manual dispatches.

It installs the exact hash-locked build dependencies, runs the version-controlled
release build in portable mode, executes the same automated verification gates,
and uploads the resulting `dist/artifacts` directory as a GitHub Actions
artifact named for the source commit SHA.

This provides a public, reviewable source-to-artifact build path. It is intended
to demonstrate repeatability and provenance; it is not currently a claim of
byte-for-byte reproducible builds across independent environments.

## Release checklist

- Update `src/version.py`, the NSIS fallback version, `CHANGELOG.md`, and the
  website's current-release and What's New text.
- Refresh dependency review records when required.
- Run the complete build.
- Manually install the `.paf.exe`, create or edit a session, then install it
  again to the same PortableApps directory and confirm `Data\config.json` is
  preserved.
- Follow [windows-lifecycle-test.md](windows-lifecycle-test.md).
- Confirm hashes for the Windows installer, simple portable ZIP, and PortableApps `.paf.exe`.
- Inspect the working tree for personal configuration and generated reports.
- Use the matching changelog entry as the basis for reviewed GitHub release
  notes.
- Include a **Code signing policy** link in GitHub release notes. Until SignPath
  approval and integration are complete, state clearly that the release is
  unsigned. After signing is enabled, identify the signed artifacts accurately
  and link to [docs/code-signing-policy.md](code-signing-policy.md).
- Create the release commit and annotated tag only after acceptance.

Authenticode signing is not currently part of the release process.
