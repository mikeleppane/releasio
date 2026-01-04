"""Shared test fixtures for release-py."""

from __future__ import annotations

import subprocess
from datetime import datetime
from typing import TYPE_CHECKING

import pytest

from release_py.config.models import CommitsConfig, ReleasePyConfig
from release_py.vcs.git import Commit

if TYPE_CHECKING:
    from pathlib import Path


# =============================================================================
# Commit Fixtures
# =============================================================================


@pytest.fixture
def sample_commits() -> list[Commit]:
    """Create sample commits for testing."""
    now = datetime.now()
    return [
        Commit(
            sha="abc1234567890",
            message="feat: add new authentication module",
            author_name="Test Author",
            author_email="test@example.com",
            date=now,
        ),
        Commit(
            sha="def2345678901",
            message="fix(api): handle null response from server",
            author_name="Test Author",
            author_email="test@example.com",
            date=now,
        ),
        Commit(
            sha="ghi3456789012",
            message=(
                "feat!: redesign configuration format\n\n"
                "BREAKING CHANGE: Config file format changed."
            ),
            author_name="Test Author",
            author_email="test@example.com",
            date=now,
        ),
        Commit(
            sha="jkl4567890123",
            message="docs: update README with examples",
            author_name="Test Author",
            author_email="test@example.com",
            date=now,
        ),
        Commit(
            sha="mno5678901234",
            message="chore: update dependencies",
            author_name="Test Author",
            author_email="test@example.com",
            date=now,
        ),
    ]


@pytest.fixture
def feat_commit() -> Commit:
    """A feature commit."""
    return Commit(
        sha="feat123456",
        message="feat: add user authentication",
        author_name="Test",
        author_email="test@test.com",
        date=datetime.now(),
    )


@pytest.fixture
def fix_commit() -> Commit:
    """A fix commit."""
    return Commit(
        sha="fix1234567",
        message="fix(core): resolve memory leak",
        author_name="Test",
        author_email="test@test.com",
        date=datetime.now(),
    )


@pytest.fixture
def breaking_commit() -> Commit:
    """A breaking change commit."""
    return Commit(
        sha="break12345",
        message="feat!: change API response format",
        author_name="Test",
        author_email="test@test.com",
        date=datetime.now(),
    )


# =============================================================================
# Config Fixtures
# =============================================================================


@pytest.fixture
def default_config() -> ReleasePyConfig:
    """Default releasio configuration."""
    return ReleasePyConfig()


@pytest.fixture
def default_commits_config() -> CommitsConfig:
    """Default commits configuration."""
    return CommitsConfig()


# =============================================================================
# Temporary Git Repository Fixtures
# =============================================================================


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository for testing.

    Returns the path to the repository root.
    """
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create initial commit
    readme = repo_path / "README.md"
    readme.write_text("# Test Project\n")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    return repo_path


@pytest.fixture
def temp_git_repo_with_pyproject(temp_git_repo: Path) -> Path:
    """Create a temp git repo with a pyproject.toml."""
    pyproject = temp_git_repo / "pyproject.toml"
    pyproject.write_text(
        """\
[project]
name = "test-project"
version = "1.0.0"
description = "A test project"
requires-python = ">=3.11"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.releasio]
default_branch = "main"
tag_prefix = "v"
"""
    )

    subprocess.run(
        ["git", "add", "pyproject.toml"],
        cwd=temp_git_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "feat: add pyproject.toml"],
        cwd=temp_git_repo,
        check=True,
        capture_output=True,
    )

    return temp_git_repo


@pytest.fixture
def temp_git_repo_with_commits(temp_git_repo_with_pyproject: Path) -> Path:
    """Create a temp git repo with several conventional commits."""
    repo = temp_git_repo_with_pyproject

    # Add some commits
    commits = [
        ("feat: add user module", "src/users.py", "# Users module\n"),
        ("fix(api): handle errors", "src/api.py", "# API module\n"),
        ("docs: update readme", "README.md", "# Test Project\n\nUpdated.\n"),
    ]

    for msg, filename, content in commits:
        filepath = repo / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content)
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=repo,
            check=True,
            capture_output=True,
        )

    return repo
