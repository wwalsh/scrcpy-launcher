# Code Signing Policy

This document defines the code-signing policy for official Windows releases of
**scrcpy-launcher**.

**Free code signing provided by SignPath.io, certificate by SignPath Foundation.**

## Status

scrcpy-launcher is preparing an application to the SignPath Foundation
open-source code-signing program.

Existing releases produced before SignPath approval are unsigned. A release must
not be represented as Authenticode-signed unless its release artifacts have
successfully completed the SignPath signing process described by this policy.

After approval and integration, this policy will govern all Windows release
artifacts signed through SignPath Foundation.

## Project

- **Project:** scrcpy-launcher
- **Repository:** https://github.com/wwalsh/scrcpy-launcher
- **Website:** https://scrcpy-launcher.link/
- **License:** GNU General Public License v3.0 only (`GPL-3.0-only`)
- **Maintainer:** William Walsh (`@wwalsh`)

scrcpy-launcher is a free and open-source Windows application for saving and
launching reusable scrcpy sessions.

The repository contains the source code and project-owned build and packaging
definitions used to produce official scrcpy-launcher releases.

## Team roles

The project is currently maintained by one person. The same maintainer may
therefore perform more than one SignPath role.

### Authors and committers

- William Walsh (`@wwalsh`)

Authors and committers are trusted to modify project-owned source code,
documentation, build definitions, and release infrastructure.

### Reviewers

- William Walsh (`@wwalsh`)

Changes submitted by external contributors must be reviewed before they are
incorporated into an official release.

Particular attention must be given to changes affecting build scripts,
packaging, dependencies, GitHub Actions workflows, or code-signing
configuration because these files can affect the contents of signed artifacts.

### Signing approver

- William Walsh (`@wwalsh`)

Every production signing request must receive manual approval before a SignPath
Foundation certificate may be applied.

The approver is responsible for confirming that the signing request corresponds
to an intended project release and that its verified source and build
information are consistent with that release.

All people holding these roles must use multi-factor authentication for GitHub
and SignPath access.

## Artifacts eligible for signing

Only official Windows release artifacts built from the public
`wwalsh/scrcpy-launcher` repository through the approved release workflow are
eligible for signing.

Project-owned artifacts that may be signed include:

- the packaged `scrcpy-launcher.exe` application;
- the official scrcpy-launcher Windows installer;
- other project-owned executable components explicitly identified by the
  SignPath artifact configuration.

Portable distributions may contain the signed project-owned executable inside
an otherwise unsigned ZIP archive.

Source archives, checksum files, documentation, configuration files, and other
non-executable release assets do not require Authenticode signing.

## Third-party components

scrcpy-launcher distributions include third-party open-source components,
including **scrcpy** and **Android Debug Bridge (ADB)**.

These components retain their respective upstream licenses and are documented
in the project's third-party notices.

The scrcpy-launcher SignPath policy must **not** be used to apply the project's
SignPath Foundation signature to upstream binaries that are not maintained by
the scrcpy-launcher project.

Unsigned upstream open-source binaries may be included within an official signed
scrcpy-launcher package when permitted by SignPath Foundation policy.

Signing a scrcpy-launcher installer or other project-owned package indicates the
authenticity and integrity of that project-owned package. It does not imply that
every embedded third-party executable has individually been signed by
scrcpy-launcher or SignPath Foundation.

## Trusted build and release process

Production-signed artifacts must:

1. originate from the public `wwalsh/scrcpy-launcher` repository;
2. be produced by the project's version-controlled release build process;
3. be built by the trusted CI system configured for the SignPath project;
4. originate from an allowed release source, normally the repository's
   `main` branch and the corresponding release tag;
5. pass the project's required automated tests and release validation;
6. pass applicable dependency and native-component security checks;
7. pass SignPath trusted-build and origin verification;
8. receive manual approval through SignPath;
9. be returned by SignPath with a valid Authenticode signature before
   publication as a signed release.

The build must be determined by source code, dependency definitions, build
scripts, packaging configuration, and CI configuration stored in the public
repository.

Local developer builds, manually uploaded executables, builds from forks,
unverified CI artifacts, debug builds, and artifacts whose source commit cannot
be established are not eligible for production signing.

A signed artifact must not be replaced after signing with a locally rebuilt or
otherwise different file.

## Distribution provenance

Official distributions must be traceable to the public project repository and a
specific source revision.

The project's public GitHub Actions build-validation workflow uses the same
version-controlled `packaging/build.ps1` release build path used for manual
release builds. For each workflow run, GitHub records the repository, source
commit, workflow definition, runner environment, logs, and produced build
artifacts.

The build process uses exact-version, SHA-256 hash-locked Python dependencies,
a pinned manifest for bundled scrcpy/ADB artifacts, automated tests, dependency
policy checks, packaged smoke tests, release inventory verification, and
SHA-256 generation for produced artifacts.

These controls make the build process repeatable, reviewable, and resistant to
unreviewed dependency or packaging changes. The project does **not** currently
claim that independent builds are guaranteed to be byte-for-byte identical.

Production signing, once enabled, must only accept artifacts whose source
revision and trusted build provenance can be established according to the
SignPath configuration.

## Release integrity

The source commit, application version, release tag, and release artifact
version must correspond to the same release.

SignPath artifact configuration must restrict signed project-owned binaries to
the expected **scrcpy-launcher** product identity and consistent version
metadata.

SHA-256 checksums published for signed release artifacts must be generated from
the final artifacts after the signing process is complete.

## Privacy

scrcpy-launcher does not collect telemetry, analytics, device inventories,
configuration data, or usage information and does not automatically send such
information to the project maintainer or a project-operated service.

The application makes no automatic Internet requests.

When the user explicitly selects **Check for updates**, scrcpy-launcher contacts
GitHub's public Releases API over HTTPS to determine whether a newer release is
available. The request includes the installed launcher version in its
user-agent. Configuration, saved sessions, Android device identifiers, and
installed application inventories are not transmitted.

The program will not transfer information to other networked systems unless
specifically requested by the user or required for an operation the user
initiated.

scrcpy itself and ADB communicate with Android devices as required to provide
their intended functionality. Their behavior and licensing are governed by
their respective upstream projects.

## User-visible system changes

scrcpy-launcher does not make undisclosed system configuration changes.

The installed edition may create normal application files, Start-menu
integration, configuration files, logs, and — when explicitly selected by the
user — Windows autostart configuration.

Portable editions operate from their extracted directory and do not require
installation.

Actions such as configuring Android USB debugging are performed by the user
outside scrcpy-launcher.

## Uninstallation

The installed edition provides a normal Windows uninstaller and may also be
removed through **Windows Settings > Apps > Installed apps**.

The uninstaller allows the user to choose whether project-created settings and
related user data should also be removed.

Portable installations may be removed by quitting the application and deleting
the extracted directory.

## Signature verification

Users may verify a signed executable or installer with Windows PowerShell:

```powershell
Get-AuthenticodeSignature -LiteralPath ".\scrcpy-launcher.exe" |
    Format-List Status, SignerCertificate, TimeStamperCertificate
```

For an authentic signed release, the signature status must be valid and the
signer certificate must correspond to the SignPath Foundation certificate used
for the project.

A SHA-256 checksum verifies file integrity against a published checksum but is
not a substitute for an Authenticode signature.

## Signing credentials and access

Private signing keys are not stored in the scrcpy-launcher repository or
distributed to maintainers.

Repository secrets, SignPath credentials, API tokens, and other signing-related
credentials must never be committed to source control or included in release
artifacts.

Access to release and signing infrastructure must be limited to the accounts
required to maintain and release the project.

## Signing incidents

If certificate misuse, unauthorized signing, compromise of release
infrastructure, or an unexpected signed artifact is suspected:

1. production signing will be suspended;
2. relevant repository, CI, and SignPath records will be preserved for
   investigation;
3. the affected release will not be distributed as trusted;
4. SignPath will be notified when the incident may involve the Foundation
   certificate or signing infrastructure;
5. certificate revocation or other remediation will be requested when
   appropriate.

Security issues should be reported according to the project's
[`SECURITY.md`](../SECURITY.md).

## Policy changes

Changes to this policy, the release workflow, signing configuration, or other
security-sensitive build infrastructure must be committed to the public
repository.

Material changes to what is eligible for signing or how signed artifacts are
produced must be reviewed before they are used for a production-signed release.
