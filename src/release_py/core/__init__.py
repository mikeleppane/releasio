"""Core business logic for releasio.

This module contains the fundamental building blocks:
- Version parsing and manipulation (PEP 440 compliant)
- Conventional commit parsing
- Changelog generation via git-cliff
- Release orchestration
"""

from __future__ import annotations

from release_py.core.changelog import generate_changelog, get_bump_from_git_cliff
from release_py.core.commits import (
    ParsedCommit,
    calculate_bump,
    format_commit_for_changelog,
    get_breaking_changes,
    group_commits_by_type,
    parse_commits,
)
from release_py.core.version import BumpType, PreRelease, Version, parse_version

__all__ = [
    # Version
    "BumpType",
    # Commits
    "ParsedCommit",
    "PreRelease",
    "Version",
    "calculate_bump",
    "format_commit_for_changelog",
    # Changelog
    "generate_changelog",
    "get_breaking_changes",
    "get_bump_from_git_cliff",
    "group_commits_by_type",
    "parse_commits",
    "parse_version",
]
