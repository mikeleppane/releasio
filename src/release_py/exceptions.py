"""Exception hierarchy for releasio.

All exceptions inherit from ReleasePyError, allowing callers to catch
all releasio errors with a single except clause if desired.
"""

from __future__ import annotations


class ReleasePyError(Exception):
    """Base exception for all releasio errors."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


# =============================================================================
# Configuration Errors
# =============================================================================


class ConfigError(ReleasePyError):
    """Error in configuration parsing or validation."""


class ConfigNotFoundError(ConfigError):
    """Configuration file not found."""


class ConfigValidationError(ConfigError):
    """Configuration values failed validation."""


# =============================================================================
# Git / VCS Errors
# =============================================================================


class GitError(ReleasePyError):
    """Error during git operations."""


class NotARepositoryError(GitError):
    """The directory is not a git repository."""


class DirtyRepositoryError(GitError):
    """Repository has uncommitted changes."""


class NoCommitsError(GitError):
    """No commits found since last tag."""


class TagExistsError(GitError):
    """Tag already exists."""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        super().__init__(f"Tag '{tag}' already exists")


# =============================================================================
# Project Detection Errors
# =============================================================================


class ProjectError(ReleasePyError):
    """Error related to project detection or manipulation."""


class ProjectNotFoundError(ProjectError):
    """No Python project found at the specified path."""


class VersionNotFoundError(ProjectError):
    """Could not find version in project files."""


class MultipleVersionsError(ProjectError):
    """Found conflicting versions in different files."""


# =============================================================================
# Version Errors
# =============================================================================


class VersionError(ReleasePyError):
    """Error related to version parsing or manipulation."""


class InvalidVersionError(VersionError):
    """Version string is not valid according to PEP 440."""

    def __init__(self, version: str, reason: str | None = None) -> None:
        self.version = version
        msg = f"Invalid version: '{version}'"
        if reason:
            msg = f"{msg} ({reason})"
        super().__init__(msg)


# =============================================================================
# GitHub / Forge Errors
# =============================================================================


class ForgeError(ReleasePyError):
    """Error during forge (GitHub/GitLab/Gitea) operations."""


class AuthenticationError(ForgeError):
    """Authentication failed."""


class RateLimitError(ForgeError):
    """API rate limit exceeded."""

    def __init__(self, reset_at: str | None = None) -> None:
        self.reset_at = reset_at
        msg = "API rate limit exceeded"
        if reset_at:
            msg = f"{msg}. Resets at {reset_at}"
        super().__init__(msg)


class PullRequestError(ForgeError):
    """Error during pull request operations."""


class ReleaseError(ForgeError):
    """Error during release operations."""


# =============================================================================
# Publishing Errors
# =============================================================================


class PublishError(ReleasePyError):
    """Error during package publishing."""


class BuildError(PublishError):
    """Failed to build the package."""


class UploadError(PublishError):
    """Failed to upload to package registry."""


class AlreadyPublishedError(PublishError):
    """This version is already published."""

    def __init__(self, package: str, version: str) -> None:
        self.package = package
        self.version = version
        super().__init__(f"{package} {version} is already published")


# =============================================================================
# Changelog Errors
# =============================================================================


class ChangelogError(ReleasePyError):
    """Error during changelog generation."""


class GitCliffError(ChangelogError):
    """git-cliff command failed."""

    def __init__(self, message: str, stderr: str | None = None) -> None:
        self.stderr = stderr
        super().__init__(message)
