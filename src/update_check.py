# SPDX-License-Identifier: GPL-3.0-only

"""Bounded, user-initiated checks for the latest GitHub release."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


LATEST_RELEASE_API = (
    "https://api.github.com/repos/wwalsh/scrcpy-launcher/releases/latest"
)
GITHUB_API_VERSION = "2026-03-10"
DEFAULT_TIMEOUT_SECONDS = 8.0
MAX_RESPONSE_BYTES = 256 * 1024

_VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?$")


class UpdateCheckError(RuntimeError):
    """A controlled failure while checking the public release feed."""


@dataclass(frozen=True)
class UpdateResult:
    """Comparison between the running version and GitHub's latest release."""

    current_version: str
    latest_version: str
    update_available: bool


def _parse_version(value: str) -> tuple[int, int, int, int]:
    match = _VERSION_PATTERN.fullmatch(value.strip())
    if match is None:
        raise UpdateCheckError(f"Unsupported release version: {value!r}")
    parts = [int(part) if part is not None else 0 for part in match.groups()]
    return parts[0], parts[1], parts[2], parts[3]


def check_latest_release(
    current_version: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> UpdateResult:
    """Return the latest stable release comparison from GitHub."""
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    current = _parse_version(current_version)
    request = Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"scrcpy-launcher/{current_version}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > MAX_RESPONSE_BYTES:
                raise UpdateCheckError("GitHub returned an unexpectedly large response.")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except UpdateCheckError:
        raise
    except HTTPError as exc:
        raise UpdateCheckError(f"GitHub returned HTTP {exc.code}.") from exc
    except (OSError, URLError, ValueError) as exc:
        raise UpdateCheckError(f"Could not contact GitHub: {exc}") from exc

    if len(raw) > MAX_RESPONSE_BYTES:
        raise UpdateCheckError("GitHub returned an unexpectedly large response.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateCheckError("GitHub returned an invalid release response.") from exc

    tag_name = payload.get("tag_name") if isinstance(payload, dict) else None
    if not isinstance(tag_name, str) or not tag_name.strip():
        raise UpdateCheckError("GitHub's release response did not include a version tag.")

    latest = _parse_version(tag_name)
    latest_version = tag_name.strip().removeprefix("v")
    return UpdateResult(
        current_version=current_version,
        latest_version=latest_version,
        update_available=latest > current,
    )
