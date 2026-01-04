"""Implementation of the 'release-pr' command.

The release-pr command creates or updates a pull request containing
the version bump and changelog updates.
"""

from __future__ import annotations

import contextlib
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.panel import Panel

from release_py.config import load_config
from release_py.core.commits import calculate_bump, filter_skip_release_commits, parse_commits
from release_py.core.version import Version
from release_py.vcs import GitRepository

if TYPE_CHECKING:
    from rich.console import Console


def run_release_pr(
    path: str | None,
    dry_run: bool,
    console: Console,
    err_console: Console,
) -> None:
    """Run the release-pr command.

    Args:
        path: Optional path to project directory
        dry_run: Whether to just preview without creating PR
        console: Console for standard output
        err_console: Console for error output
    """
    project_path = Path(path) if path else Path.cwd()

    # Load configuration
    try:
        config = load_config(project_path)
    except Exception as e:
        err_console.print(f"[red]Error loading config:[/] {e}")
        raise SystemExit(1) from e

    # Initialize git repository
    try:
        repo = GitRepository(project_path)
    except Exception as e:
        err_console.print(f"[red]Error:[/] {e}")
        raise SystemExit(1) from e

    # Get current version
    from release_py.config.loader import get_project_name, get_project_version

    try:
        project_name = get_project_name(project_path)
        current_version_str = get_project_version(project_path)
        current_version = Version.parse(current_version_str)
    except Exception as e:
        err_console.print(f"[red]Error getting project info:[/] {e}")
        raise SystemExit(1) from e

    # Get latest tag
    tag_pattern = f"{config.effective_tag_prefix}*"
    latest_tag = repo.get_latest_tag(tag_pattern)

    # Detect first release (no existing tags)
    is_first_release = latest_tag is None

    # Get commits since last tag
    commits = repo.get_commits_since_tag(latest_tag)

    if not commits:
        console.print(
            Panel(
                "[yellow]No commits found since last release.[/]\n\n"
                "Make some commits and try again.",
                title="No Changes",
                border_style="yellow",
            )
        )
        return

    # Filter out commits with skip release markers
    commits = filter_skip_release_commits(commits, config.commits.skip_release_patterns)

    if not commits:
        console.print(
            Panel(
                "[yellow]All commits have skip release markers.[/]\n\nNo release needed.",
                title="No Changes",
                border_style="yellow",
            )
        )
        return

    # Parse commits and calculate bump
    parsed = parse_commits(commits, config.commits)
    bump_type = calculate_bump(parsed, config.commits)

    # Calculate next version
    if is_first_release:
        # Use initial_version for first release
        next_version = Version.parse(config.version.initial_version)
    else:
        next_version = current_version.bump(bump_type)

    # Apply pre-release identifier based on branch config
    current_branch = repo.get_current_branch()
    effective_prerelease = config.get_effective_prerelease(current_branch)

    if effective_prerelease:
        next_version = next_version.with_prerelease(effective_prerelease)
        branch_config = config.get_branch_config(current_branch)
        if branch_config and branch_config.prerelease:
            console.print(
                f"[dim]Auto-detected pre-release channel [cyan]{effective_prerelease}[/] "
                f"from branch [cyan]{current_branch}[/][/]"
            )

    # Try to get GitHub URL for generating links
    github_url: str | None = None
    try:
        owner, repo_name = repo.parse_github_remote()
        github_owner = config.github.owner or owner
        github_repo = config.github.repo or repo_name
        # Use configured API URL base, but strip /api/v3 for web links
        api_url = config.github.api_url.rstrip("/")
        if api_url == "https://api.github.com":
            github_url = f"https://github.com/{github_owner}/{github_repo}"
        else:
            # GitHub Enterprise - strip /api/v3 suffix for web URL
            base_url = api_url.replace("/api/v3", "").replace("/api", "")
            github_url = f"{base_url}/{github_owner}/{github_repo}"
    except Exception:
        # No valid GitHub remote - links will be omitted
        github_owner = None
        github_repo = None

    # Generate PR title and body
    pr_title = f"chore(release): prepare {project_name} v{next_version}"
    pr_body = _generate_pr_body(
        project_name, current_version, next_version, parsed, is_first_release, github_url
    )

    if dry_run:
        console.print()
        console.print(
            Panel(
                f"[bold]Title:[/] {pr_title}\n\n"
                f"[bold]Branch:[/] {config.github.release_pr_branch}\n"
                f"[bold]Base:[/] {config.default_branch}\n"
                f"[bold]Labels:[/] {', '.join(config.github.release_pr_labels)}",
                title="[yellow]Pull Request Preview (Dry Run)[/]",
                border_style="yellow",
            )
        )
        console.print()
        console.print("[bold]PR Body:[/]")
        console.print(Panel(pr_body, border_style="dim"))
        console.print("\n[dim]Run without [cyan]--dry-run[/] to create the PR.[/]")
        return

    # Actually create the PR
    console.print(f"\n[bold]Creating release PR for v{next_version}...[/]\n")

    try:
        # Use already-parsed GitHub info, or fail if not available
        if github_owner is None or github_repo is None:
            owner, repo_name = repo.parse_github_remote()
            github_owner = config.github.owner or owner
            github_repo = config.github.repo or repo_name

        console.print(f"  • Repository: [cyan]{github_owner}/{github_repo}[/]")
        console.print(f"  • Branch: [cyan]{config.github.release_pr_branch}[/]")

        # Create release branch and make changes
        from release_py.core.changelog import generate_changelog
        from release_py.project.pyproject import (
            detect_version_files,
            update_pyproject_version,
            update_version_file,
            update_version_in_plain_file,
        )

        # Checkout release branch
        repo.checkout(config.github.release_pr_branch, create=True)
        console.print(f"  [green]✓[/] Created branch {config.github.release_pr_branch}")

        # Track files to commit
        files_to_commit: list[Path] = [project_path / "pyproject.toml"]

        # Update version in pyproject.toml
        update_pyproject_version(project_path, str(next_version))
        console.print("  [green]✓[/] Updated pyproject.toml")

        # Update additional version files (explicitly configured)
        for version_file in config.version.version_files:
            version_file_path = project_path / version_file
            try:
                if version_file_path.name == "VERSION":
                    update_version_in_plain_file(version_file_path, str(next_version))
                else:
                    update_version_file(version_file_path, str(next_version))
                console.print(f"  [green]✓[/] Updated version in {version_file}")
                files_to_commit.append(version_file_path)
            except Exception as e:
                console.print(f"  [yellow]⚠[/] Could not update {version_file}: {e}")

        # Auto-detect and update version files if enabled
        if config.version.auto_detect_version_files:
            detected_files = detect_version_files(project_path)
            for version_file_path in detected_files:
                relative_path = version_file_path.relative_to(project_path)
                if relative_path in config.version.version_files:
                    continue
                try:
                    if version_file_path.name == "VERSION":
                        update_version_in_plain_file(version_file_path, str(next_version))
                    else:
                        update_version_file(version_file_path, str(next_version))
                    console.print(f"  [green]✓[/] Updated {relative_path} (auto-detected)")
                    files_to_commit.append(version_file_path)
                except Exception as e:
                    console.print(f"  [yellow]⚠[/] Could not update {relative_path}: {e}")

        # Update lock file if enabled
        if config.version.update_lock_file:
            from release_py.project.lockfile import (
                detect_package_manager,
                get_lock_file_path,
                should_update_lock_file,
                update_lock_file,
            )

            if should_update_lock_file(project_path):
                pkg_manager = detect_package_manager(project_path)
                success, message = update_lock_file(project_path, pkg_manager)
                if success:
                    console.print(f"  [green]✓[/] {message}")
                    lock_file = get_lock_file_path(project_path, pkg_manager)
                    if lock_file and lock_file.exists():
                        files_to_commit.append(lock_file)
                else:
                    console.print(f"  [yellow]⚠[/] {message}")

        # Generate changelog with GitHub integration for PR links and @usernames
        github_repo_str = f"{github_owner}/{github_repo}"
        changelog_content = generate_changelog(
            repo=repo, version=next_version, config=config, github_repo=github_repo_str
        )
        changelog_path = project_path / config.effective_changelog_path

        if changelog_path.exists():
            existing = changelog_path.read_text()
            new_content = changelog_content + "\n" + existing
        else:
            new_content = changelog_content

        changelog_path.write_text(new_content)
        console.print(f"  [green]✓[/] Updated {config.effective_changelog_path}")
        files_to_commit.append(changelog_path)

        # Commit changes
        commit_message = f"chore(release): prepare v{next_version}"
        repo.commit(commit_message, files_to_commit)
        console.print("  [green]✓[/] Committed changes")

        # Push branch
        repo.push(branch=config.github.release_pr_branch, force=True, set_upstream=True)
        console.print("  [green]✓[/] Pushed to origin")

        # Create/update PR via GitHub API
        from release_py.forge.github import GitHubClient

        github = GitHubClient(owner=github_owner, repo=github_repo)

        import asyncio

        async def create_or_update_pr() -> str:
            existing_pr = await github.find_pull_request(
                head=config.github.release_pr_branch,
                base=config.default_branch,
            )

            if existing_pr:
                updated = await github.update_pull_request(
                    number=existing_pr.number,
                    title=pr_title,
                    body=pr_body,
                )
                return f"Updated PR #{updated.number}: {updated.url}"
            new_pr = await github.create_pull_request(
                title=pr_title,
                body=pr_body,
                head=config.github.release_pr_branch,
                base=config.default_branch,
                labels=config.github.release_pr_labels,
            )
            return f"Created PR #{new_pr.number}: {new_pr.url}"

        result = asyncio.run(create_or_update_pr())
        console.print(f"  [green]✓[/] {result}")

        # Switch back to default branch
        repo.checkout(config.default_branch)

        if is_first_release:
            version_info = f"🎉 First release: [green]{next_version}[/]"
        else:
            version_info = f"Version: [cyan]{current_version}[/] → [green]{next_version}[/]"

        console.print(
            Panel(
                f"[green]Release PR created successfully![/]\n\n"
                f"{version_info}\n\n"
                "Merge the PR to trigger the release.",
                title="[green]Success[/]",
                border_style="green",
            )
        )

    except Exception as e:
        err_console.print(f"[red]Error creating release PR:[/] {e}")
        # Try to checkout back to default branch
        with contextlib.suppress(Exception):
            repo.checkout(config.default_branch)
        raise SystemExit(1) from e


# Pattern to extract PR number from commit description (e.g., "add feature (#123)")
_PR_NUMBER_PATTERN = re.compile(r"\(#(\d+)\)\s*$")


def _extract_pr_number(description: str) -> tuple[str, int | None]:
    """Extract PR number from commit description if present.

    GitHub squash merge commits typically append "(#123)" to the description.

    Args:
        description: The commit description

    Returns:
        Tuple of (cleaned description, PR number or None)

    Examples:
        >>> _extract_pr_number("add new feature (#123)")
        ('add new feature', 123)
        >>> _extract_pr_number("add new feature")
        ('add new feature', None)
    """
    match = _PR_NUMBER_PATTERN.search(description)
    if match:
        pr_number = int(match.group(1))
        cleaned = _PR_NUMBER_PATTERN.sub("", description).strip()
        return cleaned, pr_number
    return description, None


def _format_commit_entry(
    pc: Any,
    github_url: str | None = None,
    include_type_emoji: bool = False,
) -> str:
    """Format a single commit entry in FastAPI-style format.

    Args:
        pc: ParsedCommit instance
        github_url: Base GitHub URL (e.g., "https://github.com/owner/repo")
        include_type_emoji: Whether to prefix with type emoji (for flat lists)

    Returns:
        Formatted commit entry string

    Example output (FastAPI style):
        ✨ add new feature. PR #123 by @author.
        🐛 **api:** fix null response. PR #456 by @contributor.
    """
    # Type emoji mapping
    type_emojis = {
        "feat": "✨",
        "fix": "🐛",
        "perf": "⚡",
        "docs": "📚",
        "refactor": "♻️",
        "test": "🧪",
        "build": "📦",
        "ci": "👷",
        "style": "💄",
        "chore": "🔨",
    }

    parts = []

    # Add type emoji if requested
    if include_type_emoji:
        emoji = type_emojis.get(pc.commit_type or "", "📝")
        parts.append(f"{emoji} ")

    # Add scope if present
    if pc.scope:
        parts.append(f"**{pc.scope}:** ")

    # Extract PR number from description
    description, pr_number = _extract_pr_number(pc.description)
    parts.append(description)

    # Add PR link and author (FastAPI style)
    author = pc.commit.author_name
    if pr_number and github_url:
        pr_url = f"{github_url}/pull/{pr_number}"
        parts.append(f". PR [#{pr_number}]({pr_url}) by @{author}.")
    elif pr_number:
        parts.append(f". PR #{pr_number} by @{author}.")
    else:
        # No PR number - just add commit link and author
        short_sha = pc.commit.short_sha
        if github_url:
            commit_url = f"{github_url}/commit/{pc.commit.sha}"
            parts.append(f". Commit [{short_sha}]({commit_url}) by @{author}.")
        else:
            parts.append(f". Commit {short_sha} by @{author}.")

    return "".join(parts)


def _generate_pr_body(
    project_name: str,
    current_version: Version,
    next_version: Version,
    parsed_commits: list[Any],
    is_first_release: bool = False,
    github_url: str | None = None,
) -> str:
    """Generate the pull request body with changelog preview.

    Creates a professional, well-formatted PR body with:
    - Version bump summary
    - Changelog preview grouped by type
    - Breaking changes highlighted
    - Links to PRs and commits (when github_url is provided)

    Args:
        project_name: Name of the project
        current_version: Current version
        next_version: Next version
        parsed_commits: List of ParsedCommit instances
        is_first_release: Whether this is the first release
        github_url: Base GitHub URL for links (e.g., "https://github.com/owner/repo")
    """
    from release_py.core.commits import ParsedCommit

    if is_first_release:
        lines = [
            "## Summary",
            "",
            f"🎉 **First release** of **{project_name}** `v{next_version}`",
            "",
            f"**Initial version:** `{next_version}`",
            "",
            "---",
            "",
            "## Changelog",
            "",
        ]
    else:
        lines = [
            "## Summary",
            "",
            f"Preparing release of **{project_name}** `v{next_version}`",
            "",
            f"**Current version:** `{current_version}`",
            f"**Next version:** `{next_version}`",
            "",
            "---",
            "",
            "## Changelog",
            "",
        ]

    # Group commits by type
    by_type: dict[str, list[ParsedCommit]] = {}
    breaking: list[ParsedCommit] = []

    for pc in parsed_commits:
        if pc.is_breaking:
            breaking.append(pc)
        commit_type = pc.commit_type or "other"
        by_type.setdefault(commit_type, []).append(pc)

    # Type labels with emojis for professional look
    type_labels = {
        "feat": "✨ Features",
        "fix": "🐛 Bug Fixes",
        "perf": "⚡ Performance",
        "docs": "📚 Documentation",
        "refactor": "♻️ Refactoring",
        "test": "🧪 Tests",
        "build": "📦 Build",
        "ci": "🔧 CI/CD",
        "style": "💄 Style",
        "chore": "🔨 Chores",
        "other": "📝 Other",
    }

    # Breaking changes first
    if breaking:
        lines.append("### ⚠️ Breaking Changes")
        lines.append("")
        for pc in breaking:
            entry = _format_commit_entry(pc, github_url)
            lines.append(f"- {entry}")
        lines.append("")

    # Other changes by type
    for commit_type, label in type_labels.items():
        commits_of_type = by_type.get(commit_type, [])
        # Filter out breaking (already listed)
        commits_of_type = [c for c in commits_of_type if not c.is_breaking]

        if commits_of_type:
            lines.append(f"### {label}")
            lines.append("")
            for pc in commits_of_type:
                entry = _format_commit_entry(pc, github_url)
                lines.append(f"- {entry}")
            lines.append("")

    lines.extend(
        [
            "---",
            "",
            "_This PR was automatically created by [releasio](https://github.com/mikeleppane/release-py)_",
        ]
    )

    return "\n".join(lines)
