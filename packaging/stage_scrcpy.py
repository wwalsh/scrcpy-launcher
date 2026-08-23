# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


class BundleError(RuntimeError):
    """Raised when a dependency cannot be verified or safely staged."""


SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}")


def _require_sha256(value: Any, description: str) -> None:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise BundleError(f"Invalid SHA-256 for {description}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleError(f"Could not read dependency manifest {path}: {exc}") from exc

    if manifest.get("schema_version") != 1:
        raise BundleError("Unsupported dependency manifest schema")
    bundle = manifest.get("bundle")
    if not isinstance(bundle, dict):
        raise BundleError("Dependency manifest is missing 'bundle'")
    required = (
        "name",
        "version",
        "architecture",
        "release_tag",
        "source_commit",
        "archive_name",
        "archive_url",
        "archive_sha256",
        "expected_root",
        "destination",
        "files",
    )
    missing = [key for key in required if not bundle.get(key)]
    if missing:
        raise BundleError(f"Dependency manifest is missing: {', '.join(missing)}")
    if not isinstance(bundle["files"], dict) or not bundle["files"]:
        raise BundleError("Dependency manifest must contain a non-empty file inventory")
    _require_sha256(bundle["archive_sha256"], "bundle archive")
    for filename, file_hash in bundle["files"].items():
        if not isinstance(filename, str) or not filename:
            raise BundleError("Dependency manifest contains an invalid filename")
        _require_sha256(file_hash, f"bundle file {filename}")
    source_artifacts = manifest.get("source_artifacts", [])
    if not isinstance(source_artifacts, list):
        raise BundleError("Dependency manifest 'source_artifacts' must be a list")
    for source in source_artifacts:
        if not isinstance(source, dict):
            raise BundleError("Dependency manifest contains an invalid source artifact")
        _require_sha256(source.get("sha256"), f"{source.get('name', 'source')} archive")
    return manifest


def acquire_file(
    *, name: str, url: str, expected_sha256: str, cache_path: Path, offline: bool
) -> Path:
    expected_sha256 = expected_sha256.lower()
    if cache_path.is_file():
        actual = sha256_file(cache_path)
        if actual != expected_sha256:
            raise BundleError(
                f"Cached {name} has SHA-256 {actual}, expected {expected_sha256}: "
                f"{cache_path}"
            )
        return cache_path
    if offline:
        raise BundleError(f"Offline dependency is not cached: {cache_path}")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{cache_path.name}.", suffix=".download", dir=cache_path.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        request = urllib.request.Request(url, headers={"User-Agent": "scrcpy-launcher-build"})
        with urllib.request.urlopen(request, timeout=120) as response, temporary_path.open(
            "wb"
        ) as output:
            shutil.copyfileobj(response, output)
        actual = sha256_file(temporary_path)
        if actual != expected_sha256:
            raise BundleError(
                f"Downloaded {name} has SHA-256 {actual}, expected {expected_sha256}"
            )
        os.replace(temporary_path, cache_path)
        temporary_path = None
        return cache_path
    except BundleError:
        raise
    except Exception as exc:
        raise BundleError(f"Could not download {name} from {url}: {exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _safe_member_path(member: zipfile.ZipInfo, expected_root: str) -> Path | None:
    raw_name = member.filename.replace("\\", "/")
    path = PurePosixPath(raw_name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise BundleError(f"Unsafe ZIP member path: {member.filename}")
    if ":" in path.parts[0] or path.parts[0] != expected_root:
        raise BundleError(f"Unexpected ZIP root in member: {member.filename}")
    unix_mode = member.external_attr >> 16
    if stat.S_ISLNK(unix_mode):
        raise BundleError(f"Symbolic links are not allowed in the bundle: {member.filename}")
    relative_parts = path.parts[1:]
    if not relative_parts:
        return None
    return Path(*relative_parts)


def verify_archive(archive: Path, bundle: dict[str, Any]) -> dict[str, zipfile.ZipInfo]:
    expected_files = bundle["files"]
    members: dict[str, zipfile.ZipInfo] = {}
    try:
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                relative_path = _safe_member_path(member, bundle["expected_root"])
                if relative_path is None or member.is_dir():
                    continue
                relative_name = relative_path.as_posix()
                if relative_name in members:
                    raise BundleError(f"Duplicate ZIP member: {relative_name}")
                members[relative_name] = member

            actual_names = set(members)
            expected_names = set(expected_files)
            if actual_names != expected_names:
                missing = sorted(expected_names - actual_names)
                unexpected = sorted(actual_names - expected_names)
                details = []
                if missing:
                    details.append(f"missing: {', '.join(missing)}")
                if unexpected:
                    details.append(f"unexpected: {', '.join(unexpected)}")
                raise BundleError("Bundle inventory mismatch (" + "; ".join(details) + ")")

            for relative_name, member in members.items():
                actual = hashlib.sha256(package.read(member)).hexdigest()
                expected = expected_files[relative_name].lower()
                if actual != expected:
                    raise BundleError(
                        f"Bundle file {relative_name} has SHA-256 {actual}, expected {expected}"
                    )
    except zipfile.BadZipFile as exc:
        raise BundleError(f"Dependency archive is not a valid ZIP: {archive}") from exc
    return members


def stage_bundle(archive: Path, manifest: dict[str, Any], destination: Path) -> Path:
    bundle = manifest["bundle"]
    members = verify_archive(archive, bundle)
    if destination.exists():
        raise BundleError(f"Refusing to overwrite existing bundle destination: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        with zipfile.ZipFile(archive) as package:
            for relative_name in sorted(members):
                target = temporary / Path(relative_name)
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(members[relative_name]) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)

        metadata = {
            "schema_version": 1,
            "bundle": {
                key: bundle[key]
                for key in (
                    "name",
                    "version",
                    "architecture",
                    "release_tag",
                    "source_commit",
                    "archive_name",
                    "archive_url",
                    "archive_sha256",
                )
            },
            "components": manifest.get("components", []),
            "files": dict(sorted(bundle["files"].items())),
            "modified": False,
        }
        (temporary / "BUNDLE-METADATA.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        os.replace(temporary, destination)
        return destination
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def stage_source_artifacts(
    manifest: dict[str, Any],
    cache_dir: Path,
    destination: Path,
    licenses_dir: Path,
    offline: bool,
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    licenses_dir.mkdir(parents=True, exist_ok=True)
    source_records = []
    for source in manifest.get("source_artifacts", []):
        cached = acquire_file(
            name=f"{source['name']} source",
            url=source["url"],
            expected_sha256=source["sha256"],
            cache_path=cache_dir / source["filename"],
            offline=offline,
        )
        output = destination / source["filename"]
        shutil.copyfile(cached, output)
        license_member = source.get("license_member")
        license_output = source.get("license_output")
        if license_member and license_output:
            try:
                if cached.suffix.lower() == ".zip":
                    with zipfile.ZipFile(cached) as archive:
                        license_text = archive.read(license_member)
                else:
                    with tarfile.open(cached, mode="r:*") as archive:
                        member = archive.getmember(license_member)
                        if not member.isfile():
                            raise BundleError(
                                f"License member is not a regular file: {license_member}"
                            )
                        extracted = archive.extractfile(member)
                        if extracted is None:
                            raise BundleError(f"Could not read license member: {license_member}")
                        license_text = extracted.read()
            except (KeyError, tarfile.TarError, zipfile.BadZipFile) as exc:
                raise BundleError(
                    f"Could not extract {source['name']} license {license_member}: {exc}"
                ) from exc
            (licenses_dir / license_output).write_bytes(license_text)
        source_records.append(dict(source))
    (destination / "SOURCE-METADATA.json").write_text(
        json.dumps({"schema_version": 1, "sources": source_records}, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Acquire and stage the pinned scrcpy bundle")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--source-artifacts-dir", type=Path)
    parser.add_argument("--licenses-dir", type=Path)
    parser.add_argument("--offline", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = load_manifest(args.manifest)
        bundle = manifest["bundle"]
        archive = acquire_file(
            name=f"scrcpy {bundle['version']} {bundle['architecture']}",
            url=bundle["archive_url"],
            expected_sha256=bundle["archive_sha256"],
            cache_path=args.cache_dir / bundle["archive_name"],
            offline=args.offline,
        )
        stage_bundle(archive, manifest, args.destination)
        if args.source_artifacts_dir:
            if args.licenses_dir is None:
                raise BundleError("--licenses-dir is required with --source-artifacts-dir")
            stage_source_artifacts(
                manifest,
                args.cache_dir / "sources",
                args.source_artifacts_dir,
                args.licenses_dir,
                args.offline,
            )
    except BundleError as exc:
        print(f"Dependency staging failed: {exc}")
        return 1
    print(f"Staged verified scrcpy bundle at {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
