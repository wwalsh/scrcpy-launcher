# Security policy

## Reporting a vulnerability

Do not publish device serials, user-profile paths, configuration files, or other
private diagnostics in a public report.

Use GitHub's private vulnerability reporting for this repository:

https://github.com/wwalsh/scrcpy-launcher/security/advisories/new

If private vulnerability reporting cannot be used, open a minimal public issue
requesting a private contact channel and omit exploit details until one is
provided.

Include the affected release, Windows version, reproduction conditions, and the
security impact. Reports involving bundled runtime tampering should also include
the displayed verification error and the release artifact's SHA-256 file.

## Dependency monitoring

- Python runtime and build requirements are exact-version, SHA-256 hash locked.
- A scheduled GitHub Actions job runs `pip-audit` against the locked Python
  dependency set every week and on relevant changes.
- Dependabot monitors Python and GitHub Actions dependencies weekly.
- Native components in the scrcpy bundle are recorded in the bundle manifest.
  Their explicit advisory review is recorded in
  `packaging/dependencies/security-review.json`.
- The native review expires after 45 days. Tests and release builds fail if it
  is stale, incomplete, marked `update-required`, or does not exactly match the
  current bundle manifest.

Before a release, resolve audit failures, update vulnerable dependencies where
practical, record any narrowly justified accepted risk, refresh the native
review date and notes, and run the complete release build.

## Code signing

scrcpy-launcher is preparing an application to the SignPath Foundation open-source code-signing program. Existing releases are not currently Authenticode signed, so signing is not represented as an existing control.

The project's signing scope, trusted-build requirements, approver role, third-party binary handling, and signing incident process are documented in [docs/code-signing-policy.md](docs/code-signing-policy.md).

## Accepted limitations

The current accepted low-risk limitations and their review triggers are
documented in [docs/security-model.md](docs/security-model.md).
