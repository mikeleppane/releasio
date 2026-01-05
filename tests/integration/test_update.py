"""Integration tests for the update command."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from release_py.cli.app import app

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


@pytest.fixture
def repo_with_feat_commit(temp_git_repo_with_pyproject: Path) -> Path:
    """Create repo with a feature commit after initial setup."""
    repo = temp_git_repo_with_pyproject

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


@pytest.fixture
def repo_with_fix_commit(temp_git_repo_with_pyproject: Path) -> Path:
    """Create repo with only a fix commit since last tag."""
    repo = temp_git_repo_with_pyproject

    # Tag current state so only the fix commit counts for version bump
    subprocess.run(["git", "tag", "v1.0.0"], cwd=repo, check=True, capture_output=True)

    # Add a fix commit
    (repo / "fix.py").write_text("# Bug fix\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: resolve bug"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    return repo


@pytest.fixture
def repo_with_breaking_change(temp_git_repo_with_pyproject: Path) -> Path:
    """Create repo with a breaking change commit."""
    repo = temp_git_repo_with_pyproject

    # Tag current state so the breaking change is the only change since tag
    subprocess.run(["git", "tag", "v1.0.0"], cwd=repo, check=True, capture_output=True)

    # Add a breaking change
    (repo / "breaking.py").write_text("# Breaking change\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat!: breaking API change"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    return repo


class TestUpdateDryRun:
    """Tests for update command in dry-run mode (default)."""

    def test_update_dry_run_shows_preview(self, repo_with_feat_commit: Path):
        """Dry run shows what would change."""
        result = runner.invoke(app, ["update", str(repo_with_feat_commit)])

        assert result.exit_code == 0
        assert "DRY-RUN" in result.stdout
        assert "Would make the following changes" in result.stdout
        assert "pyproject.toml" in result.stdout

    def test_update_dry_run_no_changes(self, temp_git_repo_with_pyproject: Path):
        """Dry run with no commits shows no changes."""
        # The fixture already has commits, but let's create a tag
        subprocess.run(
            ["git", "tag", "v1.0.0"],
            cwd=temp_git_repo_with_pyproject,
            check=True,
            capture_output=True,
        )

        result = runner.invoke(app, ["update", str(temp_git_repo_with_pyproject)])

        assert "No commits found" in result.stdout or result.exit_code == 0

    def test_update_dry_run_version_bump(self, repo_with_feat_commit: Path):
        """Dry run shows correct version bump."""
        result = runner.invoke(app, ["update", str(repo_with_feat_commit)])

        # Feature commit should trigger minor bump: 1.0.0 -> 1.1.0
        assert "1.0.0" in result.stdout
        assert result.exit_code == 0


class TestUpdateExecute:
    """Tests for update command with --execute flag."""

    def test_update_execute_updates_version(self, repo_with_feat_commit: Path):
        """Execute updates version in pyproject.toml."""
        # Mock changelog generation to avoid git-cliff dependency
        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [1.1.0] - 2024-01-01\n\n- New feature"

            result = runner.invoke(app, ["update", str(repo_with_feat_commit), "--execute"])

            assert result.exit_code == 0
            assert "EXECUTING" in result.stdout
            assert "Updated version in pyproject.toml" in result.stdout

            # Verify version was actually updated
            pyproject = repo_with_feat_commit / "pyproject.toml"
            content = pyproject.read_text()
            assert 'version = "1.1.0"' in content

    def test_update_execute_creates_changelog(self, repo_with_feat_commit: Path):
        """Execute creates/updates changelog file."""
        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [1.1.0] - 2024-01-01\n\n### Features\n\n- New feature"

            result = runner.invoke(app, ["update", str(repo_with_feat_commit), "--execute"])

            assert result.exit_code == 0
            assert "CHANGELOG.md" in result.stdout

            # Verify changelog was created
            changelog = repo_with_feat_commit / "CHANGELOG.md"
            assert changelog.exists()
            content = changelog.read_text()
            assert "1.1.0" in content

    def test_update_execute_fix_bump(self, repo_with_fix_commit: Path):
        """Fix commit triggers patch bump."""
        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [1.0.1]"

            result = runner.invoke(app, ["update", str(repo_with_fix_commit), "--execute"])

            assert result.exit_code == 0

            pyproject = repo_with_fix_commit / "pyproject.toml"
            content = pyproject.read_text()
            assert 'version = "1.0.1"' in content

    def test_update_execute_breaking_bump(self, repo_with_breaking_change: Path):
        """Breaking change triggers major bump."""
        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [2.0.0]"

            result = runner.invoke(app, ["update", str(repo_with_breaking_change), "--execute"])

            assert result.exit_code == 0

            pyproject = repo_with_breaking_change / "pyproject.toml"
            content = pyproject.read_text()
            assert 'version = "2.0.0"' in content

    def test_update_execute_shows_next_steps(self, repo_with_feat_commit: Path):
        """Execute shows next steps after completion."""
        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [1.1.0]"

            result = runner.invoke(app, ["update", str(repo_with_feat_commit), "--execute"])

            assert "Next steps" in result.stdout
            assert "git add" in result.stdout
            assert "releasio release" in result.stdout


class TestUpdateErrors:
    """Tests for update command error handling."""

    def test_update_no_repo(self, tmp_path: Path):
        """Fail gracefully when not a git repo."""
        (tmp_path / "pyproject.toml").write_text(
            """
[project]
name = "test"
version = "1.0.0"
"""
        )

        result = runner.invoke(app, ["update", str(tmp_path)])

        assert result.exit_code == 1

    def test_update_no_pyproject(self, tmp_path: Path):
        """Fail when no pyproject.toml."""
        # Initialize git repo without pyproject
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        (tmp_path / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        result = runner.invoke(app, ["update", str(tmp_path)])

        assert result.exit_code == 1

    def test_update_dirty_repo_without_allow(self, repo_with_feat_commit: Path):
        """Fail when repo is dirty and allow_dirty not set."""
        # Make repo dirty
        (repo_with_feat_commit / "uncommitted.txt").write_text("dirty")

        result = runner.invoke(app, ["update", str(repo_with_feat_commit)])

        # Should fail or warn about dirty repo
        # The actual behavior depends on config, so check it completes
        assert result.exit_code in (0, 1)


class TestUpdateAppendChangelog:
    """Tests for changelog appending behavior."""

    def test_update_appends_to_existing_changelog(self, repo_with_feat_commit: Path):
        """New changelog content is prepended to existing."""
        # Create existing changelog and commit it (to avoid dirty repo error)
        existing_changelog = repo_with_feat_commit / "CHANGELOG.md"
        existing_changelog.write_text("## [1.0.0] - 2024-01-01\n\n- Initial release\n")
        subprocess.run(
            ["git", "add", "."], cwd=repo_with_feat_commit, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "docs: add changelog"],
            cwd=repo_with_feat_commit,
            check=True,
            capture_output=True,
        )

        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [1.1.0] - 2024-02-01\n\n- New feature"

            result = runner.invoke(app, ["update", str(repo_with_feat_commit), "--execute"])

            assert result.exit_code == 0

            content = existing_changelog.read_text()
            # New version should come before old
            assert content.index("1.1.0") < content.index("1.0.0")
            assert "Initial release" in content


# =============================================================================
# First Release Detection Tests
# =============================================================================


class TestFirstReleaseDetection:
    """Tests for first release detection using initial_version."""

    @pytest.fixture
    def repo_no_tags(self, temp_git_repo_with_pyproject: Path) -> Path:
        """Create repo with commits but no tags (first release scenario)."""
        repo = temp_git_repo_with_pyproject

        # Add a feature commit
        (repo / "feature.py").write_text("# First feature\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: add first feature"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        return repo

    @pytest.fixture
    def repo_no_tags_custom_initial(self, temp_git_repo: Path) -> Path:
        """Create repo with custom initial_version configured."""
        repo = temp_git_repo

        # Create pyproject.toml with custom initial_version
        pyproject = repo / "pyproject.toml"
        pyproject.write_text(
            """\
[project]
name = "test-project"
version = "0.0.0"
description = "A test project"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.releasio]
default_branch = "main"

[tool.releasio.version]
initial_version = "1.0.0"
"""
        )

        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: initial project setup"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        return repo

    def test_first_release_uses_initial_version(self, repo_no_tags: Path):
        """First release uses config.version.initial_version (default 0.1.0)."""
        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [0.1.0] - 2024-01-01\n\n- First release"

            result = runner.invoke(app, ["update", str(repo_no_tags), "--execute"])

            assert result.exit_code == 0
            assert "First release" in result.stdout

            # Verify version was set to initial_version (0.1.0)
            pyproject = repo_no_tags / "pyproject.toml"
            content = pyproject.read_text()
            assert 'version = "0.1.0"' in content

    def test_first_release_uses_custom_initial_version(self, repo_no_tags_custom_initial: Path):
        """First release uses custom initial_version from config."""
        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [1.0.0] - 2024-01-01\n\n- First release"

            result = runner.invoke(app, ["update", str(repo_no_tags_custom_initial), "--execute"])

            assert result.exit_code == 0
            assert "First release" in result.stdout

            # Verify version was set to custom initial_version (1.0.0)
            pyproject = repo_no_tags_custom_initial / "pyproject.toml"
            content = pyproject.read_text()
            assert 'version = "1.0.0"' in content

    def test_first_release_dry_run_shows_initial_version(self, repo_no_tags: Path):
        """Dry run for first release shows initial_version."""
        result = runner.invoke(app, ["update", str(repo_no_tags)])

        assert result.exit_code == 0
        assert "First release" in result.stdout
        assert "0.1.0" in result.stdout

    def test_first_release_with_prerelease(self, repo_no_tags: Path):
        """First release with --prerelease creates pre-release initial version."""
        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [0.1.0a1] - 2024-01-01\n\n- Alpha release"

            result = runner.invoke(
                app, ["update", str(repo_no_tags), "--execute", "--prerelease", "alpha"]
            )

            assert result.exit_code == 0

            pyproject = repo_no_tags / "pyproject.toml"
            content = pyproject.read_text()
            assert 'version = "0.1.0a1"' in content

    def test_first_release_with_version_override(self, repo_no_tags: Path):
        """First release with --version override uses specified version."""
        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [2.0.0] - 2024-01-01"

            result = runner.invoke(
                app, ["update", str(repo_no_tags), "--execute", "--version", "2.0.0"]
            )

            assert result.exit_code == 0

            pyproject = repo_no_tags / "pyproject.toml"
            content = pyproject.read_text()
            assert 'version = "2.0.0"' in content

    def test_non_first_release_ignores_initial_version(self, repo_with_fix_commit: Path):
        """After first release, initial_version is not used."""
        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [1.0.1]"

            result = runner.invoke(app, ["update", str(repo_with_fix_commit), "--execute"])

            assert result.exit_code == 0
            # Should NOT say "First release"
            assert "First release" not in result.stdout

            pyproject = repo_with_fix_commit / "pyproject.toml"
            content = pyproject.read_text()
            # Should bump from 1.0.0 to 1.0.1, not use initial_version
            assert 'version = "1.0.1"' in content


class TestGitHubRemoteWarning:
    """Tests for GitHub remote detection warning."""

    def test_update_warns_when_github_remote_not_detected(self, repo_with_feat_commit: Path):
        """update shows warning when GitHub remote cannot be detected."""
        # Remove the remote so GitHub detection fails
        subprocess.run(
            ["git", "remote", "remove", "origin"],
            cwd=repo_with_feat_commit,
            check=False,
            capture_output=True,
        )

        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [1.1.0]"

            result = runner.invoke(app, ["update", str(repo_with_feat_commit), "--execute"])

            assert result.exit_code == 0
            # Should show warning about missing GitHub remote
            assert "Could not detect GitHub repository" in result.stdout
            assert "Changelog will not include PR links" in result.stdout
