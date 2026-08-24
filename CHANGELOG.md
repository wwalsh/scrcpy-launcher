# Changelog

All notable changes to the public scrcpy-launcher releases are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.3] - 2026-08-23

### Changed

- Removed obsolete UI and tray scaffolding.
- Split focused Settings dialogs into dedicated modules.
- Deferred optional imports to improve startup efficiency.
- Limited device and application polling to active discovery operations.

### Fixed

- Restored the tray icon automatically after Windows Explorer restarts.

### Compatibility

- Preserved configuration compatibility with v0.7.2.

## [0.7.2] - 2026-08-23

### Added

- Added a native About dialog with launcher version, bundled scrcpy version,
  license, and project information.
- Added a user-requested GitHub release update check.

### Changed

- Kept update checks off the tray message loop so the tray remains responsive.
- Bounded update requests and kept downloading and installation under explicit
  user control.

## [0.7.1] - 2026-08-22

### Added

- Published the first public installer and portable editions.
- Bundled verified scrcpy 4.1 and ADB runtimes.
- Added connected-device detection and installed-application selection.
- Added session creation, editing, duplication, reordering, import, and export.
- Added optional per-user Windows autostart for the launcher.

### Security

- Added configuration recovery, bounded JSON input, atomic file handling,
  dependency controls, bundled-runtime integrity verification, targeted log
  redaction, and hardened installer cleanup.

[0.7.3]: https://github.com/wwalsh/scrcpy-launcher/compare/v0.7.2...v0.7.3
[0.7.2]: https://github.com/wwalsh/scrcpy-launcher/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/wwalsh/scrcpy-launcher/releases/tag/v0.7.1
