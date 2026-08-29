# Contributing to scrcpy-launcher

Thank you for considering a contribution to scrcpy-launcher.

scrcpy-launcher is a small Windows-focused open-source project. Contributions
that improve reliability, usability, documentation, testing, packaging, or
security are welcome when they fit the project's scope and maintenance goals.

By participating in the project, you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Before contributing

For bug reports and feature ideas, check existing GitHub issues first to avoid
duplicates.

Security vulnerabilities must **not** be reported in a public issue. Follow the
private reporting instructions in [SECURITY.md](SECURITY.md).

For substantial behavioral or architectural changes, opening an issue before
writing a large patch is encouraged so the intended scope can be discussed
before significant work is invested.

## Development setup

Development requires Windows 11 and Python 3.10 or newer.

From PowerShell in the repository:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements.txt
Copy-Item .\config.example.json .\config.json
```

Run the application with:

```powershell
python -m src.main
```

Full build, packaging, dependency, and release instructions are in
[docs/building.md](docs/building.md).

## Tests

Run the automated test suite before submitting a pull request:

```powershell
python -m unittest discover -s tests -v
```

Run the deterministic dependency-policy gate when changing dependencies,
packaging, bundled runtime definitions, or release-related files:

```powershell
python packaging\security_audit.py
```

The public GitHub Actions build-validation workflow provides an additional
Windows build check for pull requests and changes to `main`.

## Pull requests

Pull requests should:

- have a clear purpose and limited scope;
- avoid unrelated cleanup or formatting changes;
- include or update tests when behavior changes;
- update user or developer documentation when necessary;
- preserve existing security, privacy, packaging, and compatibility controls;
- avoid committing personal configuration, device identifiers, generated
  reports, build caches, or release artifacts.

Changes submitted by people who are not project committers must be reviewed by
the maintainer before they are accepted.

Special attention is required for changes to:

- GitHub Actions workflows;
- build and packaging scripts;
- dependency lock files and bundled-component manifests;
- release verification;
- code-signing configuration;
- security-sensitive runtime behavior.

These files can affect the provenance or contents of official release
artifacts.

## Release and signing boundaries

Contributors must not:

- publish or replace official project releases;
- move or recreate release tags;
- represent an unsigned artifact as signed;
- use project signing infrastructure for third-party or upstream binaries;
- introduce signing credentials, private keys, API tokens, or other secrets
  into the repository.

Official release and code-signing decisions are maintainer responsibilities and
are governed by the
[Code Signing Policy](docs/code-signing-policy.md).

## Licensing

By submitting a contribution, you agree that your contribution may be
distributed under the project's
[GNU General Public License version 3 only](LICENSE), identified as
`GPL-3.0-only`.

Do not submit code or assets that you do not have the right to contribute.
Third-party material must have a compatible open-source license and must retain
required notices and attribution.

## Maintainer and review responsibility

The project is currently maintained by **William Walsh (`@wwalsh`)**.

The maintainer acts as the current committer, reviewer, and signing approver.
External contributions require maintainer review before inclusion in an
official release.

All accounts used for repository administration and code-signing approval must
use multi-factor authentication.
## Documentation expectations

Public Python APIs must have accurate docstrings describing their inputs,
outputs, exceptions, and externally visible side effects. Add rationale
comments for non-obvious Windows, process, security, concurrency, or recovery
behavior. Do not add comments that merely restate the code.

Changes to configuration, packaging, security controls, or tray behavior must
update the corresponding user or maintainer documentation. See
[`docs/code-documentation.md`](docs/code-documentation.md) for the project
standard.
