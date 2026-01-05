"""Unit tests for PyPI publishing."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from releasio.config.models import PublishConfig
from releasio.exceptions import BuildError, PublishError, UploadError
from releasio.publish.pypi import (
    build_package,
    check_pypi_version_exists,
    publish_package,
    validate_dist_files,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestBuildPackage:
    """Tests for package building."""

    def test_build_with_uv(self, tmp_path: Path):
        """Build package using uv."""
        # Create dist directory with mock files
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        (dist_dir / "package-1.0.0.whl").touch()
        (dist_dir / "package-1.0.0.tar.gz").touch()

        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/uv"
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                result = build_package(tmp_path, clean=False)

                assert len(result) == 2
                mock_run.assert_called_once()
                assert "uv" in mock_run.call_args[0][0]

    def test_build_with_hatch_fallback(self, tmp_path: Path):
        """Fall back to hatch when uv not available."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        (dist_dir / "package-1.0.0.whl").touch()

        def which_side_effect(cmd: str) -> str | None:
            if cmd == "uv":
                return None
            if cmd == "hatch":
                return "/usr/bin/hatch"
            return None

        with patch("shutil.which", side_effect=which_side_effect):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                result = build_package(tmp_path, clean=False)

                assert len(result) == 1
                assert "hatch" in mock_run.call_args[0][0]

    def test_build_with_python_build_fallback(self, tmp_path: Path):
        """Fall back to python -m build."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        (dist_dir / "package-1.0.0.whl").touch()

        def which_side_effect(cmd: str) -> str | None:
            if cmd == "python":
                return "/usr/bin/python"
            return None

        with patch("shutil.which", side_effect=which_side_effect):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                result = build_package(tmp_path, clean=False)

                assert len(result) == 1
                call_args = mock_run.call_args[0][0]
                assert "python" in call_args
                assert "-m" in call_args
                assert "build" in call_args

    def test_build_no_tool_raises(self, tmp_path: Path):
        """Raise BuildError when no build tool found."""
        with patch("shutil.which", return_value=None):
            with pytest.raises(BuildError, match="No build tool found"):
                build_package(tmp_path)

    def test_build_cleans_dist(self, tmp_path: Path):
        """Clean dist directory before building."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        old_file = dist_dir / "old-package-0.1.0.whl"
        old_file.touch()

        with patch("shutil.which", return_value="/usr/bin/uv"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                # This should clean and then fail because no files created
                with pytest.raises(BuildError, match="dist/ directory not found"):
                    build_package(tmp_path, clean=True)

                # Old file should be gone (directory removed)
                assert not old_file.exists()

    def test_build_failure_raises(self, tmp_path: Path):
        """Build failure raises BuildError."""
        with patch("shutil.which", return_value="/usr/bin/uv"):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(
                    1, "uv build", stderr="Build failed: missing setup.py"
                )

                with pytest.raises(BuildError, match="Build with uv failed"):
                    build_package(tmp_path)

    def test_build_no_dist_files_raises(self, tmp_path: Path):
        """Raise BuildError when no distribution files found."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        # Empty dist directory

        with patch("shutil.which", return_value="/usr/bin/uv"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                with pytest.raises(BuildError, match="no distribution files found"):
                    build_package(tmp_path, clean=False)


class TestPublishPackage:
    """Tests for package publishing."""

    def test_publish_disabled(self, tmp_path: Path):
        """Skip publishing when disabled."""
        config = PublishConfig(enabled=False)

        # Should not raise or call anything
        publish_package(tmp_path, config)

    def test_publish_with_uv(self, tmp_path: Path):
        """Publish using uv."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(enabled=True, tool="uv")

        with patch("shutil.which", return_value="/usr/bin/uv"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                publish_package(tmp_path, config, dist_files=[whl])

                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                assert "uv" in call_args
                assert "publish" in call_args

    def test_publish_with_twine(self, tmp_path: Path):
        """Publish using twine."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(enabled=True, tool="twine")

        with patch("shutil.which", return_value="/usr/bin/twine"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                publish_package(tmp_path, config, dist_files=[whl])

                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                assert "twine" in call_args
                assert "upload" in call_args

    def test_publish_custom_registry(self, tmp_path: Path):
        """Publish to custom registry."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(
            enabled=True,
            tool="uv",
            registry="https://test.pypi.org/legacy/",
        )

        with patch("shutil.which", return_value="/usr/bin/uv"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                publish_package(tmp_path, config, dist_files=[whl])

                call_args = mock_run.call_args[0][0]
                assert "--publish-url" in call_args
                assert "https://test.pypi.org/legacy/" in call_args

    def test_publish_no_files_raises(self, tmp_path: Path):
        """Raise PublishError when no files to publish."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()  # Empty

        config = PublishConfig(enabled=True, tool="uv")

        with pytest.raises(PublishError, match="No distribution files"):
            publish_package(tmp_path, config)

    def test_publish_uv_not_found_raises(self, tmp_path: Path):
        """Raise PublishError when uv not found."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(enabled=True, tool="uv")

        with patch("shutil.which", return_value=None):
            with pytest.raises(PublishError, match="uv not found"):
                publish_package(tmp_path, config, dist_files=[whl])

    def test_publish_twine_not_found_raises(self, tmp_path: Path):
        """Raise PublishError when twine not found."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(enabled=True, tool="twine")

        with patch("shutil.which", return_value=None):
            with pytest.raises(PublishError, match="twine not found"):
                publish_package(tmp_path, config, dist_files=[whl])

    def test_publish_version_exists_raises(self, tmp_path: Path):
        """Raise UploadError when version already published."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(enabled=True, tool="uv")

        with patch("shutil.which", return_value="/usr/bin/uv"):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(
                    1, "uv publish", stderr="File already exists"
                )

                with pytest.raises(UploadError, match="already been published"):
                    publish_package(tmp_path, config, dist_files=[whl])


class TestCheckPypiVersionExists:
    """Tests for PyPI version checking."""

    def test_version_exists(self):
        """Return True when version exists on PyPI."""
        with patch("httpx.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200)

            result = check_pypi_version_exists("requests", "2.28.0")

            assert result is True
            mock_get.assert_called_once_with(
                "https://pypi.org/pypi/requests/2.28.0/json",
                timeout=10,
            )

    def test_version_not_exists(self):
        """Return False when version doesn't exist."""
        with patch("httpx.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=404)

            result = check_pypi_version_exists("requests", "99.99.99")

            assert result is False

    def test_http_error_returns_false(self):
        """Return False on HTTP errors."""
        import httpx

        with patch("httpx.get") as mock_get:
            mock_get.side_effect = httpx.HTTPError("Connection failed")

            result = check_pypi_version_exists("requests", "2.28.0")

            assert result is False

    def test_timeout_returns_false(self):
        """Return False on timeout."""
        import httpx

        with patch("httpx.get") as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Timeout")

            result = check_pypi_version_exists("requests", "2.28.0")

            assert result is False


class TestBuildPackageWithPoetry:
    """Tests for building with Poetry."""

    def test_build_with_poetry_when_configured(self, tmp_path: Path):
        """Build package using poetry when tool=poetry."""
        # Create poetry.lock to indicate Poetry project
        (tmp_path / "poetry.lock").touch()

        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        (dist_dir / "package-1.0.0.whl").touch()

        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/poetry"
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                result = build_package(tmp_path, clean=False, tool="poetry")

                assert len(result) == 1
                mock_run.assert_called_once()
                assert "poetry" in mock_run.call_args[0][0]
                assert "build" in mock_run.call_args[0][0]

    def test_build_poetry_missing_lock_file_raises(self, tmp_path: Path):
        """Raise BuildError when poetry configured but poetry.lock missing."""
        with patch("shutil.which", return_value="/usr/bin/poetry"):
            with pytest.raises(BuildError, match=r"poetry\.lock not found"):
                build_package(tmp_path, tool="poetry")

    def test_build_poetry_falls_back_to_uv(self, tmp_path: Path):
        """Fall back to uv when poetry not installed."""
        (tmp_path / "poetry.lock").touch()
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        (dist_dir / "package-1.0.0.whl").touch()

        def which_side_effect(cmd: str) -> str | None:
            if cmd == "poetry":
                return None
            if cmd == "uv":
                return "/usr/bin/uv"
            return None

        with patch("shutil.which", side_effect=which_side_effect):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                result = build_package(tmp_path, clean=False, tool="poetry")

                # Should fall back to uv
                assert len(result) == 1
                assert "uv" in mock_run.call_args[0][0]


class TestBuildPackageWithPDM:
    """Tests for building with PDM."""

    def test_build_with_pdm_when_configured(self, tmp_path: Path):
        """Build package using pdm when tool=pdm."""
        (tmp_path / "pdm.lock").touch()

        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        (dist_dir / "package-1.0.0.whl").touch()

        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/pdm"
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                result = build_package(tmp_path, clean=False, tool="pdm")

                assert len(result) == 1
                mock_run.assert_called_once()
                assert "pdm" in mock_run.call_args[0][0]
                assert "build" in mock_run.call_args[0][0]

    def test_build_pdm_missing_lock_file_raises(self, tmp_path: Path):
        """Raise BuildError when pdm configured but pdm.lock missing."""
        with patch("shutil.which", return_value="/usr/bin/pdm"):
            with pytest.raises(BuildError, match=r"pdm\.lock not found"):
                build_package(tmp_path, tool="pdm")


class TestPublishWithPoetry:
    """Tests for publishing with Poetry."""

    def test_publish_with_poetry(self, tmp_path: Path):
        """Publish using poetry."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(enabled=True, tool="poetry")

        with patch("shutil.which", return_value="/usr/bin/poetry"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                publish_package(tmp_path, config, dist_files=[whl])

                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                assert "poetry" in call_args
                assert "publish" in call_args

    def test_publish_poetry_custom_registry(self, tmp_path: Path):
        """Publish to custom registry with poetry."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(
            enabled=True,
            tool="poetry",
            registry="https://test.pypi.org/legacy/",
        )

        with patch("shutil.which", return_value="/usr/bin/poetry"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                publish_package(tmp_path, config, dist_files=[whl])

                call_args = mock_run.call_args[0][0]
                assert "--repository" in call_args
                assert "https://test.pypi.org/legacy/" in call_args

    def test_publish_poetry_not_found_raises(self, tmp_path: Path):
        """Raise PublishError when poetry not found."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(enabled=True, tool="poetry")

        with patch("shutil.which", return_value=None):
            with pytest.raises(PublishError, match="poetry not found"):
                publish_package(tmp_path, config, dist_files=[whl])

    def test_publish_poetry_already_published_raises(self, tmp_path: Path):
        """Raise UploadError when version already published."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(enabled=True, tool="poetry")

        with patch("shutil.which", return_value="/usr/bin/poetry"):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(
                    1, "poetry publish", stderr="File already exists"
                )

                with pytest.raises(UploadError, match="already been published"):
                    publish_package(tmp_path, config, dist_files=[whl])

    def test_publish_poetry_authentication_error(self, tmp_path: Path):
        """Poetry publish fails with helpful message on auth error."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(enabled=True, tool="poetry")

        with patch("shutil.which", return_value="/usr/bin/poetry"):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(
                    1, "poetry publish", stderr="Authentication credentials were not provided"
                )

                with pytest.raises(PublishError, match="Poetry authentication failed"):
                    publish_package(tmp_path, config, dist_files=[whl])


class TestPublishWithPDM:
    """Tests for publishing with PDM."""

    def test_publish_with_pdm(self, tmp_path: Path):
        """Publish using pdm."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(enabled=True, tool="pdm")

        with patch("shutil.which", return_value="/usr/bin/pdm"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                publish_package(tmp_path, config, dist_files=[whl])

                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                assert "pdm" in call_args
                assert "publish" in call_args
                assert "--no-build" in call_args

    def test_publish_pdm_custom_registry(self, tmp_path: Path):
        """Publish to custom registry with pdm."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(
            enabled=True,
            tool="pdm",
            registry="https://test.pypi.org/legacy/",
        )

        with patch("shutil.which", return_value="/usr/bin/pdm"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                publish_package(tmp_path, config, dist_files=[whl])

                call_args = mock_run.call_args[0][0]
                assert "--repository" in call_args
                assert "https://test.pypi.org/legacy/" in call_args

    def test_publish_pdm_not_found_raises(self, tmp_path: Path):
        """Raise PublishError when pdm not found."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(enabled=True, tool="pdm")

        with patch("shutil.which", return_value=None):
            with pytest.raises(PublishError, match="pdm not found"):
                publish_package(tmp_path, config, dist_files=[whl])

    def test_publish_pdm_authentication_error(self, tmp_path: Path):
        """PDM publish fails with helpful message on auth error."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(enabled=True, tool="pdm")

        with patch("shutil.which", return_value="/usr/bin/pdm"):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(
                    1, "pdm publish", stderr="401 Unauthorized - authentication required"
                )

                with pytest.raises(PublishError, match="PDM authentication failed"):
                    publish_package(tmp_path, config, dist_files=[whl])


class TestBuildCustomCommand:
    """Tests for custom build commands."""

    def test_build_with_custom_command_version_substitution(self, tmp_path: Path):
        """Custom build command with {version} variable substitution."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        (dist_dir / "package-1.0.0.whl").touch()

        custom_cmd = "echo Building version {version} && mkdir -p dist"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            build_package(
                tmp_path,
                clean=False,
                custom_command=custom_cmd,
                version="1.0.0",
            )

            # Verify command substitution
            called_cmd = mock_run.call_args[0][0]
            assert "1.0.0" in called_cmd
            assert "{version}" not in called_cmd
            # Verify it was called with shell=True
            assert mock_run.call_args[1]["shell"] is True

    def test_build_with_custom_command_path_substitution(self, tmp_path: Path):
        """Custom build command with {project_path} variable substitution."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        (dist_dir / "package-1.0.0.whl").touch()

        custom_cmd = "cd {project_path} && make build"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            build_package(tmp_path, clean=False, custom_command=custom_cmd)

            called_cmd = mock_run.call_args[0][0]
            assert str(tmp_path) in called_cmd
            assert "{project_path}" not in called_cmd

    def test_build_custom_command_failure_raises(self, tmp_path: Path):
        """Custom build command failure raises BuildError."""
        custom_cmd = "exit 1"

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, custom_cmd, stderr="Build failed"
            )

            with pytest.raises(BuildError, match="Custom build command failed"):
                build_package(tmp_path, custom_command=custom_cmd)


class TestValidateDistFiles:
    """Tests for distribution file validation."""

    def test_validate_with_twine_success(self, tmp_path: Path):
        """Validation succeeds when twine check passes."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0-py3-none-any.whl"
        whl.write_text("fake wheel")
        tarball = dist_dir / "package-1.0.0.tar.gz"
        tarball.write_text("fake tarball")

        with patch("shutil.which", return_value="/usr/bin/twine"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="Checking dist/package-1.0.0-py3-none-any.whl: PASSED\nChecking dist/package-1.0.0.tar.gz: PASSED",
                )

                is_valid, message = validate_dist_files([whl, tarball])

                assert is_valid is True
                assert "PASSED" in message or "passed" in message.lower()
                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                assert "twine" in call_args
                assert "check" in call_args

    def test_validate_with_twine_failure(self, tmp_path: Path):
        """Validation fails when twine check fails."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0-py3-none-any.whl"
        whl.write_text("invalid wheel")

        with patch("shutil.which", return_value="/usr/bin/twine"):
            with patch("subprocess.run") as mock_run:
                error = subprocess.CalledProcessError(1, "twine check")
                error.stdout = "Checking dist/package-1.0.0-py3-none-any.whl: FAILED"
                error.stderr = "Package metadata is invalid"
                mock_run.side_effect = error

                is_valid, message = validate_dist_files([whl])

                assert is_valid is False
                assert "Validation failed" in message
                assert "metadata is invalid" in message

    def test_validate_without_twine_basic_checks(self, tmp_path: Path):
        """Fallback to basic validation when twine not available."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0-py3-none-any.whl"
        whl.write_text("fake wheel")

        with patch("shutil.which", return_value=None):
            is_valid, message = validate_dist_files([whl])

            assert is_valid is True
            assert "basic checks only" in message

    def test_validate_file_not_exists(self, tmp_path: Path):
        """Validation fails when file doesn't exist."""
        nonexistent = tmp_path / "dist" / "nonexistent.whl"

        with patch("shutil.which", return_value=None):
            is_valid, message = validate_dist_files([nonexistent])

            assert is_valid is False
            assert "not found" in message

    def test_validate_invalid_extension(self, tmp_path: Path):
        """Validation fails for invalid file types."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        invalid_file = dist_dir / "package-1.0.0.txt"
        invalid_file.write_text("not a distribution file")

        with patch("shutil.which", return_value=None):
            is_valid, message = validate_dist_files([invalid_file])

            assert is_valid is False
            assert "Invalid distribution file type" in message

    def test_validate_empty_list(self):
        """Validation fails when no files provided."""
        is_valid, message = validate_dist_files([])

        assert is_valid is False
        assert "No distribution files" in message

    def test_validate_multiple_files(self, tmp_path: Path):
        """Validation checks multiple files."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0-py3-none-any.whl"
        whl.write_text("fake wheel")
        tarball = dist_dir / "package-1.0.0.tar.gz"
        tarball.write_text("fake tarball")
        sdist = dist_dir / "package-1.0.0.zip"
        sdist.write_text("fake sdist")

        with patch("shutil.which", return_value="/usr/bin/twine"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="All checks passed")

                is_valid, _ = validate_dist_files([whl, tarball, sdist])

                assert is_valid is True
                # Should call twine check with all three files
                call_args = mock_run.call_args[0][0]
                assert len([arg for arg in call_args if arg.endswith((".whl", ".gz", ".zip"))]) == 3


class TestTrustedPublishing:
    """Tests for OIDC trusted publishing functionality."""

    def test_is_trusted_publishing_available_true(self):
        """Detect OIDC environment when variables are set."""
        from releasio.publish.pypi import is_trusted_publishing_available

        with patch.dict(
            "os.environ",
            {
                "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "token123",
                "ACTIONS_ID_TOKEN_REQUEST_URL": "https://token.actions.githubusercontent.com",
            },
        ):
            assert is_trusted_publishing_available() is True

    def test_is_trusted_publishing_available_false(self):
        """Return False when OIDC environment not available."""
        from releasio.publish.pypi import is_trusted_publishing_available

        with patch.dict("os.environ", {}, clear=True):
            assert is_trusted_publishing_available() is False

    def test_is_trusted_publishing_partial_env(self):
        """Return False when only partial OIDC env is set."""
        from releasio.publish.pypi import is_trusted_publishing_available

        # Only token set, no URL
        with patch.dict(
            "os.environ",
            {"ACTIONS_ID_TOKEN_REQUEST_TOKEN": "token123"},
            clear=True,
        ):
            assert is_trusted_publishing_available() is False

    def test_publish_uv_trusted_publishing_enabled_with_oidc(self, tmp_path: Path):
        """Use --trusted-publishing=always when OIDC available and enabled."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(enabled=True, tool="uv", trusted_publishing=True)

        with patch("shutil.which", return_value="/usr/bin/uv"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                with patch.dict(
                    "os.environ",
                    {
                        "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "token",
                        "ACTIONS_ID_TOKEN_REQUEST_URL": "https://example.com",
                    },
                ):
                    publish_package(tmp_path, config, dist_files=[whl])

                    call_args = mock_run.call_args[0][0]
                    assert "--trusted-publishing=always" in call_args

    def test_publish_uv_trusted_publishing_enabled_without_oidc(self, tmp_path: Path):
        """Use --trusted-publishing=automatic when enabled but no OIDC."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(enabled=True, tool="uv", trusted_publishing=True)

        with patch("shutil.which", return_value="/usr/bin/uv"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                with patch.dict("os.environ", {}, clear=True):
                    publish_package(tmp_path, config, dist_files=[whl])

                    call_args = mock_run.call_args[0][0]
                    assert "--trusted-publishing=automatic" in call_args

    def test_publish_uv_trusted_publishing_disabled(self, tmp_path: Path):
        """Use --trusted-publishing=never when disabled."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(enabled=True, tool="uv", trusted_publishing=False)

        with patch("shutil.which", return_value="/usr/bin/uv"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                publish_package(tmp_path, config, dist_files=[whl])

                call_args = mock_run.call_args[0][0]
                assert "--trusted-publishing=never" in call_args

    def test_publish_uv_removes_tokens_when_oidc_available(self, tmp_path: Path):
        """Tokens must be removed from env when using trusted publishing with OIDC.

        uv rejects publishing when both OIDC and tokens are present:
        "a username and a password are not allowed when using trusted publishing"
        """
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(enabled=True, tool="uv", trusted_publishing=True)

        with patch("shutil.which", return_value="/usr/bin/uv"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                with patch.dict(
                    "os.environ",
                    {
                        "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "oidc_token",
                        "ACTIONS_ID_TOKEN_REQUEST_URL": "https://example.com",
                        "UV_PUBLISH_TOKEN": "pypi-secret-token",
                        "PYPI_TOKEN": "another-token",
                    },
                ):
                    publish_package(tmp_path, config, dist_files=[whl])

                    # Verify tokens were removed from the env passed to subprocess
                    call_kwargs = mock_run.call_args[1]
                    env = call_kwargs.get("env", {})
                    assert "UV_PUBLISH_TOKEN" not in env
                    assert "PYPI_TOKEN" not in env
                    # OIDC vars should still be present
                    assert env.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN") == "oidc_token"

    def test_publish_uv_maps_pypi_token_when_no_oidc(self, tmp_path: Path):
        """PYPI_TOKEN should be mapped to UV_PUBLISH_TOKEN when OIDC not available."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(enabled=True, tool="uv", trusted_publishing=True)

        with patch("shutil.which", return_value="/usr/bin/uv"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                # OIDC not available, only PYPI_TOKEN set
                with patch.dict(
                    "os.environ",
                    {"PYPI_TOKEN": "pypi-secret-token"},
                    clear=True,
                ):
                    publish_package(tmp_path, config, dist_files=[whl])

                    call_kwargs = mock_run.call_args[1]
                    env = call_kwargs.get("env", {})
                    # PYPI_TOKEN should be mapped to UV_PUBLISH_TOKEN
                    assert env.get("UV_PUBLISH_TOKEN") == "pypi-secret-token"

    def test_publish_uv_maps_pypi_token_when_trusted_disabled(self, tmp_path: Path):
        """PYPI_TOKEN should be mapped to UV_PUBLISH_TOKEN when trusted publishing disabled."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(enabled=True, tool="uv", trusted_publishing=False)

        with patch("shutil.which", return_value="/usr/bin/uv"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                with patch.dict(
                    "os.environ",
                    {"PYPI_TOKEN": "pypi-secret-token"},
                    clear=True,
                ):
                    publish_package(tmp_path, config, dist_files=[whl])

                    call_kwargs = mock_run.call_args[1]
                    env = call_kwargs.get("env", {})
                    assert env.get("UV_PUBLISH_TOKEN") == "pypi-secret-token"

    def test_publish_uv_preserves_uv_publish_token_over_pypi_token(self, tmp_path: Path):
        """UV_PUBLISH_TOKEN takes precedence over PYPI_TOKEN."""
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        whl = dist_dir / "package-1.0.0.whl"
        whl.touch()

        config = PublishConfig(enabled=True, tool="uv", trusted_publishing=False)

        with patch("shutil.which", return_value="/usr/bin/uv"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                with patch.dict(
                    "os.environ",
                    {
                        "UV_PUBLISH_TOKEN": "uv-native-token",
                        "PYPI_TOKEN": "pypi-token",
                    },
                    clear=True,
                ):
                    publish_package(tmp_path, config, dist_files=[whl])

                    call_kwargs = mock_run.call_args[1]
                    env = call_kwargs.get("env", {})
                    # UV_PUBLISH_TOKEN should NOT be overwritten
                    assert env.get("UV_PUBLISH_TOKEN") == "uv-native-token"
