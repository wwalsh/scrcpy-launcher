# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = PROJECT_ROOT / "packaging" / "stage_scrcpy.py"
SPEC = importlib.util.spec_from_file_location("stage_scrcpy", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
stage_scrcpy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage_scrcpy)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest_for(files: dict[str, bytes]) -> dict:
    return {
        "schema_version": 1,
        "bundle": {
            "name": "scrcpy",
            "version": "test",
            "architecture": "win64",
            "release_tag": "vtest",
            "source_commit": "abc123",
            "archive_name": "bundle.zip",
            "archive_url": "https://example.invalid/bundle.zip",
            "archive_sha256": "unused",
            "expected_root": "scrcpy-test",
            "destination": "tools/scrcpy",
            "files": {name: digest(data) for name, data in files.items()},
        },
        "components": [],
        "source_artifacts": [],
    }


def write_bundle(path: Path, files: dict[str, bytes], extra: dict[str, bytes] | None = None) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(f"scrcpy-test/{name}", data)
        for name, data in (extra or {}).items():
            archive.writestr(name, data)


class DependencyBundleTests(unittest.TestCase):
    def test_pinned_manifest_matches_official_scrcpy_release(self) -> None:
        manifest = stage_scrcpy.load_manifest(
            PROJECT_ROOT / "packaging" / "dependencies" / "scrcpy-win64-v4.1.json"
        )
        bundle = manifest["bundle"]

        self.assertEqual(bundle["version"], "4.1")
        self.assertEqual(bundle["architecture"], "win64")
        self.assertEqual(bundle["source_commit"], "2926c06")
        self.assertEqual(
            bundle["archive_sha256"],
            "5b12172b3264b2889f4583ee64752ce832e29bc8b1089dca81093459697165db",
        )
        self.assertNotIn("latest", bundle["archive_url"])
        for required in ("scrcpy.exe", "scrcpy-server", "adb.exe", "SDL3.dll"):
            self.assertIn(required, bundle["files"])

    def test_acquire_rejects_wrong_cached_hash_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cached = Path(directory) / "bundle.zip"
            cached.write_bytes(b"wrong")
            with self.assertRaisesRegex(stage_scrcpy.BundleError, "Cached bundle"):
                stage_scrcpy.acquire_file(
                    name="bundle",
                    url="https://example.invalid/bundle.zip",
                    expected_sha256=digest(b"right"),
                    cache_path=cached,
                    offline=True,
                )

    def test_manifest_rejects_malformed_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            manifest = manifest_for({"scrcpy.exe": b"exe"})
            manifest["bundle"]["archive_sha256"] = "too-short"
            path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(stage_scrcpy.BundleError, "Invalid SHA-256"):
                stage_scrcpy.load_manifest(path)

    def test_verify_rejects_missing_and_unexpected_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "bundle.zip"
            write_bundle(archive, {"scrcpy.exe": b"exe"}, {"scrcpy-test/extra": b"x"})
            manifest = manifest_for({"scrcpy.exe": b"exe", "adb.exe": b"adb"})

            with self.assertRaisesRegex(stage_scrcpy.BundleError, "inventory mismatch"):
                stage_scrcpy.verify_archive(archive, manifest["bundle"])

    def test_verify_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "bundle.zip"
            write_bundle(
                archive,
                {"scrcpy.exe": b"exe"},
                {"scrcpy-test/../escaped.exe": b"unsafe"},
            )
            manifest = manifest_for({"scrcpy.exe": b"exe"})

            with self.assertRaisesRegex(stage_scrcpy.BundleError, "Unsafe ZIP"):
                stage_scrcpy.verify_archive(archive, manifest["bundle"])

    def test_stage_bundle_creates_verified_layout_and_deterministic_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "bundle.zip"
            files = {"scrcpy.exe": b"exe", "sub/data.bin": b"data"}
            write_bundle(archive, files)
            manifest = manifest_for(files)
            first = root / "first"
            second = root / "second"

            stage_scrcpy.stage_bundle(archive, manifest, first)
            stage_scrcpy.stage_bundle(archive, manifest, second)

            self.assertEqual((first / "scrcpy.exe").read_bytes(), b"exe")
            self.assertEqual((first / "sub" / "data.bin").read_bytes(), b"data")
            self.assertEqual(
                (first / "BUNDLE-METADATA.json").read_bytes(),
                (second / "BUNDLE-METADATA.json").read_bytes(),
            )

    def test_source_artifacts_are_verified_and_license_texts_extracted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "cache"
            cache.mkdir()
            tar_path = cache / "source.tar.gz"
            license_text = b"example license\n"
            with tarfile.open(tar_path, "w:gz") as archive:
                info = tarfile.TarInfo("source/COPYING")
                info.size = len(license_text)
                archive.addfile(info, io.BytesIO(license_text))
            manifest = {
                "source_artifacts": [
                    {
                        "name": "example",
                        "filename": tar_path.name,
                        "url": "https://example.invalid/source.tar.gz",
                        "sha256": stage_scrcpy.sha256_file(tar_path),
                        "license_member": "source/COPYING",
                        "license_output": "example.txt",
                    }
                ]
            }

            stage_scrcpy.stage_source_artifacts(
                manifest, cache, root / "sources", root / "licenses", offline=True
            )

            self.assertEqual((root / "licenses" / "example.txt").read_bytes(), license_text)
            self.assertEqual((root / "sources" / tar_path.name).read_bytes(), tar_path.read_bytes())
            metadata = json.loads((root / "sources" / "SOURCE-METADATA.json").read_text())
            self.assertEqual(metadata["sources"][0]["name"], "example")


if __name__ == "__main__":
    unittest.main()
