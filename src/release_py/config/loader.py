"""Configuration loading from pyproject.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from release_py.config.models import ReleasePyConfig
from release_py.exceptions import ConfigNotFoundError, ConfigValidationError


def find_pyproject_toml(start_path: Path | None = None) -> Path:
    """Find pyproject.toml by walking up from start_path.

    Args:
        start_path: Directory to start searching from. Defaults to cwd.

    Returns:
        Path to pyproject.toml

    Raises:
        ConfigNotFoundError: If no pyproject.toml is found
    """
    current = (start_path or Path.cwd()).resolve()

    while current != current.parent:
        pyproject = current / "pyproject.toml"
        if pyproject.is_file():
            return pyproject
        current = current.parent

    # Check root as well
    pyproject = current / "pyproject.toml"
    if pyproject.is_file():
        return pyproject

    raise ConfigNotFoundError(
        f"No pyproject.toml found in {start_path or Path.cwd()} or any parent directory"
    )


def load_pyproject_toml(path: Path) -> dict[str, Any]:
    """Load and parse pyproject.toml.

    Args:
        path: Path to pyproject.toml

    Returns:
        Parsed TOML as dictionary

    Raises:
        ConfigNotFoundError: If file doesn't exist
        ConfigValidationError: If TOML parsing fails
    """
    if not path.is_file():
        raise ConfigNotFoundError(f"File not found: {path}")

    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigValidationError(f"Invalid TOML in {path}: {e}") from e


def extract_release_py_config(pyproject: dict[str, Any]) -> dict[str, Any]:
    """Extract [tool.releasio] section from pyproject.toml data.

    Args:
        pyproject: Parsed pyproject.toml data

    Returns:
        The releasio configuration dict (empty if not present)
    """
    tool: dict[str, Any] = pyproject.get("tool", {})
    result: dict[str, Any] = tool.get("releasio", {})
    return result


def load_config(path: Path | None = None) -> ReleasePyConfig:
    """Load releasio configuration from pyproject.toml.

    Configuration is read from [tool.releasio] section.
    Missing config uses sensible defaults.

    Args:
        path: Path to pyproject.toml, or directory to search from.
              If None, searches from current directory.

    Returns:
        Validated configuration

    Raises:
        ConfigNotFoundError: If pyproject.toml not found
        ConfigValidationError: If configuration is invalid
    """
    # Determine the pyproject.toml path
    if path is None:
        pyproject_path = find_pyproject_toml()
    elif path.is_dir():
        pyproject_path = find_pyproject_toml(path)
    else:
        pyproject_path = path

    # Load and parse
    pyproject_data = load_pyproject_toml(pyproject_path)
    config_data = extract_release_py_config(pyproject_data)

    # Validate and return
    try:
        return ReleasePyConfig.model_validate(config_data)
    except ValidationError as e:
        errors = []
        for error in e.errors():
            loc = ".".join(str(x) for x in error["loc"])
            msg = error["msg"]
            errors.append(f"  - {loc}: {msg}")
        raise ConfigValidationError(
            f"Invalid configuration in {pyproject_path}:\n" + "\n".join(errors)
        ) from e


def get_project_name(path: Path | None = None) -> str:
    """Get the project name from pyproject.toml.

    Args:
        path: Path to pyproject.toml or directory to search from

    Returns:
        Project name

    Raises:
        ConfigNotFoundError: If pyproject.toml not found
        ConfigValidationError: If project name not found
    """
    if path is None:
        pyproject_path = find_pyproject_toml()
    elif path.is_dir():
        pyproject_path = find_pyproject_toml(path)
    else:
        pyproject_path = path

    pyproject_data = load_pyproject_toml(pyproject_path)

    try:
        name: str = pyproject_data["project"]["name"]
    except KeyError as e:
        raise ConfigValidationError(f"Missing [project].name in {pyproject_path}") from e
    else:
        return name


def get_project_version(path: Path | None = None) -> str:
    """Get the project version from pyproject.toml.

    Supports both PEP 621 format ([project].version) and
    Poetry format ([tool.poetry].version).

    Args:
        path: Path to pyproject.toml or directory to search from

    Returns:
        Project version string

    Raises:
        ConfigNotFoundError: If pyproject.toml not found
        ConfigValidationError: If project version not found
    """
    if path is None:
        pyproject_path = find_pyproject_toml()
    elif path.is_dir():
        pyproject_path = find_pyproject_toml(path)
    else:
        pyproject_path = path

    pyproject_data = load_pyproject_toml(pyproject_path)

    # Try PEP 621 format first
    if "project" in pyproject_data and "version" in pyproject_data["project"]:
        return str(pyproject_data["project"]["version"])

    # Try Poetry format
    if (
        "tool" in pyproject_data
        and "poetry" in pyproject_data["tool"]
        and "version" in pyproject_data["tool"]["poetry"]
    ):
        return str(pyproject_data["tool"]["poetry"]["version"])

    raise ConfigValidationError(
        f"Missing version in {pyproject_path}. "
        "Expected [project].version or [tool.poetry].version. "
        "Dynamic versioning is not yet supported."
    )
