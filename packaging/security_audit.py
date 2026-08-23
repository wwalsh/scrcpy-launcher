# SPDX-License-Identifier: GPL-3.0-only

"""Deterministic dependency-policy checks used by tests, CI, and release builds."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = PROJECT_ROOT / "packaging/dependencies/scrcpy-win64-v4.1.json"
DEFAULT_REVIEW = PROJECT_ROOT / "packaging/dependencies/security-review.json"
REQUIREMENT_FILES = (
    PROJECT_ROOT / "requirements.txt",
    PROJECT_ROOT / "requirements-build.txt",
)
_EXACT_REQUIREMENT = re.compile(r"^[A-Za-z0-9_.-]+(?:\[[^]]+\])?==[^\s\\]+")
_HASH = re.compile(r"--hash=sha256:[0-9a-fA-F]{64}\b")


class SecurityAuditError(ValueError):
    """The checked dependency policy is incomplete or stale."""


def _logical_requirement_lines(path: Path) -> list[str]:
    logical: list[str] = []
    current = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.split("#", 1)[0].strip()
        if not stripped:
            continue
        continued = stripped.endswith("\\")
        fragment = stripped[:-1].strip() if continued else stripped
        current = f"{current} {fragment}".strip()
        if not continued:
            logical.append(current)
            current = ""
    if current:
        raise SecurityAuditError(f"{path.name} ends with an incomplete continuation")
    return logical


def validate_requirement_locks(paths: tuple[Path, ...] = REQUIREMENT_FILES) -> None:
    """Require exact versions and SHA-256 hashes for every Python package."""
    for path in paths:
        for line in _logical_requirement_lines(path):
            if line.startswith(("-r ", "--requirement ")):
                continue
            if not _EXACT_REQUIREMENT.match(line) or not _HASH.search(line):
                raise SecurityAuditError(
                    f"{path.name} contains an unpinned or unhashed requirement: {line}"
                )


def validate_native_review(
    manifest_path: Path = DEFAULT_MANIFEST,
    review_path: Path = DEFAULT_REVIEW,
    *,
    today: date | None = None,
) -> None:
    """Require a recent explicit review matching every bundled native component."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if review.get("schema_version") != 1:
        raise SecurityAuditError("unsupported dependency security-review schema")
    try:
        reviewed_on = date.fromisoformat(review["reviewed_on"])
        max_age_days = review["max_age_days"]
    except (KeyError, TypeError, ValueError) as exc:
        raise SecurityAuditError("dependency security-review metadata is invalid") from exc
    if not isinstance(max_age_days, int) or not 1 <= max_age_days <= 90:
        raise SecurityAuditError("dependency review max_age_days must be between 1 and 90")
    age = (today or date.today()) - reviewed_on
    if age.days < 0:
        raise SecurityAuditError("dependency security review date is in the future")
    if age.days > max_age_days:
        raise SecurityAuditError(
            f"dependency security review is stale ({age.days} days old; "
            f"maximum {max_age_days})"
        )

    expected = {(item["name"], item["version"]) for item in manifest["components"]}
    reviewed: set[tuple[str, str]] = set()
    for item in review.get("components", []):
        try:
            identity = (item["name"], item["version"])
            sources = item["advisory_sources"]
            status = item["status"]
            notes = item["notes"]
        except (KeyError, TypeError) as exc:
            raise SecurityAuditError("dependency review component is incomplete") from exc
        if identity in reviewed:
            raise SecurityAuditError(f"duplicate dependency review entry: {identity[0]}")
        if status not in {"reviewed", "accepted-risk", "update-required"}:
            raise SecurityAuditError(f"invalid review status for {identity[0]}")
        if status == "update-required":
            raise SecurityAuditError(f"dependency update is required for {identity[0]}")
        if not isinstance(sources, list) or not sources or not all(
            isinstance(source, str) and source.startswith("https://") for source in sources
        ):
            raise SecurityAuditError(f"advisory sources are missing for {identity[0]}")
        if not isinstance(notes, str) or not notes.strip():
            raise SecurityAuditError(f"review notes are missing for {identity[0]}")
        reviewed.add(identity)

    if reviewed != expected:
        missing = sorted(expected - reviewed)
        unexpected = sorted(reviewed - expected)
        raise SecurityAuditError(
            f"dependency review does not match bundle manifest; "
            f"missing={missing}, unexpected={unexpected}"
        )


def run_audit(*, today: date | None = None) -> None:
    validate_requirement_locks()
    validate_native_review(today=today)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--today", type=date.fromisoformat, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        run_audit(today=args.today)
    except (OSError, json.JSONDecodeError, SecurityAuditError) as exc:
        parser.error(str(exc))
    print("Dependency security policy checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
