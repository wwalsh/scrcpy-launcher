# SPDX-License-Identifier: GPL-3.0-only
import re
from pathlib import Path
SITE=Path(__file__).parents[1]/"site"
def test_required_files_and_assets():
    for n in ("index.html","styles.css","404.html","robots.txt","sitemap.xml","_headers"): assert (SITE/n).is_file()
    for n in ("icon.ico","settings-overview-generated.png","app-selector-generated.png"): assert (SITE/"assets"/n).is_file()
def test_links_headers_and_no_dependencies():
    h=(SITE/"index.html").read_text(encoding="utf-8")
    assert "<script" not in h.lower()
    assert not re.search(r"cdn|unpkg|googletagmanager|analytics|cookie",h,re.I)
    for r in re.findall(r'(?:src|href)="([^"]+)"',h):
        if not r.startswith(("http://","https://","#")): assert (SITE/r.split("#")[0]).is_file()
    x=(SITE/"_headers").read_text(encoding="utf-8")
    for v in ("Content-Security-Policy","script-src 'none'","X-Content-Type-Options","Referrer-Policy","Permissions-Policy","X-Frame-Options"): assert v in x
def test_metadata_and_project_disclosures():
    h=(SITE/"index.html").read_text(encoding="utf-8")
    for v in ("canonical","og:title","https://scrcpy-launcher.link/","releases/latest","docs/user-guide.md","SECURITY.md","THIRD-PARTY-NOTICES.md","issues","LICENSE","scrcpy 4.1","not the official scrcpy project","SHA-256","Authenticode"): assert v in h
