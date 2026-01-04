"""Pydantic models for releasio configuration.

Configuration is read from pyproject.toml under [tool.releasio].
All fields have sensible defaults for zero-config usage.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class BranchConfig(BaseModel):
    """Configuration for a release branch channel.

    Allows different branches to produce different types of releases
    (e.g., alpha, beta, stable).
    """

    match: str = Field(
        description="Branch name or pattern to match (e.g., 'main', 'beta', 'release/*')",
    )
    prerelease: bool = Field(
        default=False,
        description="Whether releases from this branch are pre-releases",
    )
    prerelease_token: str | None = Field(
        default=None,
        description="Pre-release token to use (e.g., 'alpha', 'beta', 'rc')",
    )

    model_config = {"extra": "forbid"}

    def matches_branch(self, branch_name: str) -> bool:
        """Check if this config matches the given branch name.

        Supports exact matches and glob-style patterns with '*'.
        """
        pattern = self.match.replace("*", ".*")
        return bool(re.fullmatch(pattern, branch_name))


class CommitParser(BaseModel):
    """Configuration for a custom commit parser.

    Allows parsing non-conventional commit formats like Gitmoji, Angular, or custom patterns.
    Each parser defines a regex pattern with named groups to extract commit information.

    Example - Gitmoji support:
        CommitParser(
            pattern=r"^:sparkles:\\s*(?P<description>.+)$",
            type="feat",
            group="Features",
        )

    Example - Custom pattern with scope:
        CommitParser(
            pattern=r"^\\[(?P<scope>\\w+)\\]\\s*(?P<description>.+)$",
            type="change",
            group="Changes",
            scope_group="scope",
        )
    """

    pattern: str = Field(
        description=(
            "Regex pattern with named capture groups. "
            "Must include a group for the description (default: 'description')."
        ),
    )
    type: str = Field(
        description="Commit type to assign (e.g., 'feat', 'fix', 'breaking')",
    )
    group: str = Field(
        description="Changelog section name for this commit type (e.g., 'Features', 'Bug Fixes')",
    )
    scope_group: str | None = Field(
        default=None,
        description="Name of the regex group containing the scope (if any)",
    )
    description_group: str = Field(
        default="description",
        description="Name of the regex group containing the commit description",
    )
    breaking_indicator: str | None = Field(
        default=None,
        description=(
            "If set, commits matching this parser are treated as breaking changes. "
            "The value is the indicator that triggers this (e.g., ':boom:', '!')."
        ),
    )

    model_config = {"extra": "forbid"}


class CommitsConfig(BaseModel):
    """Configuration for conventional commit parsing.

    Determines how commits map to version bump types.
    Supports both conventional commits and custom parsers for other formats.
    """

    types_major: list[str] = Field(
        default_factory=list,
        description="Commit types that trigger a major version bump",
    )
    types_minor: list[str] = Field(
        default_factory=lambda: ["feat"],
        description="Commit types that trigger a minor version bump",
    )
    types_patch: list[str] = Field(
        default_factory=lambda: ["fix", "perf"],
        description="Commit types that trigger a patch version bump",
    )
    breaking_pattern: str = Field(
        default=r"BREAKING[ -]CHANGE:",
        description="Regex pattern to detect breaking changes in commit body",
    )
    scope_regex: str | None = Field(
        default=None,
        description="Only process commits matching this scope (for monorepos)",
    )
    skip_release_patterns: list[str] = Field(
        default_factory=lambda: ["[skip release]", "[release skip]", "[no release]"],
        description="Patterns in commit messages that skip release (case-insensitive)",
    )
    commit_parsers: list[CommitParser] = Field(
        default_factory=list,
        description=(
            "Custom commit parsers for non-conventional formats (e.g., Gitmoji, Angular). "
            "Parsers are tried in order before falling back to conventional commits."
        ),
    )
    use_conventional_fallback: bool = Field(
        default=True,
        description=(
            "Fall back to conventional commit parsing if no custom parser matches. "
            "Set to False to only use custom parsers."
        ),
    )

    model_config = {"extra": "forbid"}


class ChangelogConfig(BaseModel):
    """Configuration for changelog generation.

    Supports git-cliff for advanced changelog generation, with a native fallback
    when git-cliff is not available or when `native_fallback` is enabled.
    """

    enabled: bool = Field(
        default=True,
        description="Whether to generate changelog",
    )
    path: Path = Field(
        default=Path("CHANGELOG.md"),
        description="Path to the changelog file",
    )
    template: str | None = Field(
        default=None,
        description="Custom git-cliff template (path or inline)",
    )
    header: str | None = Field(
        default=None,
        description="Custom header for the changelog",
    )
    use_github_prs: bool = Field(
        default=False,
        description="Use GitHub PR-based changelog (recommended for squash merge workflows)",
    )
    ignore_authors: list[str] = Field(
        default_factory=lambda: [
            "dependabot[bot]",
            "dependabot-preview[bot]",
            "renovate[bot]",
            "renovate-bot",
            "github-actions[bot]",
            "pre-commit-ci[bot]",
            "codecov[bot]",
            "semantic-release-bot",
            "allcontributors[bot]",
            "snyk-bot",
            "greenkeeper[bot]",
            "imgbot[bot]",
            "depfu[bot]",
            "pyup-bot",
            "mergify[bot]",
        ],
        description="Authors to exclude from changelog (bots)",
    )
    # Custom template settings for fallback/native changelog
    section_headers: dict[str, str] = Field(
        default_factory=lambda: {
            "breaking": "⚠️ Breaking Changes",
            "feat": "✨ Features",
            "fix": "🐛 Bug Fixes",
            "perf": "⚡ Performance",
            "docs": "📚 Documentation",
            "refactor": "♻️ Refactoring",
            "test": "🧪 Tests",
            "build": "📦 Build",
            "ci": "🔧 CI",
            "style": "💄 Style",
            "chore": "🔨 Chores",
            "other": "📝 Other",
        },
        description="Custom section headers for each commit type (supports emojis)",
    )
    show_authors: bool = Field(
        default=False,
        description="Include author names in changelog entries",
    )
    show_commit_hash: bool = Field(
        default=False,
        description="Include short commit hash in changelog entries",
    )
    commit_template: str | None = Field(
        default=None,
        description=(
            "Custom template for each commit entry. "
            "Available variables: {scope}, {description}, {author}, {hash}, {body}, {type}"
        ),
    )
    native_fallback: bool = Field(
        default=True,
        description=(
            "Generate changelog natively if git-cliff is not available. "
            "Uses section_headers and commit_template settings."
        ),
    )
    generate_cliff_config: bool = Field(
        default=False,
        description=(
            "Auto-generate git-cliff config from releasio settings."
            "Maps section_headers and commit_parsers to cliff.toml format."
        ),
    )
    cliff_body_template: str | None = Field(
        default=None,
        description=(
            "Custom body template for auto-generated git-cliff config. "
            "Uses git-cliff's Tera template syntax."
        ),
    )

    model_config = {"extra": "forbid"}


class VersionConfig(BaseModel):
    """Configuration for version management."""

    initial_version: str = Field(
        default="0.1.0",
        description="Version to use for first release",
    )
    tag_prefix: str = Field(
        default="v",
        description="Prefix for git tags (e.g., 'v' for 'v1.0.0')",
    )
    pre_release: str | None = Field(
        default=None,
        description="Pre-release identifier (e.g., 'alpha', 'beta', 'rc')",
    )
    version_files: list[Path] = Field(
        default_factory=list,
        description="Additional files containing version to update",
    )
    auto_detect_version_files: bool = Field(
        default=False,
        description=(
            "Automatically detect and update version files "
            "(e.g., __init__.py, __version__.py) in addition to pyproject.toml"
        ),
    )
    update_lock_file: bool = Field(
        default=True,
        description=(
            "Automatically update lock file (uv.lock, poetry.lock, pdm.lock) "
            "after version bump to keep it in sync"
        ),
    )

    model_config = {"extra": "forbid"}


class GitHubConfig(BaseModel):
    """Configuration for GitHub integration."""

    owner: str | None = Field(
        default=None,
        description="Repository owner (auto-detected from git remote if not set)",
    )
    repo: str | None = Field(
        default=None,
        description="Repository name (auto-detected from git remote if not set)",
    )
    api_url: str = Field(
        default="https://api.github.com",
        description="GitHub API URL (for GitHub Enterprise, e.g., https://github.mycompany.com/api/v3)",
    )
    release_pr_branch: str = Field(
        default="releasio/release",
        description="Branch name for release PRs",
    )
    release_pr_labels: list[str] = Field(
        default_factory=lambda: ["release"],
        description="Labels to apply to release PRs",
    )
    draft_releases: bool = Field(
        default=False,
        description="Create releases as drafts",
    )

    model_config = {"extra": "forbid"}


class PublishConfig(BaseModel):
    """Configuration for PyPI publishing."""

    enabled: bool = Field(
        default=True,
        description="Whether to publish to PyPI",
    )
    registry: str = Field(
        default="https://upload.pypi.org/legacy/",
        description="PyPI registry URL",
    )
    tool: Literal["uv", "twine"] = Field(
        default="uv",
        description="Tool to use for publishing",
    )
    trusted_publishing: bool = Field(
        default=True,
        description="Use OIDC trusted publishing when available",
    )

    model_config = {"extra": "forbid"}


class PackagesConfig(BaseModel):
    """Configuration for monorepo support."""

    paths: list[str] = Field(
        default_factory=list,
        description="Package directories for monorepo (empty = single package at root)",
    )
    independent: bool = Field(
        default=True,
        description="Use independent versioning per package",
    )

    model_config = {"extra": "forbid"}


class HooksConfig(BaseModel):
    """Configuration for pre/post release hooks.

    Hooks are shell commands executed at specific points in the release process.
    Commands can use template variables like {version}, {prev_version}, {bump_type}.
    """

    pre_bump: list[str] = Field(
        default_factory=list,
        description="Commands to run before version bump (e.g., ['npm run lint'])",
    )
    post_bump: list[str] = Field(
        default_factory=list,
        description="Commands to run after version bump (e.g., ['npm run build'])",
    )
    pre_release: list[str] = Field(
        default_factory=list,
        description="Commands to run before release (e.g., ['pytest'])",
    )
    post_release: list[str] = Field(
        default_factory=list,
        description="Commands to run after release (e.g., ['./scripts/notify.sh'])",
    )
    build: str | None = Field(
        default=None,
        description=(
            "Custom build command to use instead of the default 'uv build'. "
            "Set to build the package before publishing. "
            "Available variables: {version}, {project_path}"
        ),
    )

    model_config = {"extra": "forbid"}


class ReleasePyConfig(BaseModel):
    """Main configuration for releasio.

    Read from pyproject.toml under [tool.releasio].
    All fields have sensible defaults for zero-config usage.
    """

    # Core settings
    default_branch: str = Field(
        default="main",
        description="Default branch for releases",
    )
    allow_dirty: bool = Field(
        default=False,
        description="Allow releases from dirty working directory",
    )
    tag_prefix: Annotated[str, Field(deprecated="Use version.tag_prefix instead")] = Field(
        default="v",
        description="Prefix for git tags (deprecated: use version.tag_prefix)",
    )
    changelog_path: Annotated[Path, Field(deprecated="Use changelog.path instead")] = Field(
        default=Path("CHANGELOG.md"),
        description="Path to changelog (deprecated: use changelog.path)",
    )

    # Sub-configurations
    commits: CommitsConfig = Field(default_factory=CommitsConfig)
    changelog: ChangelogConfig = Field(default_factory=ChangelogConfig)
    version: VersionConfig = Field(default_factory=VersionConfig)
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    publish: PublishConfig = Field(default_factory=PublishConfig)
    packages: PackagesConfig = Field(default_factory=PackagesConfig)
    hooks: HooksConfig = Field(default_factory=HooksConfig)
    branches: dict[str, BranchConfig] = Field(
        default_factory=dict,
        description=(
            "Branch-specific release configurations for multi-channel releases. "
            "Keys are channel names (e.g., 'main', 'beta', 'alpha')."
        ),
    )

    model_config = {"extra": "forbid"}

    @property
    def effective_tag_prefix(self) -> str:
        """Get the effective tag prefix (preferring version.tag_prefix)."""
        # If version.tag_prefix is explicitly set to something other than default,
        # use it. Otherwise fall back to the top-level tag_prefix.
        if self.version.tag_prefix != "v":
            return self.version.tag_prefix
        return self.tag_prefix

    @property
    def effective_changelog_path(self) -> Path:
        """Get the effective changelog path (preferring changelog.path)."""
        if self.changelog.path != Path("CHANGELOG.md"):
            return self.changelog.path
        return self.changelog_path

    @property
    def is_monorepo(self) -> bool:
        """Check if this is a monorepo configuration."""
        return len(self.packages.paths) > 0

    def get_branch_config(self, branch_name: str) -> BranchConfig | None:
        """Get the branch configuration for the given branch.

        Searches through configured branches and returns the first match.
        Returns None if no matching branch config is found.

        Args:
            branch_name: The current git branch name

        Returns:
            BranchConfig if a match is found, None otherwise
        """
        for config in self.branches.values():
            if config.matches_branch(branch_name):
                return config
        return None

    def get_effective_prerelease(self, branch_name: str) -> str | None:
        """Get the effective pre-release token for the given branch.

        Checks branch-specific config first, then falls back to version.pre_release.

        Args:
            branch_name: The current git branch name

        Returns:
            Pre-release token (e.g., 'alpha', 'beta') or None for stable releases
        """
        branch_config = self.get_branch_config(branch_name)
        if branch_config and branch_config.prerelease:
            return branch_config.prerelease_token
        return self.version.pre_release
