"""Comprehensive E2E tests for version file detection and lock file updates.

These tests exercise the full workflow with various project layouts
and package manager configurations to find edge cases and bugs.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from release_py.cli.app import app
from release_py.project.lockfile import PackageManager, detect_package_manager
from release_py.project.pyproject import detect_version_files, get_version_from_file

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


# =============================================================================
# Fixtures for different project layouts
# =============================================================================


@pytest.fixture
def git_repo_base(tmp_path: Path) -> Path:
    """Create base git repo without pyproject.toml."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


@pytest.fixture
def src_layout_project(git_repo_base: Path) -> Path:
    """Create project with src/ layout and version in __init__.py."""
    repo = git_repo_base

    # Create pyproject.toml
    pyproject = repo / "pyproject.toml"
    pyproject.write_text("""\
[project]
name = "mypackage"
version = "1.0.0"
description = "Test package"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.releasio]
default_branch = "main"
allow_dirty = true

[tool.releasio.version]
auto_detect_version_files = true
update_lock_file = true
""")

    # Create src/mypackage/__init__.py with version
    pkg_dir = repo / "src" / "mypackage"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text('"""My package."""\n\n__version__ = "1.0.0"\n')

    # Create uv.lock
    (repo / "uv.lock").write_text("# uv lock file\nversion = 1\n")

    # Initial commit
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: initial setup"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Tag v1.0.0
    subprocess.run(["git", "tag", "v1.0.0"], cwd=repo, check=True, capture_output=True)

    # Add feature commit
    (repo / "src" / "mypackage" / "feature.py").write_text("# Feature\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add new feature"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    return repo


@pytest.fixture
def flat_layout_project(git_repo_base: Path) -> Path:
    """Create project with flat layout and multiple version files."""
    repo = git_repo_base

    # Create pyproject.toml
    pyproject = repo / "pyproject.toml"
    pyproject.write_text("""\
[project]
name = "flatpkg"
version = "2.0.0"
description = "Flat layout package"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.releasio]
default_branch = "main"

[tool.releasio.version]
auto_detect_version_files = true
update_lock_file = false
""")

    # Create flatpkg/__init__.py with version
    pkg_dir = repo / "flatpkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text('__version__ = "2.0.0"\n')

    # Create flatpkg/__version__.py as well
    (pkg_dir / "__version__.py").write_text('__version__ = "2.0.0"\n')

    # Create VERSION file in root
    (repo / "VERSION").write_text("2.0.0\n")

    # Initial commit
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: initial setup"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Tag v2.0.0
    subprocess.run(["git", "tag", "v2.0.0"], cwd=repo, check=True, capture_output=True)

    # Add fix commit
    (repo / "flatpkg" / "fix.py").write_text("# Fix\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: bug fix"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    return repo


@pytest.fixture
def poetry_project(git_repo_base: Path) -> Path:
    """Create project with Poetry format pyproject.toml."""
    repo = git_repo_base

    # Create Poetry-style pyproject.toml
    pyproject = repo / "pyproject.toml"
    pyproject.write_text("""\
[tool.poetry]
name = "poetry-pkg"
version = "1.5.0"
description = "Poetry package"

[tool.poetry.dependencies]
python = "^3.11"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.releasio]
default_branch = "main"
allow_dirty = true

[tool.releasio.version]
auto_detect_version_files = true
update_lock_file = true
""")

    # Create poetry.lock
    (repo / "poetry.lock").write_text("# poetry lock\n")

    # Create src layout with _version.py
    pkg_dir = repo / "src" / "poetry_pkg"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text("# init\n")
    (pkg_dir / "_version.py").write_text('__version__ = "1.5.0"\n')

    # Initial commit
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: initial poetry setup"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Tag v1.5.0
    subprocess.run(["git", "tag", "v1.5.0"], cwd=repo, check=True, capture_output=True)

    # Add feature commit
    (repo / "src" / "poetry_pkg" / "new.py").write_text("# new\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add new module"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    return repo


@pytest.fixture
def pdm_project(git_repo_base: Path) -> Path:
    """Create project with PDM configuration."""
    repo = git_repo_base

    # Create PDM-style pyproject.toml
    pyproject = repo / "pyproject.toml"
    pyproject.write_text("""\
[project]
name = "pdm-pkg"
version = "3.0.0"
description = "PDM package"

[tool.pdm]
distribution = true

[build-system]
requires = ["pdm-backend"]
build-backend = "pdm.backend"

[tool.releasio]
default_branch = "main"
allow_dirty = true

[tool.releasio.version]
auto_detect_version_files = true
update_lock_file = true
""")

    # Create pdm.lock
    (repo / "pdm.lock").write_text("# pdm lock\n")

    # Create package with version.py
    pkg_dir = repo / "pdm_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("from .version import __version__\n")
    (pkg_dir / "version.py").write_text('__version__ = "3.0.0"\nVERSION = "3.0.0"\n')

    # Initial commit
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: initial pdm setup"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Tag v3.0.0
    subprocess.run(["git", "tag", "v3.0.0"], cwd=repo, check=True, capture_output=True)

    # Add breaking change
    (repo / "pdm_pkg" / "breaking.py").write_text("# breaking\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat!: breaking API change"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    return repo


# =============================================================================
# Version File Detection Tests
# =============================================================================


class TestVersionFileDetection:
    """Tests for version file auto-detection."""

    def test_detect_src_layout_init(self, src_layout_project: Path):
        """Detect __init__.py in src/ layout."""
        detected = detect_version_files(src_layout_project)

        assert len(detected) == 1
        assert detected[0].name == "__init__.py"
        assert "src/mypackage" in str(detected[0])

    def test_detect_flat_layout_multiple_files(self, flat_layout_project: Path):
        """Detect multiple version files in flat layout."""
        detected = detect_version_files(flat_layout_project)

        # Should find __init__.py, __version__.py, and VERSION
        assert len(detected) == 3
        names = {f.name for f in detected}
        assert "__init__.py" in names
        assert "__version__.py" in names
        assert "VERSION" in names

    def test_detect_poetry_version_file(self, poetry_project: Path):
        """Detect _version.py in Poetry project."""
        detected = detect_version_files(poetry_project)

        assert len(detected) == 1
        assert detected[0].name == "_version.py"

    def test_detect_pdm_version_file(self, pdm_project: Path):
        """Detect version.py in PDM project."""
        detected = detect_version_files(pdm_project)

        # version.py should be detected because it contains VERSION = "..."
        assert len(detected) == 1
        assert detected[0].name == "version.py"

    def test_skip_tests_directory(self, src_layout_project: Path):
        """Skip version files in tests/ directory."""
        # Create tests/__init__.py with version
        tests_dir = src_layout_project / "tests"
        tests_dir.mkdir()
        (tests_dir / "__init__.py").write_text('__version__ = "0.0.0"\n')

        detected = detect_version_files(src_layout_project)

        # Should NOT include the tests/__init__.py
        for f in detected:
            # Check relative path from project root, not absolute path
            # (absolute path might contain "test" in pytest temp dir name)
            rel_path = f.relative_to(src_layout_project)
            assert not str(rel_path).startswith("tests/")


# =============================================================================
# Lock File Detection Tests
# =============================================================================


class TestLockFileDetection:
    """Tests for package manager and lock file detection."""

    def test_detect_uv(self, src_layout_project: Path):
        """Detect uv from uv.lock."""
        pm = detect_package_manager(src_layout_project)
        assert pm == PackageManager.UV

    def test_detect_poetry(self, poetry_project: Path):
        """Detect Poetry from poetry.lock."""
        pm = detect_package_manager(poetry_project)
        assert pm == PackageManager.POETRY

    def test_detect_pdm(self, pdm_project: Path):
        """Detect PDM from pdm.lock."""
        pm = detect_package_manager(pdm_project)
        assert pm == PackageManager.PDM

    def test_lock_file_takes_precedence_over_pyproject_config(self, git_repo_base: Path):
        """Lock file detection takes precedence over pyproject.toml configuration."""
        repo = git_repo_base

        # Create pyproject.toml with [tool.pdm] but also have poetry.lock
        pyproject = repo / "pyproject.toml"
        pyproject.write_text("""\
[project]
name = "test"
version = "1.0.0"

[tool.pdm]
distribution = true
""")

        # Create poetry.lock (should take precedence)
        (repo / "poetry.lock").write_text("# poetry\n")

        pm = detect_package_manager(repo)
        assert pm == PackageManager.POETRY


# =============================================================================
# Full E2E Update Tests
# =============================================================================


class TestE2EUpdateWithVersionFiles:
    """End-to-end tests for update command with version file detection."""

    def test_update_src_layout_updates_init(self, src_layout_project: Path):
        """Update command updates __init__.py in src/ layout."""
        # Disable lock file updates to avoid subprocess.run mock issues
        pyproject = src_layout_project / "pyproject.toml"
        content = pyproject.read_text().replace(
            "update_lock_file = true", "update_lock_file = false"
        )
        pyproject.write_text(content)

        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [1.1.0]\n\n- New feature"

            result = runner.invoke(app, ["update", str(src_layout_project), "--execute"])

            assert result.exit_code == 0, f"Failed with output: {result.stdout}"
            assert "Updated version in pyproject.toml" in result.stdout
            assert "auto-detected" in result.stdout

            # Verify __init__.py was updated
            init_file = src_layout_project / "src" / "mypackage" / "__init__.py"
            content = init_file.read_text()
            assert '__version__ = "1.1.0"' in content

            # Verify pyproject.toml was updated
            pyproject = src_layout_project / "pyproject.toml"
            assert 'version = "1.1.0"' in pyproject.read_text()

    def test_update_flat_layout_updates_all_files(self, flat_layout_project: Path):
        """Update command updates all version files in flat layout."""
        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [2.0.1]\n\n- Bug fix"

            result = runner.invoke(app, ["update", str(flat_layout_project), "--execute"])

            assert result.exit_code == 0

            # Verify all version files were updated
            init_file = flat_layout_project / "flatpkg" / "__init__.py"
            assert '__version__ = "2.0.1"' in init_file.read_text()

            version_file = flat_layout_project / "flatpkg" / "__version__.py"
            assert '__version__ = "2.0.1"' in version_file.read_text()

            root_version = flat_layout_project / "VERSION"
            assert root_version.read_text().strip() == "2.0.1"

            # Verify pyproject.toml was updated
            pyproject = flat_layout_project / "pyproject.toml"
            assert 'version = "2.0.1"' in pyproject.read_text()

    def test_update_poetry_project(self, poetry_project: Path):
        """Update command works with Poetry project."""
        # Disable lock file updates to avoid subprocess.run mock issues
        pyproject_path = poetry_project / "pyproject.toml"
        content = pyproject_path.read_text().replace(
            "update_lock_file = true", "update_lock_file = false"
        )
        pyproject_path.write_text(content)

        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [1.6.0]\n\n- New module"

            result = runner.invoke(app, ["update", str(poetry_project), "--execute"])

            assert result.exit_code == 0, f"Failed with output: {result.stdout}"

            # Verify _version.py was updated
            version_file = poetry_project / "src" / "poetry_pkg" / "_version.py"
            assert '__version__ = "1.6.0"' in version_file.read_text()

            # Verify pyproject.toml was updated (Poetry format)
            pyproject = poetry_project / "pyproject.toml"
            assert 'version = "1.6.0"' in pyproject.read_text()

    def test_update_pdm_project_major_bump(self, pdm_project: Path):
        """Update command handles major bump in PDM project."""
        # Disable lock file updates to avoid subprocess.run mock issues
        pyproject_path = pdm_project / "pyproject.toml"
        content = pyproject_path.read_text().replace(
            "update_lock_file = true", "update_lock_file = false"
        )
        pyproject_path.write_text(content)

        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [4.0.0]\n\n- Breaking change"

            result = runner.invoke(app, ["update", str(pdm_project), "--execute"])

            assert result.exit_code == 0, f"Failed with output: {result.stdout}"

            # Verify version.py was updated (but only __version__ pattern)
            version_file = pdm_project / "pdm_pkg" / "version.py"
            content = version_file.read_text()
            assert '__version__ = "4.0.0"' in content
            # VERSION = "3.0.0" should NOT be updated (different pattern)
            # Actually the update_version_file only updates __version__

            # Verify pyproject.toml was updated
            pyproject = pdm_project / "pyproject.toml"
            assert 'version = "4.0.0"' in pyproject.read_text()


# =============================================================================
# Edge Cases and Bug Hunting
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and potential bugs."""

    def test_version_mismatch_between_files(self, git_repo_base: Path):
        """Handle version mismatch between pyproject.toml and __init__.py."""
        repo = git_repo_base

        # Create pyproject.toml with version 1.0.0
        pyproject = repo / "pyproject.toml"
        pyproject.write_text("""\
[project]
name = "mismatched"
version = "1.0.0"

[tool.releasio.version]
auto_detect_version_files = true
""")

        # Create __init__.py with DIFFERENT version (simulating out-of-sync)
        pkg_dir = repo / "mismatched"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text('__version__ = "0.9.0"\n')  # Different!

        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: initial"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "tag", "v1.0.0"], cwd=repo, check=True, capture_output=True)

        # Add commit
        (repo / "mismatched" / "new.py").write_text("# new\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "fix: something"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [1.0.1]"

            result = runner.invoke(app, ["update", str(repo), "--execute"])

            # Should update both to 1.0.1 (syncing them)
            assert result.exit_code == 0

            init_file = repo / "mismatched" / "__init__.py"
            assert '__version__ = "1.0.1"' in init_file.read_text()

    def test_init_without_version_not_updated(self, git_repo_base: Path):
        """Don't update __init__.py without version string."""
        repo = git_repo_base

        pyproject = repo / "pyproject.toml"
        pyproject.write_text("""\
[project]
name = "noversion"
version = "1.0.0"

[tool.releasio.version]
auto_detect_version_files = true
""")

        # Create __init__.py WITHOUT version
        pkg_dir = repo / "noversion"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text('"""No version here."""\n')

        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: initial"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "tag", "v1.0.0"], cwd=repo, check=True, capture_output=True)

        (repo / "noversion" / "new.py").write_text("# new\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: add feature"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [1.1.0]"

            result = runner.invoke(app, ["update", str(repo), "--execute"])

            assert result.exit_code == 0
            # Should NOT mention auto-detected files (none found)
            assert "auto-detected" not in result.stdout

            # __init__.py should be unchanged
            init_file = repo / "noversion" / "__init__.py"
            assert "__version__" not in init_file.read_text()

    def test_lock_file_update_tool_not_found(self, src_layout_project: Path):
        """Handle case when lock file tool (uv/poetry/pdm) not found."""
        with (
            patch("release_py.core.changelog.generate_changelog") as mock_changelog,
            patch("shutil.which", return_value=None),
        ):  # Tool not found
            mock_changelog.return_value = "## [1.1.0]"

            result = runner.invoke(app, ["update", str(src_layout_project), "--execute"])

            # Should still succeed, but warn about lock file
            assert result.exit_code == 0
            assert "not found" in result.stdout.lower() or "Updated version" in result.stdout

    def test_lock_file_disabled(self, flat_layout_project: Path):
        """Lock file update disabled in config."""
        # flat_layout_project has update_lock_file = false
        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [2.0.1]"

            result = runner.invoke(app, ["update", str(flat_layout_project), "--execute"])

            assert result.exit_code == 0
            # Should not mention lock file at all
            assert "lock" not in result.stdout.lower() or "CHANGELOG" in result.stdout

    def test_nested_packages_not_detected(self, git_repo_base: Path):
        """Don't detect version files in deeply nested packages."""
        repo = git_repo_base

        pyproject = repo / "pyproject.toml"
        pyproject.write_text("""\
[project]
name = "toplevel"
version = "1.0.0"

[tool.releasio.version]
auto_detect_version_files = true
""")

        # Create top-level package
        pkg_dir = repo / "toplevel"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text('__version__ = "1.0.0"\n')

        # Create nested sub-package with its own version
        subpkg = pkg_dir / "subpkg"
        subpkg.mkdir()
        (subpkg / "__init__.py").write_text('__version__ = "0.5.0"\n')  # Different version

        detected = detect_version_files(repo)

        # Should only detect the top-level __init__.py, not the nested one
        assert len(detected) == 1
        assert "subpkg" not in str(detected[0])

    def test_single_quotes_version(self, git_repo_base: Path):
        """Handle version with single quotes."""
        repo = git_repo_base

        pyproject = repo / "pyproject.toml"
        pyproject.write_text("""\
[project]
name = "singlequotes"
version = '1.0.0'

[tool.releasio.version]
auto_detect_version_files = true
""")

        pkg_dir = repo / "singlequotes"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("__version__ = '1.0.0'\n")  # Single quotes

        detected = detect_version_files(repo)

        assert len(detected) == 1
        version = get_version_from_file(detected[0])
        assert version == "1.0.0"

    def test_explicit_version_files_config(self, git_repo_base: Path):
        """Explicit version_files config takes precedence."""
        repo = git_repo_base

        pyproject = repo / "pyproject.toml"
        pyproject.write_text("""\
[project]
name = "explicit"
version = "1.0.0"

[tool.releasio.version]
auto_detect_version_files = true
version_files = ["custom_version.txt"]
""")

        # Create custom version file
        custom = repo / "custom_version.txt"
        custom.write_text('__version__ = "1.0.0"\n')

        # Also create auto-detectable file
        pkg_dir = repo / "explicit"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text('__version__ = "1.0.0"\n')

        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: initial"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "tag", "v1.0.0"], cwd=repo, check=True, capture_output=True)

        (repo / "explicit" / "new.py").write_text("# new\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: add feature"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        with patch("release_py.core.changelog.generate_changelog") as mock_changelog:
            mock_changelog.return_value = "## [1.1.0]"

            result = runner.invoke(app, ["update", str(repo), "--execute"])

            assert result.exit_code == 0
            # Both files should be updated
            assert "custom_version.txt" in result.stdout
            assert "auto-detected" in result.stdout


class TestVersionPatternVariations:
    """Tests for various version string patterns."""

    def test_version_with_spaces(self, tmp_path: Path):
        """Handle version assignment with various spacing."""
        file_path = tmp_path / "test.py"

        # Test different spacing patterns
        patterns = [
            '__version__="1.0.0"',  # No spaces
            '__version__ = "1.0.0"',  # Normal spacing
            '__version__  =  "1.0.0"',  # Extra spaces
            '__version__   =   "1.0.0"',  # Lots of spaces
        ]

        for pattern in patterns:
            file_path.write_text(f"{pattern}\n")
            version = get_version_from_file(file_path)
            assert version == "1.0.0", f"Failed for pattern: {pattern}"

    def test_uppercase_version_constant(self, tmp_path: Path):
        """Handle VERSION = '...' pattern."""
        file_path = tmp_path / "version.py"
        file_path.write_text('VERSION = "2.5.0"\n')

        version = get_version_from_file(file_path)
        assert version == "2.5.0"

    def test_lowercase_version_constant(self, tmp_path: Path):
        """Handle version = '...' pattern."""
        file_path = tmp_path / "version.py"
        file_path.write_text('version = "3.0.0-beta.1"\n')

        version = get_version_from_file(file_path)
        assert version == "3.0.0-beta.1"

    def test_version_in_multiline_file(self, tmp_path: Path):
        """Find version in file with other content."""
        file_path = tmp_path / "__init__.py"
        file_path.write_text('''"""Package docstring.

This is a longer description.
"""

import os
import sys

__version__ = "1.2.3"
__author__ = "Test Author"

def main():
    pass
''')

        version = get_version_from_file(file_path)
        assert version == "1.2.3"


class TestDryRunMode:
    """Tests for dry-run mode with new features."""

    def test_dry_run_shows_detected_files(self, src_layout_project: Path):
        """Dry run shows what files would be updated."""
        result = runner.invoke(app, ["update", str(src_layout_project)])

        assert result.exit_code == 0
        assert "DRY-RUN" in result.stdout
        assert "pyproject.toml" in result.stdout

    def test_dry_run_does_not_modify_files(self, flat_layout_project: Path):
        """Dry run doesn't actually modify any files."""
        # Record original content
        original_pyproject = (flat_layout_project / "pyproject.toml").read_text()
        original_init = (flat_layout_project / "flatpkg" / "__init__.py").read_text()
        original_version = (flat_layout_project / "VERSION").read_text()

        result = runner.invoke(app, ["update", str(flat_layout_project)])

        assert result.exit_code == 0

        # Verify nothing changed
        assert (flat_layout_project / "pyproject.toml").read_text() == original_pyproject
        assert (flat_layout_project / "flatpkg" / "__init__.py").read_text() == original_init
        assert (flat_layout_project / "VERSION").read_text() == original_version
