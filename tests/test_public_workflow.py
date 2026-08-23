# SPDX-License-Identifier: GPL-3.0-only

"""Safety checks for the public snapshot workflow."""

from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "packaging" / "Publish-PublicSnapshot.ps1"
DOC = Path(__file__).parents[1] / "docs" / "public-workflow.md"


def test_publisher_requires_explicit_refs_and_publish_mode():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "[Parameter(Mandatory = $true)]" in text
    assert "[string] $SourceRef" in text
    assert "[string] $DestinationRef" in text
    assert "Choose -DryRun or -Publish" in text
    assert "HEAD:$DestinationRef" in text


def test_publisher_rejects_master_force_and_unrelated_repositories():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'if ($SourceRef -eq "master"' in text
    assert "ExpectedRepository" in text
    assert '"--force"' not in text
    assert "git push" in text


def test_publisher_uses_tracked_content_and_checks_release_version():
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"ls-tree", "-r", "--name-only"' in text
    assert '"archive", "--format=zip"' in text
    assert "APP_VERSION" in text
    assert "Refusing to alter existing release tag" in text


def test_workflow_documents_separate_histories_and_artifacts():
    text = DOC.read_text(encoding="utf-8")
    for phrase in ("unrelated histories", "Dependabot", "Release artifacts", "git push public"):
        assert phrase in text
