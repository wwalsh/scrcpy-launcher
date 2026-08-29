# Windows release lifecycle test

Use this checklist for every Windows installer, simple portable ZIP, and
PortableApps.com release. Test with production
artifacts from `dist\artifacts`, not the PyInstaller staging directory. Preserve a
copy of any real configuration before testing.

## v0.7.3 acceptance record

`v0.7.3` completes the Milestone 8 maintenance phase. It removes obsolete UI
and tray scaffolding, separates focused Settings dialogs, defers optional
startup imports, limits device and application polling to active discovery, and
restores the tray icon automatically after Windows Explorer restarts.

| Check | Result |
| --- | --- |
| Automated tests | Passed 2026-08-23: 230 tests |
| Dependency security policy | Passed 2026-08-23 |
| Production build and package inventories | Passed 2026-08-23 |
| Portable archive inventory and isolation | Passed 2026-08-23 |
| Installer upgrade and configuration preservation | Passed 2026-08-23 |
| Installed and portable smoke tests | Passed 2026-08-23 |
| Settings and session workflow regression | Passed 2026-08-23 |
| Explorer restart recovery | Passed 2026-08-23: icon and menu recovered after two Explorer restarts |

## v0.7.2 acceptance record

`v0.7.2` adds native About information and a bounded, user-initiated GitHub
release check. The update checker runs outside the tray message loop and never
downloads or installs software.

| Check | Result |
| --- | --- |
| Automated tests | Passed 2026-08-23: 217 tests |
| Dependency security policy | Passed 2026-08-23 |
| Production build and package inventories | Passed 2026-08-23 |
| Portable archive inventory and isolation | Passed 2026-08-23 |
| About dialog and project link | Passed 2026-08-23: version, bundled scrcpy, license, and GitHub link verified |
| Update check responsiveness | Passed 2026-08-23: tray remained responsive and v0.7.1 was reported current |
| Installer upgrade and configuration preservation | Passed 2026-08-23 |
| Installed and portable smoke tests | Passed 2026-08-23 |

## v0.7.1 acceptance record

`v0.7.1` is the security-hardening release. It adds bounded configuration input,
safe atomic files, pinned build dependencies, bundled-runtime integrity checks,
targeted log redaction, reparse-point-safe installer cleanup, and enforceable
dependency-review policy.

| Check | Result |
| --- | --- |
| Automated tests | Passed 2026-08-22: 200 tests |
| Dependency security policy | Passed 2026-08-22 |
| Production build and package inventories | Passed 2026-08-22 |
| Portable archive inventory and isolation | Passed 2026-08-22 |
| NSIS reparse-point cleanup harness | Passed 2026-08-22: junction target preserved |
| Fresh install and installed package smoke test | Passed 2026-08-22 |
| Same-version repair | Passed 2026-08-22: configuration hash preserved |
| Silent uninstall and final reinstall | Passed 2026-08-22: configuration preserved and version `0.7.1` registered |
| Installed Settings and device discovery | Passed 2026-08-22: Settings opened and 2 devices detected |

## Automated release checks

The release build verifies that:

- installer staging contains no portable marker, portable default, or user config;
- the portable ZIP contains exactly the staged application plus
  `portable.marker` and `default-config.json`;
- the portable ZIP does not contain `config.json` or its backup;
- the bundled scrcpy metadata, required files, and hashes are valid;
- both installers are nonempty Windows executables;
- the `.paf.exe` payload passes archive-integrity checks, contains the required
  launcher and application files, and contains no user `Data` directory.

Run a release build before the manual matrix. Use `-OfflineDependencies` only
when the verified cache is already populated:

```powershell
.\packaging\build.ps1 -OfflineDependencies
```

## Manual matrix

Use a distinctive session name and custom scrcpy path so preservation failures
are obvious. Quit the tray before running Setup or Uninstall.

| Scenario | Procedure | Pass condition |
| --- | --- | --- |
| Fresh install | Remove or temporarily rename the launcher's AppData config, then install | A schema 2 bundled-mode config is created and bundled scrcpy launches |
| Custom upgrade | Select custom mode, add a session, and run the newer installer | Mode, path, sessions, and arguments are unchanged |
| Bundled upgrade | Select bundled mode, add a session, and run the newer installer | Sessions are unchanged and the packaged scrcpy version is current |
| Repair | Delete `tools\scrcpy\scrcpy.exe`, then rerun the same installer | Setup restores scrcpy; configuration is byte-for-byte unchanged |
| Normal uninstall | Uninstall and answer **No** to user-data removal | Application, shortcuts, and owned autostart entry are removed; config remains |
| Full uninstall | Reinstall, uninstall, and answer **Yes** | Application files, config, backups, recovery archives, and logs are removed |
| Portable first run | Extract the ZIP into a new folder and launch it | Adjacent `config.json` is created in bundled mode; AppData config is untouched |
| Portable upgrade | Edit adjacent `config.json`, then extract a newer ZIP over the folder | Adjacent config is byte-for-byte unchanged and the new application launches |
| PortableApps first run | Install the `.paf.exe` into a new PortableApps directory and launch it | `Data\config.json` is created in bundled mode; installed and simple-portable configs are untouched |
| PortableApps upgrade | Add a distinctive session, quit the tray, then install the same or newer `.paf.exe` to the same directory | The session and `Data\config.json` are preserved and the updated application launches |
| Side-by-side | Run installed and portable editions separately | Installed edition uses AppData; portable edition uses only its adjacent config |
| Explorer restart | With the tray running, restart **Windows Explorer** twice from Task Manager | The icon returns once after each restart; its menu, Settings, and Quit remain responsive |

## Location checks

Installed files:

```text
%LOCALAPPDATA%\Programs\scrcpy-launcher
```

Installed configuration:

```text
%APPDATA%\scrcpy-launcher\config.json
```

Portable configuration:

```text
<portable folder>\config.json
```

PortableApps.com configuration:

```text
<PortableApps folder>\scrcpy-launcherPortable\Data\config.json
```

The installer intentionally preserves installed configuration during upgrades
and same-version reinstalls. A portable upgrade is safe because release ZIPs
never contain `config.json`. PortableApps.com upgrades preserve the package's
`Data` directory. Uninstall only removes user data after an explicit
confirmation; silent uninstall defaults to preserving it.
