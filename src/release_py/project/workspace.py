"""Monorepo/workspace support.

This module provides functionality for handling Python monorepos
with multiple packages.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from release_py.project.detector import ProjectInfo, detect_project

if TYPE_CHECKING:
    from release_py.config.models import ReleasePyConfig


@dataclass
class WorkspacePackage:
    """A package within a workspace/monorepo.

    Attributes:
        name: Package name
        path: Path to package directory
        version: Current version
        info: Full project info
    """

    name: str
    path: Path
    version: str
    info: ProjectInfo


def detect_workspace(
    config: ReleasePyConfig,
    root_path: Path | None = None,
) -> list[WorkspacePackage]:
    """Detect packages in a workspace.

    Uses configuration from [tool.releasio.packages] if available,
    otherwise attempts auto-detection.

    Args:
        config: Release configuration
        root_path: Workspace root path. Defaults to current directory.

    Returns:
        List of detected packages
    """
    root = (root_path or Path.cwd()).resolve()
    packages: list[WorkspacePackage] = []

    if config.packages.paths:
        # Use configured package paths
        for pkg_path_str in config.packages.paths:
            pkg_path = root / pkg_path_str
            if pkg_path.is_dir():
                try:
                    info = detect_project(pkg_path)
                    packages.append(
                        WorkspacePackage(
                            name=info.name,
                            path=pkg_path,
                            version=info.version,
                            info=info,
                        )
                    )
                except Exception:
                    # Skip packages that can't be detected
                    pass
    else:
        # Auto-detect packages using common patterns
        from release_py.project.detector import detect_workspace_packages

        for pkg_path in detect_workspace_packages(root):
            try:
                info = detect_project(pkg_path)
                packages.append(
                    WorkspacePackage(
                        name=info.name,
                        path=pkg_path,
                        version=info.version,
                        info=info,
                    )
                )
            except Exception:
                pass

    return packages


def get_package_by_name(
    packages: list[WorkspacePackage],
    name: str,
) -> WorkspacePackage | None:
    """Find a package by name.

    Args:
        packages: List of packages to search
        name: Package name to find

    Returns:
        The package if found, None otherwise
    """
    for pkg in packages:
        if pkg.name == name:
            return pkg
    return None
