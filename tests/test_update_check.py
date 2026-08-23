# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

from src.update_check import (
    GITHUB_API_VERSION,
    LATEST_RELEASE_API,
    MAX_RESPONSE_BYTES,
    UpdateCheckError,
    check_latest_release,
)


class _Response:
    def __init__(self, body: bytes, *, content_length: str | None = None) -> None:
        self._body = body
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = content_length

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self._body[:limit]


def _release(tag: str) -> bytes:
    return json.dumps({"tag_name": tag}).encode("utf-8")


class UpdateCheckTests(unittest.TestCase):
    @patch("src.update_check.urlopen")
    def test_newer_release_is_reported_and_request_is_identified(self, urlopen) -> None:
        urlopen.return_value = _Response(_release("v0.8.0"))

        result = check_latest_release("0.7.1", timeout=3)

        self.assertTrue(result.update_available)
        self.assertEqual(result.latest_version, "0.8.0")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, LATEST_RELEASE_API)
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("User-agent"), "scrcpy-launcher/0.7.1")
        self.assertEqual(request.get_header("X-github-api-version"), GITHUB_API_VERSION)
        urlopen.assert_called_once_with(request, timeout=3)

    @patch("src.update_check.urlopen")
    def test_equal_or_older_release_is_not_an_update(self, urlopen) -> None:
        urlopen.side_effect = [
            _Response(_release("v0.7.1")),
            _Response(_release("v0.6.0")),
        ]

        self.assertFalse(check_latest_release("0.7.1").update_available)
        self.assertFalse(check_latest_release("0.7.1").update_available)

    @patch("src.update_check.urlopen")
    def test_rejects_invalid_or_missing_version_tags(self, urlopen) -> None:
        urlopen.side_effect = [
            _Response(_release("latest")),
            _Response(b"{}"),
        ]

        with self.assertRaisesRegex(UpdateCheckError, "Unsupported release version"):
            check_latest_release("0.7.1")
        with self.assertRaisesRegex(UpdateCheckError, "did not include a version tag"):
            check_latest_release("0.7.1")

    @patch("src.update_check.urlopen")
    def test_rejects_oversized_responses_before_or_during_read(self, urlopen) -> None:
        urlopen.side_effect = [
            _Response(b"{}", content_length=str(MAX_RESPONSE_BYTES + 1)),
            _Response(b"x" * (MAX_RESPONSE_BYTES + 1)),
        ]

        for _ in range(2):
            with self.assertRaisesRegex(UpdateCheckError, "unexpectedly large"):
                check_latest_release("0.7.1")

    @patch("src.update_check.urlopen", side_effect=URLError("offline"))
    def test_network_failures_are_controlled(self, _urlopen) -> None:
        with self.assertRaisesRegex(UpdateCheckError, "Could not contact GitHub"):
            check_latest_release("0.7.1")

    def test_timeout_and_current_version_are_validated_before_network(self) -> None:
        with self.assertRaises(ValueError):
            check_latest_release("0.7.1", timeout=0)
        with self.assertRaises(UpdateCheckError):
            check_latest_release("development")


if __name__ == "__main__":
    unittest.main()
