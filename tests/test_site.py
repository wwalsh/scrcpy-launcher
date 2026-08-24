# SPDX-License-Identifier: GPL-3.0-only

import re
import unittest
from pathlib import Path

from src.version import APP_VERSION


SITE = Path(__file__).parents[1] / "site"


class SiteTests(unittest.TestCase):
    def test_required_files_and_assets(self) -> None:
        for name in (
            "index.html",
            "styles.css",
            "404.html",
            "robots.txt",
            "sitemap.xml",
            "_headers",
        ):
            self.assertTrue((SITE / name).is_file())
        for name in (
            "icon.ico",
            "settings-overview-generated.png",
            "app-selector-generated.png",
        ):
            self.assertTrue((SITE / "assets" / name).is_file())

    def test_links_headers_and_no_dependencies(self) -> None:
        html = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("<script", html.lower())
        self.assertIsNone(
            re.search(r"cdn|unpkg|googletagmanager|analytics|cookie", html, re.I)
        )
        for reference in re.findall(r'(?:src|href)="([^"]+)"', html):
            if not reference.startswith(("http://", "https://", "#")):
                self.assertTrue((SITE / reference.split("#")[0]).is_file())

        headers = (SITE / "_headers").read_text(encoding="utf-8")
        for value in (
            "Content-Security-Policy",
            "script-src 'none'",
            "X-Content-Type-Options",
            "Referrer-Policy",
            "Permissions-Policy",
            "X-Frame-Options",
        ):
            self.assertIn(value, headers)

    def test_metadata_project_disclosures_and_current_version(self) -> None:
        html = (SITE / "index.html").read_text(encoding="utf-8")
        for value in (
            "canonical",
            "og:title",
            "https://scrcpy-launcher.link/",
            "releases/latest",
            "docs/user-guide.md",
            "SECURITY.md",
            "THIRD-PARTY-NOTICES.md",
            "issues",
            "LICENSE",
            "scrcpy 4.1",
            "not the official scrcpy project",
            "SHA-256",
            "Authenticode",
        ):
            self.assertIn(value, html)
        self.assertIn(f"Current release: v{APP_VERSION}", html)


if __name__ == "__main__":
    unittest.main()
