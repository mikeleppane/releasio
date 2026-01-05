"""Unit tests for project detection and version resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from release_py.exceptions import ProjectNotFoundError
from release_py.project.detector import (
    _resolve_dynamic_version,
    _resolve_fallback_version,
    _resolve_flit_version,
    _resolve_hatchling_version,
    _resolve_pdm_version,
    _resolve_setuptools_version,
    detect_project,
    detect_workspace_packages,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestDynamicVersionResolution:
    """Tests for dynamic version resolution from various build backends."""

    def test_resolve_hatchling_version(self, tmp_path: Path):
        """Resolve version from hatchling configuration."""
        # Create a version file
        src_dir = tmp_path / "src" / "mypackage"
        src_dir.mkdir(parents=True)
        version_file = src_dir / "_version.py"
        version_file.write_text('__version__ = "1.2.3"\n')

        # Test data with hatchling config
        tool_config = {
            "hatch": {
                "version": {
                    "path": "src/mypackage/_version.py",
                }
            }
        }

        version = _resolve_hatchling_version(tool_config, tmp_path)

        assert version == "1.2.3"

    def test_resolve_setuptools_version_attr(self, tmp_path: Path):
        """Resolve version from setuptools using attr format."""
        # Create package with __version__
        src_dir = tmp_path / "src" / "mypackage"
        src_dir.mkdir(parents=True)
        init_file = src_dir / "__init__.py"
        init_file.write_text('__version__ = "2.0.0"\n')

        # Test data with setuptools dynamic config (attr format)
        tool_config = {
            "setuptools": {
                "dynamic": {
                    "version": {
                        "attr": "mypackage.__version__",
                    }
                }
            }
        }

        version = _resolve_setuptools_version(tool_config, tmp_path)

        assert version == "2.0.0"

    def test_resolve_setuptools_version_file(self, tmp_path: Path):
        """Resolve version from setuptools using file format."""
        # Create version file
        version_file = tmp_path / "VERSION.txt"
        version_file.write_text("3.1.4\n")

        # Test data with setuptools dynamic config (file format)
        tool_config = {
            "setuptools": {
                "dynamic": {
                    "version": {
                        "file": "VERSION.txt",
                    }
                }
            }
        }

        version = _resolve_setuptools_version(tool_config, tmp_path)

        assert version == "3.1.4"

    def test_resolve_flit_version(self, tmp_path: Path):
        """Resolve version from flit configuration."""
        # Create module with __version__
        module_dir = tmp_path / "src" / "mymodule"
        module_dir.mkdir(parents=True)
        init_file = module_dir / "__init__.py"
        init_file.write_text('__version__ = "1.0.0"\n')

        # Test data with flit config
        tool_config = {
            "flit": {
                "module": {
                    "name": "mymodule",
                }
            }
        }

        version = _resolve_flit_version(tool_config, tmp_path)

        assert version == "1.0.0"

    def test_resolve_pdm_version(self, tmp_path: Path):
        """Resolve version from PDM configuration."""
        # Create version file
        version_file = tmp_path / "src" / "mypackage" / "__version__.py"
        version_file.parent.mkdir(parents=True)
        version_file.write_text('__version__ = "4.2.0"\n')

        # Test data with PDM config
        tool_config = {
            "pdm": {
                "version": {
                    "source": "file",
                    "path": "src/mypackage/__version__.py",
                }
            }
        }

        version = _resolve_pdm_version(tool_config, tmp_path)

        assert version == "4.2.0"

    def test_resolve_fallback_version(self, tmp_path: Path):
        """Fallback to common version file locations."""
        # Create package in src/ with __version__
        src_dir = tmp_path / "src" / "my_package"
        src_dir.mkdir(parents=True)
        init_file = src_dir / "__init__.py"
        init_file.write_text('__version__ = "0.5.0"\n')

        # Test data with project name
        data = {
            "project": {
                "name": "my-package",  # Note: hyphen converted to underscore
            }
        }

        version = _resolve_fallback_version(data, tmp_path)

        assert version == "0.5.0"

    def test_resolve_version_no_version_found(self, tmp_path: Path):
        """Return empty string when version not found."""
        tool_config = {
            "hatch": {
                "version": {
                    "path": "nonexistent/_version.py",
                }
            }
        }

        version = _resolve_hatchling_version(tool_config, tmp_path)

        assert version == ""

    def test_resolve_dynamic_version_with_backend(self, tmp_path: Path):
        """Dynamic version resolution uses backend-specific resolver."""
        # Create hatchling version file
        src_dir = tmp_path / "src" / "pkg"
        src_dir.mkdir(parents=True)
        version_file = src_dir / "__init__.py"
        version_file.write_text('__version__ = "1.5.0"\n')

        data = {
            "tool": {
                "hatch": {
                    "version": {
                        "path": "src/pkg/__init__.py",
                    }
                }
            }
        }

        version = _resolve_dynamic_version(data, tmp_path, "hatchling")

        assert version == "1.5.0"


class TestBuildBackendDetection:
    """Tests for build backend detection."""

    def test_detect_poetry_backend(self, tmp_path: Path):
        """Detect Poetry as build backend."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[tool.poetry]
name = "my-package"
version = "1.0.0"
""")

        project = detect_project(tmp_path)

        assert project.build_backend == "poetry"
        assert project.project_type == "poetry"
        assert project.name == "my-package"
        assert project.version == "1.0.0"

    def test_detect_hatchling_backend(self, tmp_path: Path):
        """Detect hatchling as build backend."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "my-package"
version = "2.0.0"
""")

        project = detect_project(tmp_path)

        assert project.build_backend == "hatchling"
        assert project.project_type == "pyproject"
        assert project.name == "my-package"

    def test_detect_setuptools_backend(self, tmp_path: Path):
        """Detect setuptools as build backend."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "my-package"
version = "3.0.0"
""")

        project = detect_project(tmp_path)

        assert project.build_backend == "setuptools"
        assert project.project_type == "pyproject"

    def test_detect_flit_backend(self, tmp_path: Path):
        """Detect flit as build backend."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[build-system]
requires = ["flit_core>=3.2"]
build-backend = "flit_core.buildapi"

[project]
name = "my-package"
version = "4.0.0"
""")

        project = detect_project(tmp_path)

        assert project.build_backend == "flit"
        assert project.project_type == "pyproject"

    def test_detect_pdm_backend(self, tmp_path: Path):
        """Detect PDM as build backend."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[build-system]
requires = ["pdm-backend"]
build-backend = "pdm.backend"

[project]
name = "my-package"
version = "5.0.0"
""")

        project = detect_project(tmp_path)

        assert project.build_backend == "pdm"
        assert project.project_type == "pyproject"


class TestWorkspaceDetection:
    """Tests for monorepo/workspace package detection."""

    def test_detect_workspace_packages(self, tmp_path: Path):
        """Detect multiple packages in monorepo structure."""
        # Create packages/*/pyproject.toml pattern
        package1 = tmp_path / "packages" / "core"
        package1.mkdir(parents=True)
        (package1 / "pyproject.toml").write_text('[project]\nname = "core"')

        package2 = tmp_path / "packages" / "utils"
        package2.mkdir(parents=True)
        (package2 / "pyproject.toml").write_text('[project]\nname = "utils"')

        # Create libs/*/pyproject.toml pattern
        lib1 = tmp_path / "libs" / "common"
        lib1.mkdir(parents=True)
        (lib1 / "pyproject.toml").write_text('[project]\nname = "common"')

        packages = detect_workspace_packages(tmp_path)

        assert len(packages) == 3
        package_names = [p.name for p in packages]
        assert "core" in package_names
        assert "utils" in package_names
        assert "common" in package_names

    def test_detect_workspace_empty(self, tmp_path: Path):
        """Return empty list for single package project."""
        # Create only root pyproject.toml (not a monorepo)
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "single-package"')

        packages = detect_workspace_packages(tmp_path)

        # Should find the subdirectory if there are nested pyprojects
        # But since we only have root level, it should be empty or just root
        # Based on the glob patterns, it won't match root level
        assert len(packages) == 0

    def test_detect_workspace_excludes_common_dirs(self, tmp_path: Path):
        """Exclude common non-package directories."""
        # Create excluded directories
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "pyproject.toml").write_text('[project]\nname = "tests"')

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "pyproject.toml").write_text('[project]\nname = "docs"')

        # Create valid package
        package_dir = tmp_path / "packages" / "app"
        package_dir.mkdir(parents=True)
        (package_dir / "pyproject.toml").write_text('[project]\nname = "app"')

        packages = detect_workspace_packages(tmp_path)

        # Should only find app, not tests or docs
        assert len(packages) == 1
        assert packages[0].name == "app"


class TestProjectDetection:
    """Tests for general project detection."""

    def test_detect_project_not_found(self, tmp_path: Path):
        """Raise error when no project files found."""
        with pytest.raises(ProjectNotFoundError, match="No Python project found"):
            detect_project(tmp_path)

    def test_detect_setup_py(self, tmp_path: Path):
        """Detect project from setup.py."""
        setup_py = tmp_path / "setup.py"
        setup_py.write_text("""
from setuptools import setup

setup(
    name="my-package",
    version="1.0.0",
)
""")

        project = detect_project(tmp_path)

        assert project.project_type == "setup.py"
        assert project.build_backend == "setuptools"
        assert project.name == "my-package"
        assert project.version == "1.0.0"

    def test_detect_setup_cfg(self, tmp_path: Path):
        """Detect project from setup.cfg."""
        setup_cfg = tmp_path / "setup.cfg"
        setup_cfg.write_text("""
[metadata]
name = my-package
version = 2.0.0
""")

        project = detect_project(tmp_path)

        assert project.project_type == "setup.cfg"
        assert project.build_backend == "setuptools"
        assert project.name == "my-package"
        assert project.version == "2.0.0"

    def test_detect_pyproject_missing_sections(self, tmp_path: Path):
        """Raise error when pyproject.toml has no project or poetry section."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[tool.black]
line-length = 100
""")

        with pytest.raises(ProjectNotFoundError, match=r"missing \[project\] or \[tool\.poetry\]"):
            detect_project(tmp_path)

    def test_detect_pyproject_with_dynamic_version(self, tmp_path: Path):
        """Detect project with dynamic version."""
        # Create version file
        src_dir = tmp_path / "src" / "mypackage"
        src_dir.mkdir(parents=True)
        init_file = src_dir / "__init__.py"
        init_file.write_text('__version__ = "3.2.1"\n')

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mypackage"
dynamic = ["version"]

[tool.hatch.version]
path = "src/mypackage/__init__.py"
""")

        project = detect_project(tmp_path)

        assert project.name == "mypackage"
        assert project.version == "3.2.1"
        assert project.build_backend == "hatchling"
