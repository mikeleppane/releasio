"""PyPI publishing via uv or twine.

This module provides functionality for building and publishing
Python packages to PyPI using either uv or twine.

uv is preferred as it's faster and has better UX, but twine
is supported as a fallback.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

from release_py.exceptions import BuildError, PublishError, UploadError

if TYPE_CHECKING:
    from pathlib import Path

    from release_py.config.models import PublishConfig


def _get_build_commands(project_path: Path, preferred_tool: str) -> list[tuple[list[str], str]]:
    """Get build commands in priority order based on preferred tool.

    Args:
        project_path: Project directory
        preferred_tool: Tool specified in config (uv, poetry, pdm, twine)

    Returns:
        List of (command, tool_name) tuples in priority order
    """
    # If a specific tool is preferred, try it first
    if preferred_tool == "poetry" and (project_path / "poetry.lock").exists():
        return [
            (["poetry", "build"], "poetry"),
            (["uv", "build"], "uv"),
            (["hatch", "build"], "hatch"),
            (["python", "-m", "build"], "python-build"),
        ]
    if preferred_tool == "pdm" and (project_path / "pdm.lock").exists():
        return [
            (["pdm", "build"], "pdm"),
            (["uv", "build"], "uv"),
            (["hatch", "build"], "hatch"),
            (["python", "-m", "build"], "python-build"),
        ]
    # Default: uv first (preferred_tool="uv" or "twine")
    return [
        (["uv", "build"], "uv"),
        (["hatch", "build"], "hatch"),
        (["python", "-m", "build"], "python-build"),
    ]


def build_package(
    project_path: Path,
    *,
    clean: bool = True,
    custom_command: str | None = None,
    version: str | None = None,
    tool: str = "uv",
) -> list[Path]:
    """Build the package using configured tool or fallback chain.

    Args:
        project_path: Path to the project directory
        clean: Whether to clean dist/ before building
        custom_command: Custom build command (supports {version}, {project_path} variables)
        version: Version being built (for template substitution)
        tool: Preferred build tool (from config.publish.tool)

    Returns:
        List of paths to built distribution files

    Raises:
        BuildError: If the build fails
    """
    dist_dir = project_path / "dist"

    # Clean dist directory if requested
    if clean and dist_dir.exists():
        shutil.rmtree(dist_dir)

    # Use custom command if provided
    if custom_command:
        # Substitute template variables
        template_vars = {
            "version": version or "",
            "project_path": str(project_path),
        }
        expanded_cmd = custom_command.format(**template_vars)

        try:
            subprocess.run(
                expanded_cmd,
                shell=True,
                cwd=project_path,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise BuildError(f"Custom build command failed:\n{e.stderr}") from e
    else:
        # Validate lock file exists for poetry/pdm before trying to build
        if tool in ("poetry", "pdm"):
            lock_file = f"{tool}.lock"
            if not (project_path / lock_file).exists():
                raise BuildError(
                    f"tool is set to '{tool}' but {lock_file} not found. "
                    f"Run '{tool} install' or change tool to 'uv'"
                )

        # Get build commands based on preferred tool
        build_commands = _get_build_commands(project_path, tool)

        for cmd, tool_name in build_commands:
            if shutil.which(cmd[0]) is not None:
                # Additional validation for poetry/pdm
                if tool_name in ("poetry", "pdm"):
                    lock_file = f"{tool_name}.lock"
                    if not (project_path / lock_file).exists():
                        # Skip this tool if lock file missing
                        continue

                try:
                    subprocess.run(
                        cmd,
                        cwd=project_path,
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    break
                except subprocess.CalledProcessError as e:
                    raise BuildError(f"Build with {tool_name} failed:\n{e.stderr}") from e
        else:
            # No tool succeeded
            raise BuildError(
                "No build tool found. Install one of: uv, poetry, pdm, hatch, or build"
            )

    # Find built files
    if not dist_dir.exists():
        raise BuildError("Build completed but dist/ directory not found")

    dist_files = list(dist_dir.glob("*.whl")) + list(dist_dir.glob("*.tar.gz"))

    if not dist_files:
        raise BuildError("Build completed but no distribution files found in dist/")

    return dist_files


def publish_package(
    project_path: Path,
    config: PublishConfig,
    *,
    dist_files: list[Path] | None = None,
) -> None:
    """Publish the package to PyPI.

    Uses the tool specified in config (uv, poetry, pdm, or twine).
    For trusted publishing (OIDC), no token is needed.

    Args:
        project_path: Path to the project directory
        config: Publishing configuration
        dist_files: Specific files to publish. If None, publishes all in dist/

    Raises:
        PublishError: If publishing fails
    """
    if not config.enabled:
        return

    dist_dir = project_path / "dist"

    if dist_files is None:
        dist_files = list(dist_dir.glob("*.whl")) + list(dist_dir.glob("*.tar.gz"))

    if not dist_files:
        raise PublishError("No distribution files to publish")

    # Use configured tool
    if config.tool == "uv":
        _publish_with_uv(dist_files, config)
    elif config.tool == "poetry":
        _publish_with_poetry(dist_files, config)
    elif config.tool == "pdm":
        _publish_with_pdm(dist_files, config)
    else:  # twine
        _publish_with_twine(dist_files, config)


def _publish_with_uv(dist_files: list[Path], config: PublishConfig) -> None:
    """Publish using uv publish."""
    if shutil.which("uv") is None:
        raise PublishError("uv not found. Install with: pip install uv")

    cmd = ["uv", "publish"]

    # Add registry if not default PyPI
    if config.registry != "https://upload.pypi.org/legacy/":
        cmd.extend(["--publish-url", config.registry])

    # Add files
    cmd.extend(str(f) for f in dist_files)

    try:
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        if "already exists" in e.stderr.lower():
            raise UploadError("This version has already been published to PyPI") from e
        raise UploadError(f"uv publish failed:\n{e.stderr}") from e


def _publish_with_twine(dist_files: list[Path], config: PublishConfig) -> None:
    """Publish using twine."""
    if shutil.which("twine") is None:
        raise PublishError("twine not found. Install with: pip install twine")

    cmd = [
        "twine",
        "upload",
        "--repository-url",
        config.registry,
    ]

    # Add files
    cmd.extend(str(f) for f in dist_files)

    try:
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        if "already exists" in e.stderr.lower():
            raise UploadError("This version has already been published to PyPI") from e
        raise UploadError(f"twine upload failed:\n{e.stderr}") from e


def _publish_with_poetry(dist_files: list[Path], config: PublishConfig) -> None:
    """Publish using poetry publish.

    Poetry publish supports:
    - --repository: Repository name or URL
    - --username: Username for authentication
    - --password: Password/token for authentication

    Args:
        dist_files: Distribution files to publish
        config: Publishing configuration

    Raises:
        PublishError: If poetry not found
        UploadError: If publishing fails
    """
    if shutil.which("poetry") is None:
        raise PublishError("poetry not found. Install with: pip install poetry")

    cmd = ["poetry", "publish"]

    # Add repository if not default PyPI
    if config.registry != "https://upload.pypi.org/legacy/":
        cmd.extend(["--repository", config.registry])

    # Get project directory from dist_files path
    if dist_files:
        project_dir = dist_files[0].parent.parent
    else:
        raise PublishError("No distribution files to publish")

    try:
        subprocess.run(
            cmd,
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.lower()
        if "already exists" in stderr or "file already uploaded" in stderr:
            raise UploadError("This version has already been published to PyPI") from e
        if "authentication" in stderr or "credentials" in stderr:
            raise PublishError(
                "Poetry authentication failed. "
                f"Configure with: poetry config pypi-token.pypi <token>\n{e.stderr}"
            ) from e
        raise UploadError(f"poetry publish failed:\n{e.stderr}") from e


def _publish_with_pdm(dist_files: list[Path], config: PublishConfig) -> None:
    """Publish using pdm publish.

    PDM publish supports:
    - --repository: Repository name or URL
    - --username: Username for authentication
    - --password: Password/token for authentication
    - --no-build: Skip building (we already built)

    Args:
        dist_files: Distribution files to publish
        config: Publishing configuration

    Raises:
        PublishError: If pdm not found
        UploadError: If publishing fails
    """
    if shutil.which("pdm") is None:
        raise PublishError("pdm not found. Install with: pip install pdm")

    cmd = ["pdm", "publish", "--no-build"]

    # Add repository if not default PyPI
    if config.registry != "https://upload.pypi.org/legacy/":
        cmd.extend(["--repository", config.registry])

    # Get project directory
    if dist_files:
        project_dir = dist_files[0].parent.parent
    else:
        raise PublishError("No distribution files to publish")

    try:
        subprocess.run(
            cmd,
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.lower()
        if "already exists" in stderr or "file already uploaded" in stderr:
            raise UploadError("This version has already been published to PyPI") from e
        if "authentication" in stderr or "credentials" in stderr:
            raise PublishError(
                "PDM authentication failed. Set PDM_PUBLISH_PASSWORD env var "
                f"or configure with: pdm config pypi.token <token>\n{e.stderr}"
            ) from e
        raise UploadError(f"pdm publish failed:\n{e.stderr}") from e


def check_pypi_version_exists(
    package_name: str,
    version: str,
) -> bool:
    """Check if a version is already published to PyPI.

    Args:
        package_name: Name of the package
        version: Version to check

    Returns:
        True if the version exists on PyPI
    """
    import httpx

    url = f"https://pypi.org/pypi/{package_name}/{version}/json"

    try:
        response = httpx.get(url, timeout=10)
    except httpx.HTTPError:
        return False
    else:
        return response.status_code == 200
