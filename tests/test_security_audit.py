# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import json
import importlib.util
import tempfile
import unittest
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "scrcpy_launcher_security_audit",
    PROJECT_ROOT / "packaging/security_audit.py",
)
assert _SPEC is not None and _SPEC.loader is not None
security_audit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(security_audit)

DEFAULT_MANIFEST = security_audit.DEFAULT_MANIFEST
DEFAULT_REVIEW = security_audit.DEFAULT_REVIEW
SecurityAuditError = security_audit.SecurityAuditError
run_audit = security_audit.run_audit
validate_native_review = security_audit.validate_native_review
validate_requirement_locks = security_audit.validate_requirement_locks


class SecurityAuditTests(unittest.TestCase):
    def test_current_dependency_policy_passes(self) -> None:
        run_audit(today=date(2026, 8, 22))

    def test_requirement_must_be_exactly_pinned_and_hashed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            unlocked = Path(directory) / "requirements.txt"
            unlocked.write_text("example>=1.0\n", encoding="utf-8")

            with self.assertRaisesRegex(SecurityAuditError, "unhashed"):
                validate_requirement_locks((unlocked,))

    def test_stale_native_review_fails(self) -> None:
        with self.assertRaisesRegex(SecurityAuditError, "stale"):
            validate_native_review(today=date(2026, 10, 7))

    def test_manifest_version_change_requires_new_review(self) -> None:
        manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        manifest["components"][0]["version"] = "future"
        with tempfile.TemporaryDirectory() as directory:
            changed_manifest = Path(directory) / "manifest.json"
            changed_manifest.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(SecurityAuditError, "does not match"):
                validate_native_review(
                    changed_manifest,
                    DEFAULT_REVIEW,
                    today=date(2026, 8, 22),
                )


if __name__ == "__main__":
    unittest.main()
