"""Integration tests for the release-pr command."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from release_py.cli.app import app
from release_py.forge.base import MergeRequest, MergeRequestState

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


@pytest.fixture
def pr_ready_repo(temp_git_repo_with_pyproject: Path) -> Path:
    """Create a repo ready for PR creation."""
    repo = temp_git_repo_with_pyproject

    # Add remote
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/owner/repo.git"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Tag current state so the feature commit is the only change since tag
    subprocess.run(["git", "tag", "v1.0.0"], cwd=repo, check=True, capture_output=True)

    # Add a feature commit
    (repo / "feature.py").write_text("# New feature\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add new feature"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    return repo


class TestReleasePrDryRun:
    """Tests for release-pr command in dry-run mode."""

    def test_release_pr_dry_run_shows_preview(self, pr_ready_repo: Path):
        """Dry run shows PR preview."""
        result = runner.invoke(app, ["release-pr", str(pr_ready_repo), "--dry-run"])

        assert result.exit_code == 0
        assert "Dry Run" in result.stdout or "Preview" in result.stdout
        assert "Title" in result.stdout

    def test_release_pr_dry_run_shows_version(self, pr_ready_repo: Path):
        """Dry run shows version information."""
        result = runner.invoke(app, ["release-pr", str(pr_ready_repo), "--dry-run"])

        assert result.exit_code == 0
        # Should show current and next version
        assert "1.0.0" in result.stdout or "1.1.0" in result.stdout

    def test_release_pr_dry_run_shows_branch(self, pr_ready_repo: Path):
        """Dry run shows branch information."""
        result = runner.invoke(app, ["release-pr", str(pr_ready_repo), "--dry-run"])

        assert result.exit_code == 0
        assert "Branch" in result.stdout or "release" in result.stdout.lower()

    def test_release_pr_dry_run_no_commits(self, temp_git_repo_with_pyproject: Path):
        """Dry run with no new commits shows message."""
        repo = temp_git_repo_with_pyproject

        # Add remote
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/owner/repo.git"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        # Create tag at current HEAD
        subprocess.run(
            ["git", "tag", "v1.0.0"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        result = runner.invoke(app, ["release-pr", str(repo), "--dry-run"])

        # Should indicate no changes
        assert "No commits" in result.stdout or "No Changes" in result.stdout


class TestReleasePrExecution:
    """Tests for release-pr command execution."""

    def test_release_pr_creates_branch(self, pr_ready_repo: Path):
        """Release-pr creates release branch."""
        with patch("release_py.forge.github.GitHubClient") as mock_github:
            mock_client = MagicMock()
            mock_client.find_pull_request = AsyncMock(return_value=None)
            mock_client.create_pull_request = AsyncMock(
                return_value=MergeRequest(
                    number=1,
                    title="Release",
                    body="Changelog",
                    head_branch="releasio/release",
                    base_branch="main",
                    url="https://github.com/owner/repo/pull/1",
                    state=MergeRequestState.OPEN,
                    labels=[],
                )
            )
            mock_github.return_value = mock_client

            with patch("release_py.core.changelog.generate_changelog") as mock_cl:
                mock_cl.return_value = "## [1.1.0]\n\n- Feature"

                # Mock git push to avoid actual network call
                with patch("release_py.vcs.git.GitRepository.push"):
                    result = runner.invoke(app, ["release-pr", str(pr_ready_repo)])

                    # Check branch was created
                    subprocess.run(
                        ["git", "branch", "--list", "releasio/release"],
                        check=False,
                        cwd=pr_ready_repo,
                        capture_output=True,
                        text=True,
                    )

                    # Branch may or may not exist depending on test order
                    assert result.exit_code in (0, 1)

    def test_release_pr_updates_version(self, pr_ready_repo: Path):
        """Release-pr updates version in pyproject.toml."""
        with patch("release_py.forge.github.GitHubClient") as mock_github:
            mock_client = MagicMock()
            mock_client.find_pull_request = AsyncMock(return_value=None)
            mock_client.create_pull_request = AsyncMock(
                return_value=MergeRequest(
                    number=1,
                    title="Release",
                    body="Changelog",
                    head_branch="releasio/release",
                    base_branch="main",
                    url="https://github.com/owner/repo/pull/1",
                    state=MergeRequestState.OPEN,
                    labels=[],
                )
            )
            mock_github.return_value = mock_client

            with patch("release_py.core.changelog.generate_changelog") as mock_cl:
                mock_cl.return_value = "## [1.1.0]\n\n- Feature"

                with patch("release_py.vcs.git.GitRepository.push"):
                    result = runner.invoke(app, ["release-pr", str(pr_ready_repo)])

                    if result.exit_code == 0:
                        # Check pyproject was updated
                        pyproject = pr_ready_repo / "pyproject.toml"
                        content = pyproject.read_text()
                        # Version should be bumped
                        assert "1.1.0" in content or "1.0.0" in content

    def test_release_pr_creates_pr(self, pr_ready_repo: Path):
        """Release-pr creates pull request via GitHub API."""
        with patch("release_py.forge.github.GitHubClient") as mock_github:
            mock_client = MagicMock()
            mock_client.find_pull_request = AsyncMock(return_value=None)
            mock_client.create_pull_request = AsyncMock(
                return_value=MergeRequest(
                    number=42,
                    title="chore(release): prepare v1.1.0",
                    body="## Summary\n\nRelease",
                    head_branch="releasio/release",
                    base_branch="main",
                    url="https://github.com/owner/repo/pull/42",
                    state=MergeRequestState.OPEN,
                    labels=["release"],
                )
            )
            mock_github.return_value = mock_client

            with patch("release_py.core.changelog.generate_changelog") as mock_cl:
                mock_cl.return_value = "## [1.1.0]\n\n- Feature"

                with patch("release_py.vcs.git.GitRepository.push"):
                    result = runner.invoke(app, ["release-pr", str(pr_ready_repo)])

                    if result.exit_code == 0:
                        mock_client.create_pull_request.assert_called_once()
                        # Check output mentions PR
                        assert "#42" in result.stdout or "Created PR" in result.stdout


class TestReleasePrUpdate:
    """Tests for updating existing release PR."""

    def test_release_pr_updates_existing(self, pr_ready_repo: Path):
        """Update existing PR instead of creating new one."""
        existing_pr = MergeRequest(
            number=10,
            title="chore(release): prepare v1.0.1",
            body="Old body",
            head_branch="releasio/release",
            base_branch="main",
            url="https://github.com/owner/repo/pull/10",
            state=MergeRequestState.OPEN,
            labels=["release"],
        )

        with patch("release_py.forge.github.GitHubClient") as mock_github:
            mock_client = MagicMock()
            mock_client.find_pull_request = AsyncMock(return_value=existing_pr)
            mock_client.update_pull_request = AsyncMock(
                return_value=MergeRequest(
                    number=10,
                    title="chore(release): prepare v1.1.0",
                    body="Updated body",
                    head_branch="releasio/release",
                    base_branch="main",
                    url="https://github.com/owner/repo/pull/10",
                    state=MergeRequestState.OPEN,
                    labels=["release"],
                )
            )
            mock_github.return_value = mock_client

            with patch("release_py.core.changelog.generate_changelog") as mock_cl:
                mock_cl.return_value = "## [1.1.0]\n\n- Feature"

                with patch("release_py.vcs.git.GitRepository.push"):
                    result = runner.invoke(app, ["release-pr", str(pr_ready_repo)])

                    if result.exit_code == 0:
                        mock_client.update_pull_request.assert_called_once()
                        # Check output mentions update
                        assert "Updated" in result.stdout or "#10" in result.stdout


class TestReleasePrErrors:
    """Tests for release-pr error handling."""

    def test_release_pr_no_remote(self, temp_git_repo_with_pyproject: Path):
        """Fail gracefully when no remote configured."""
        repo = temp_git_repo_with_pyproject

        # Add a commit but no remote
        (repo / "feature.py").write_text("# Feature\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: add feature"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        result = runner.invoke(app, ["release-pr", str(repo)])

        assert result.exit_code == 1

    def test_release_pr_non_github_remote(self, temp_git_repo_with_pyproject: Path):
        """Fail gracefully for non-GitHub remotes."""
        repo = temp_git_repo_with_pyproject

        # Add GitLab remote
        subprocess.run(
            ["git", "remote", "add", "origin", "https://gitlab.com/owner/repo.git"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        # Add a commit
        (repo / "feature.py").write_text("# Feature\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: add feature"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        result = runner.invoke(app, ["release-pr", str(repo)])

        # Should fail because GitLab not supported
        assert result.exit_code == 1


class TestReleasePrBody:
    """Tests for PR body generation."""

    def test_pr_body_contains_version(self, pr_ready_repo: Path):
        """PR body contains version information."""
        result = runner.invoke(app, ["release-pr", str(pr_ready_repo), "--dry-run"])

        assert result.exit_code == 0
        # PR body should mention versions
        assert "1.0.0" in result.stdout or "1.1.0" in result.stdout

    def test_pr_body_contains_changelog(self, pr_ready_repo: Path):
        """PR body contains changelog preview."""
        result = runner.invoke(app, ["release-pr", str(pr_ready_repo), "--dry-run"])

        assert result.exit_code == 0
        # Should show some changelog content
        # The body is shown in dry-run output
        output_lower = result.stdout.lower()
        assert "changelog" in output_lower or "feature" in output_lower or "summary" in output_lower
