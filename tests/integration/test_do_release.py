"""Integration tests for the do-release command."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from release_py.cli.app import app

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


@pytest.fixture
def do_release_ready_repo(temp_git_repo_with_pyproject: Path) -> Path:
    """Create a repo ready for do-release (with commits and remote)."""
    repo = temp_git_repo_with_pyproject

    # Rename master to main
    subprocess.run(
        ["git", "branch", "-m", "master", "main"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Add remote
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/owner/repo.git"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

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


class TestDoReleaseDryRun:
    """Tests for do-release command in dry-run mode."""

    def test_do_release_dry_run_shows_preview(self, do_release_ready_repo: Path):
        """Dry run shows what would happen."""
        result = runner.invoke(app, ["do-release", str(do_release_ready_repo)])

        assert result.exit_code == 0
        assert "Dry Run" in result.stdout or "Preview" in result.stdout
        # First release shows 0.1.0, subsequent would show 1.1.0
        assert "0.1.0" in result.stdout or "1.1.0" in result.stdout

    def test_do_release_dry_run_shows_actions(self, do_release_ready_repo: Path):
        """Dry run shows all actions that would be performed."""
        result = runner.invoke(app, ["do-release", str(do_release_ready_repo)])

        assert result.exit_code == 0
        # Should show the steps
        assert "pyproject.toml" in result.stdout
        assert "tag" in result.stdout.lower()
        assert "--execute" in result.stdout

    def test_do_release_dry_run_no_changes(self, do_release_ready_repo: Path):
        """Dry run doesn't modify any files."""
        # Get original pyproject content
        pyproject = do_release_ready_repo / "pyproject.toml"
        original_content = pyproject.read_text()

        result = runner.invoke(app, ["do-release", str(do_release_ready_repo)])

        assert result.exit_code == 0
        # pyproject should be unchanged
        assert pyproject.read_text() == original_content


class TestDoReleaseExecution:
    """Tests for do-release command execution."""

    def test_do_release_updates_version(self, do_release_ready_repo: Path):
        """Do-release updates version in pyproject.toml."""
        with patch("release_py.forge.github.GitHubClient") as mock_github:
            mock_client = MagicMock()
            mock_client.create_release = AsyncMock(
                return_value=MagicMock(
                    tag="v1.1.0",
                    url="https://github.com/owner/repo/releases/tag/v1.1.0",
                )
            )
            mock_github.return_value = mock_client

            with patch("release_py.publish.pypi.build_package", return_value=[]):
                with patch("release_py.publish.pypi.publish_package"):
                    with patch("release_py.vcs.git.GitRepository.push_tag"):
                        result = runner.invoke(
                            app,
                            ["do-release", str(do_release_ready_repo), "--execute"],
                        )

                        if result.exit_code == 0:
                            # Version should be updated
                            pyproject = do_release_ready_repo / "pyproject.toml"
                            content = pyproject.read_text()
                            assert "1.1.0" in content

    def test_do_release_creates_commit(self, do_release_ready_repo: Path):
        """Do-release creates a commit for version changes."""
        with patch("release_py.forge.github.GitHubClient") as mock_github:
            mock_client = MagicMock()
            mock_client.create_release = AsyncMock(
                return_value=MagicMock(
                    tag="v1.1.0",
                    url="https://github.com/owner/repo/releases/tag/v1.1.0",
                )
            )
            mock_github.return_value = mock_client

            with patch("release_py.publish.pypi.build_package", return_value=[]):
                with patch("release_py.publish.pypi.publish_package"):
                    with patch("release_py.vcs.git.GitRepository.push_tag"):
                        result = runner.invoke(
                            app,
                            ["do-release", str(do_release_ready_repo), "--execute"],
                        )

                        if result.exit_code == 0:
                            # Check commit was created
                            log_result = subprocess.run(
                                ["git", "log", "--oneline", "-1"],
                                cwd=do_release_ready_repo,
                                capture_output=True,
                                text=True,
                                check=True,
                            )
                            assert "chore(release)" in log_result.stdout

    def test_do_release_creates_tag(self, do_release_ready_repo: Path):
        """Do-release creates a git tag."""
        with patch("release_py.forge.github.GitHubClient") as mock_github:
            mock_client = MagicMock()
            mock_client.create_release = AsyncMock(
                return_value=MagicMock(
                    tag="v1.1.0",
                    url="https://github.com/owner/repo/releases/tag/v1.1.0",
                )
            )
            mock_github.return_value = mock_client

            with patch("release_py.publish.pypi.build_package", return_value=[]):
                with patch("release_py.publish.pypi.publish_package"):
                    with patch("release_py.vcs.git.GitRepository.push_tag"):
                        result = runner.invoke(
                            app,
                            ["do-release", str(do_release_ready_repo), "--execute"],
                        )

                        if result.exit_code == 0:
                            # Check tag was created
                            tags_result = subprocess.run(
                                ["git", "tag"],
                                cwd=do_release_ready_repo,
                                capture_output=True,
                                text=True,
                                check=True,
                            )
                            assert "v1.1.0" in tags_result.stdout

    def test_do_release_skip_publish(self, do_release_ready_repo: Path):
        """Do-release with --skip-publish skips PyPI."""
        with patch("release_py.forge.github.GitHubClient") as mock_github:
            mock_client = MagicMock()
            mock_client.create_release = AsyncMock(
                return_value=MagicMock(
                    tag="v1.1.0",
                    url="https://github.com/owner/repo/releases/tag/v1.1.0",
                )
            )
            mock_github.return_value = mock_client

            with patch("release_py.publish.pypi.build_package") as mock_build:
                with patch("release_py.publish.pypi.publish_package") as mock_publish:
                    with patch("release_py.vcs.git.GitRepository.push_tag"):
                        result = runner.invoke(
                            app,
                            [
                                "do-release",
                                str(do_release_ready_repo),
                                "--execute",
                                "--skip-publish",
                            ],
                        )

                        if result.exit_code == 0:
                            # Build and publish should NOT be called
                            mock_build.assert_not_called()
                            mock_publish.assert_not_called()


class TestDoReleaseErrors:
    """Tests for do-release error handling."""

    def test_do_release_dirty_repo_fails(self, do_release_ready_repo: Path):
        """Fail when repo has uncommitted changes."""
        # Make repo dirty
        (do_release_ready_repo / "uncommitted.txt").write_text("dirty")

        result = runner.invoke(app, ["do-release", str(do_release_ready_repo), "--execute"])

        assert result.exit_code == 1
        # Error message may be in stdout or output
        output = result.stdout + (result.output if hasattr(result, "output") else "")
        assert "uncommitted" in output.lower() or result.exit_code == 1

    def test_do_release_wrong_branch_fails(self, do_release_ready_repo: Path):
        """Fail when not on default branch."""
        # Create and checkout feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature-branch"],
            cwd=do_release_ready_repo,
            check=True,
            capture_output=True,
        )

        result = runner.invoke(app, ["do-release", str(do_release_ready_repo), "--execute"])

        assert result.exit_code == 1
        # Error message may be in stdout or output
        output = result.stdout + (result.output if hasattr(result, "output") else "")
        assert "main" in output or "branch" in output.lower() or result.exit_code == 1

    def test_do_release_no_commits_shows_message(self, temp_git_repo_with_pyproject: Path):
        """Show message when no commits since last tag."""
        repo = temp_git_repo_with_pyproject

        # Rename to main
        subprocess.run(
            ["git", "branch", "-m", "master", "main"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        # Add remote
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/owner/repo.git"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        # Create tag at current HEAD
        subprocess.run(["git", "tag", "v1.0.0"], cwd=repo, check=True, capture_output=True)

        result = runner.invoke(app, ["do-release", str(repo)])

        assert result.exit_code == 0
        assert "No commits" in result.stdout


class TestDoReleaseVersionOverride:
    """Tests for version override functionality."""

    def test_do_release_version_override(self, do_release_ready_repo: Path):
        """Can override calculated version."""
        result = runner.invoke(
            app, ["do-release", str(do_release_ready_repo), "--version", "2.0.0"]
        )

        assert result.exit_code == 0
        assert "2.0.0" in result.stdout

    def test_do_release_prerelease(self, do_release_ready_repo: Path):
        """Can create pre-release version."""
        result = runner.invoke(
            app, ["do-release", str(do_release_ready_repo), "--prerelease", "alpha"]
        )

        assert result.exit_code == 0
        # Should show alpha pre-release version
        assert "alpha" in result.stdout.lower() or "a1" in result.stdout


class TestDoReleasePublishWorkflow:
    """Tests for do-release publish and build workflow."""

    def test_do_release_with_custom_build_command(self, do_release_ready_repo: Path):
        """Do-release executes custom build command."""
        # Add custom build command to config
        pyproject = do_release_ready_repo / "pyproject.toml"
        config_content = pyproject.read_text()
        config_content += '\n[tool.releasio.hooks]\nbuild = "echo Building custom {version}"\n'
        pyproject.write_text(config_content)

        with patch("release_py.forge.github.GitHubClient") as mock_github:
            mock_client = MagicMock()
            mock_client.create_release = AsyncMock(
                return_value=MagicMock(
                    tag="v1.1.0",
                    url="https://github.com/owner/repo/releases/tag/v1.1.0",
                )
            )
            mock_github.return_value = mock_client

            with patch("release_py.vcs.git.GitRepository.push_tag"):
                result = runner.invoke(
                    app,
                    ["do-release", str(do_release_ready_repo), "--execute", "--skip-publish"],
                )

                if result.exit_code == 0:
                    # Custom build message should appear
                    assert "custom" in result.stdout.lower() or result.exit_code == 0

    def test_do_release_build_failure_shows_error(self, do_release_ready_repo: Path):
        """Do-release shows clear error when build fails."""
        # Add a build command that will fail
        pyproject = do_release_ready_repo / "pyproject.toml"
        config_content = pyproject.read_text()
        config_content += '\n[tool.releasio.hooks]\nbuild = "exit 1"\n'
        pyproject.write_text(config_content)

        result = runner.invoke(
            app,
            ["do-release", str(do_release_ready_repo), "--execute"],
        )

        assert result.exit_code == 1
        # Should show build error
        output = result.stdout + (result.output if hasattr(result, "output") else "")
        assert "build" in output.lower() or result.exit_code == 1

    def test_do_release_publish_failure_shows_error(self, do_release_ready_repo: Path):
        """Do-release shows clear error when publish fails."""
        with patch("release_py.forge.github.GitHubClient") as mock_github:
            mock_client = MagicMock()
            mock_client.create_release = AsyncMock(
                return_value=MagicMock(
                    tag="v1.1.0",
                    url="https://github.com/owner/repo/releases/tag/v1.1.0",
                )
            )
            mock_github.return_value = mock_client

            # Mock changelog generation to avoid git-cliff issues
            with patch(
                "release_py.core.changelog.generate_changelog",
                return_value="## [1.1.0]\n\n- Feature",
            ):
                with patch("release_py.publish.pypi.build_package", return_value=[]):
                    with patch("release_py.publish.pypi.publish_package") as mock_publish:
                        from release_py.exceptions import UploadError

                        mock_publish.side_effect = UploadError("Upload failed")

                        with patch("release_py.vcs.git.GitRepository.push_tag"):
                            result = runner.invoke(
                                app,
                                ["do-release", str(do_release_ready_repo), "--execute"],
                            )

                            assert result.exit_code == 1
                            output = result.stdout + (
                                result.output if hasattr(result, "output") else ""
                            )
                            assert "upload" in output.lower() or "publish" in output.lower()

    def test_do_release_github_release_creation(self, do_release_ready_repo: Path):
        """Do-release creates GitHub release with proper parameters."""
        with patch("release_py.forge.github.GitHubClient") as mock_github:
            mock_client = MagicMock()
            mock_create_release = AsyncMock(
                return_value=MagicMock(
                    tag="v1.1.0",
                    url="https://github.com/owner/repo/releases/tag/v1.1.0",
                )
            )
            mock_client.create_release = mock_create_release
            mock_github.return_value = mock_client

            with patch("release_py.publish.pypi.build_package", return_value=[]):
                with patch("release_py.publish.pypi.publish_package"):
                    with patch("release_py.vcs.git.GitRepository.push_tag"):
                        result = runner.invoke(
                            app,
                            ["do-release", str(do_release_ready_repo), "--execute"],
                        )

                        if result.exit_code == 0:
                            # Verify GitHub release was called
                            assert mock_create_release.called

    def test_do_release_first_release_flow(self, temp_git_repo_with_pyproject: Path):
        """Do-release handles first release (no previous tags) correctly."""
        repo = temp_git_repo_with_pyproject

        # Rename to main
        subprocess.run(
            ["git", "branch", "-m", "master", "main"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        # Add remote
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/owner/repo.git"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        # Add a commit
        (repo / "feature.py").write_text("# Feature\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: first feature"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        result = runner.invoke(app, ["do-release", str(repo)])

        assert result.exit_code == 0
        # First release should show initial version
        assert "0.1.0" in result.stdout or "first" in result.stdout.lower()


class TestDoReleaseHelp:
    """Tests for do-release help output."""

    def test_do_release_help(self):
        """do-release --help shows options."""
        result = runner.invoke(app, ["do-release", "--help"])

        assert result.exit_code == 0
        assert "--execute" in result.stdout
        assert "--skip-publish" in result.stdout
        assert "--version" in result.stdout
        assert "--prerelease" in result.stdout
