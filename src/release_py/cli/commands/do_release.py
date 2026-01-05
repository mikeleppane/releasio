"""Implementation of the 'do-release' command.

The do-release command combines update + commit + release into one atomic workflow.
It updates version files, commits the changes, creates a tag, publishes to PyPI,
and creates a GitHub release.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from rich.panel import Panel

from release_py.config import load_config
from release_py.core.commits import calculate_bump, filter_skip_release_commits, parse_commits
from release_py.core.version import BumpType, Version
from release_py.vcs import GitRepository

if TYPE_CHECKING:
    from rich.console import Console

    from release_py.config.models import ReleasePyConfig


def run_do_release(
    path: str | None,
    execute: bool,
    skip_publish: bool,
    version_override: str | None,
    prerelease: str | None,
    console: Console,
    err_console: Console,
) -> None:
    """Run the complete release workflow: update + commit + release.

    Args:
        path: Optional path to project directory
        execute: Whether to actually apply changes (default is dry-run)
        skip_publish: Whether to skip PyPI publishing
        version_override: Manual version override (e.g., "2.0.0")
        prerelease: Pre-release identifier (e.g., "alpha", "beta", "rc")
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

    # Must be clean (no uncommitted changes)
    if repo.is_dirty():
        err_console.print(
            "[red]Error:[/] Repository has uncommitted changes.\nCommit or stash them first."
        )
        raise SystemExit(1)

    # Must be on default branch
    current_branch = repo.get_current_branch()
    if current_branch != config.default_branch:
        err_console.print(
            f"[red]Error:[/] Must be on [cyan]{config.default_branch}[/] branch "
            f"(currently on [yellow]{current_branch}[/])."
        )
        raise SystemExit(1)

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
    tag_pattern = f"{config.version.tag_prefix}*"
    latest_tag = repo.get_latest_tag(tag_pattern)

    # Detect first release (no existing tags)
    is_first_release = latest_tag is None

    # Get commits since last tag
    commits = repo.get_commits_since_tag(latest_tag)

    if not commits:
        console.print("[yellow]No commits found since last release. Nothing to do.[/]")
        return

    # Filter out commits with skip release markers
    commits = filter_skip_release_commits(commits, config.commits.skip_release_patterns)

    if not commits:
        console.print("[yellow]All commits have skip release markers. Nothing to do.[/]")
        return

    # Parse commits and calculate bump
    parsed = parse_commits(commits, config.commits)
    bump_type = calculate_bump(parsed, config.commits)

    # Handle manual version override
    if version_override:
        try:
            next_version = Version.parse(version_override)
        except Exception as e:
            err_console.print(f"[red]Invalid version format:[/] {e}")
            raise SystemExit(1) from e
    elif is_first_release:
        next_version = Version.parse(config.version.initial_version)
    else:
        if bump_type == BumpType.NONE:
            console.print(
                "[yellow]No releasable changes found (only non-release commit types).[/]\n"
                "[dim]Use [cyan]--version[/] to force a specific version.[/]"
            )
            return
        next_version = current_version.bump(bump_type)

    # Apply pre-release identifier if specified
    effective_prerelease = prerelease or config.get_effective_prerelease(current_branch)
    if effective_prerelease:
        next_version = next_version.with_prerelease(effective_prerelease)
        branch_config = config.get_branch_config(current_branch)
        if branch_config and branch_config.prerelease:
            console.print(
                f"[dim]Auto-detected pre-release channel [cyan]{effective_prerelease}[/] "
                f"from branch [cyan]{current_branch}[/][/]"
            )

    # Create tag name
    tag_name = next_version.with_tag_prefix(config.version.tag_prefix)

    # Check if tag already exists
    if repo.tag_exists(tag_name):
        err_console.print(
            f"[red]Error:[/] Tag [cyan]{tag_name}[/] already exists.\n"
            "This version may have already been released."
        )
        raise SystemExit(1)

    # Dry-run mode: show preview
    if not execute:
        _show_preview(
            console=console,
            project_name=project_name,
            current_version=current_version,
            next_version=next_version,
            tag_name=tag_name,
            is_first_release=is_first_release,
            skip_publish=skip_publish,
            config=config,
            commits_count=len(commits),
        )
        return

    # Execute the full release workflow
    console.print()
    if is_first_release:
        console.print(f"[bold]🎉 First release of {project_name} v{next_version}![/]\n")
    else:
        console.print(
            f"[bold]Releasing {project_name}: "
            f"[cyan]{current_version}[/] → [green]{next_version}[/][/]\n"
        )

    # Track modified files for commit
    files_to_commit: list[Path] = []

    # Phase 1: Update version files
    console.print("[bold]Phase 1: Updating version files[/]")
    files_to_commit = _perform_update(
        project_path=project_path,
        next_version=next_version,
        config=config,
        repo=repo,
        console=console,
        err_console=err_console,
    )

    # Phase 2: Commit changes
    console.print("\n[bold]Phase 2: Committing changes[/]")
    commit_message = f"chore(release): prepare v{next_version}"
    repo.commit(commit_message, files_to_commit)
    console.print(f"  [green]✓[/] Committed: {commit_message}")

    # Phase 3: Create and push tag
    console.print("\n[bold]Phase 3: Creating tag[/]")
    repo.create_tag(tag_name, message=f"Release {tag_name}")
    repo.push_tag(tag_name)
    console.print(f"  [green]✓[/] Created and pushed tag {tag_name}")

    # Phase 4: Build and publish
    if not skip_publish and config.publish.enabled:
        console.print("\n[bold]Phase 4: Publishing to PyPI[/]")
        _perform_publish(
            project_path=project_path,
            next_version=next_version,
            config=config,
            console=console,
            err_console=err_console,
        )
    elif skip_publish:
        console.print("\n[bold]Phase 4: Skipping publish (--skip-publish)[/]")

    # Phase 5: Create GitHub release
    console.print("\n[bold]Phase 5: Creating GitHub release[/]")
    release_url = _create_github_release(
        project_name=project_name,
        next_version=next_version,
        tag_name=tag_name,
        config=config,
        repo=repo,
        console=console,
        err_console=err_console,
    )

    # Success!
    console.print()
    console.print(
        Panel(
            f"[bold green]🎉 Successfully released {project_name} v{next_version}![/]\n\n"
            f"[bold]GitHub Release:[/] {release_url}\n"
            + (
                f"[bold]PyPI:[/] https://pypi.org/project/{project_name}/{next_version}/\n"
                if not skip_publish and config.publish.enabled
                else ""
            )
            + "\nThank you for using releasio! ⭐",
            title="[bold green]Release Complete[/]",
            border_style="green",
        )
    )


def _show_preview(
    console: Console,
    project_name: str,
    current_version: Version,
    next_version: Version,
    tag_name: str,
    is_first_release: bool,
    skip_publish: bool,
    config: ReleasePyConfig,
    commits_count: int,
) -> None:
    """Show dry-run preview of what would happen."""
    version_info = (
        f"🎉 First release: [green]{next_version}[/]"
        if is_first_release
        else f"[cyan]{current_version}[/] → [green]{next_version}[/]"
    )

    console.print()
    console.print(
        Panel(
            f"[bold]Package:[/] {project_name}\n"
            f"[bold]Version:[/] {version_info}\n"
            f"[bold]Tag:[/] {tag_name}\n"
            f"[bold]Commits:[/] {commits_count}\n"
            f"[bold]Publish:[/] {'No (--skip-publish)' if skip_publish else 'Yes (PyPI)'}",
            title="[yellow]Release Preview (Dry Run)[/]",
            border_style="yellow",
        )
    )
    console.print()
    console.print("[bold]Actions that would be performed:[/]")
    console.print("  1. Update version in [cyan]pyproject.toml[/]")
    console.print(f"  2. Generate changelog in [cyan]{config.changelog.path}[/]")
    console.print(f"  3. Commit: [cyan]chore(release): prepare v{next_version}[/]")
    console.print(f"  4. Create and push tag [cyan]{tag_name}[/]")
    if not skip_publish:
        console.print("  5. Build package with uv")
        console.print("  6. Publish to PyPI")
    console.print(f"  7. Create GitHub release for [cyan]{tag_name}[/]")
    console.print("\n[dim]Run with [cyan]--execute[/] to perform the release.[/]")


def _perform_update(
    project_path: Path,
    next_version: Version,
    config: ReleasePyConfig,
    repo: GitRepository,
    console: Console,
    err_console: Console,
) -> list[Path]:
    """Perform version and changelog updates. Returns list of modified files."""
    from release_py.project.pyproject import (
        detect_version_files,
        update_pyproject_version,
        update_version_file,
        update_version_in_plain_file,
    )

    files_modified: list[Path] = []

    # Update pyproject.toml
    try:
        update_pyproject_version(project_path, str(next_version))
        console.print("  [green]✓[/] Updated version in pyproject.toml")
        files_modified.append(project_path / "pyproject.toml")
    except Exception as e:
        err_console.print(f"[red]Error updating pyproject.toml:[/] {e}")
        raise SystemExit(1) from e

    # Update additional version files (explicitly configured)
    for version_file in config.version.version_files:
        version_file_path = project_path / version_file
        try:
            if version_file_path.name == "VERSION":
                update_version_in_plain_file(version_file_path, str(next_version))
            else:
                update_version_file(version_file_path, str(next_version))
            console.print(f"  [green]✓[/] Updated version in {version_file}")
            files_modified.append(version_file_path)
        except Exception as e:
            err_console.print(f"[red]Error updating {version_file}:[/] {e}")
            raise SystemExit(1) from e

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
                console.print(f"  [green]✓[/] Updated version in {relative_path} (auto-detected)")
                files_modified.append(version_file_path)
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
                    files_modified.append(lock_file)
            else:
                console.print(f"  [yellow]⚠[/] {message}")

    # Generate changelog
    try:
        from release_py.core.changelog import generate_changelog

        github_repo_str: str | None = None
        try:
            owner, repo_name = repo.parse_github_remote()
            github_owner = config.github.owner or owner
            github_repo = config.github.repo or repo_name
            github_repo_str = f"{github_owner}/{github_repo}"
        except Exception:
            pass

        changelog_content = generate_changelog(
            repo=repo,
            version=next_version,
            config=config,
            github_repo=github_repo_str,
        )

        changelog_path = project_path / config.changelog.path
        if changelog_path.exists():
            existing = changelog_path.read_text()
            new_content = changelog_content + "\n" + existing
        else:
            new_content = changelog_content

        changelog_path.write_text(new_content)
        console.print(f"  [green]✓[/] Updated {config.changelog.path}")
        files_modified.append(changelog_path)
    except Exception as e:
        err_console.print(f"[red]Error generating changelog:[/] {e}")
        raise SystemExit(1) from e

    return files_modified


def _perform_publish(
    project_path: Path,
    next_version: Version,
    config: ReleasePyConfig,
    console: Console,
    err_console: Console,
) -> None:
    """Build and publish package to PyPI."""
    from release_py.publish.pypi import build_package, publish_package

    # Build
    custom_build = config.hooks.build
    if custom_build:
        console.print(f"  • Building package (custom: [dim]{custom_build}[/])...")
    else:
        console.print(f"  • Building package with {config.publish.tool}...")

    try:
        build_package(
            project_path,
            custom_command=custom_build,
            version=str(next_version),
            tool=config.publish.tool,
        )
        console.print("  [green]✓[/] Built package")
    except Exception as e:
        err_console.print(f"[red]Error building package:[/] {e}")
        raise SystemExit(1) from e

    # Publish
    console.print("  • Publishing to PyPI...")
    try:
        publish_package(project_path, config.publish)
        console.print("  [green]✓[/] Published to PyPI")
    except Exception as e:
        err_console.print(f"[red]Error publishing to PyPI:[/] {e}")
        raise SystemExit(1) from e


def _create_github_release(
    project_name: str,
    next_version: Version,
    tag_name: str,
    config: ReleasePyConfig,
    repo: GitRepository,
    console: Console,
    err_console: Console,
) -> str:
    """Create GitHub release. Returns the release URL."""
    from release_py.forge.github import GitHubClient

    console.print("  • Creating GitHub release...")

    try:
        owner, repo_name = repo.parse_github_remote()
        github_owner = config.github.owner or owner
        github_repo = config.github.repo or repo_name
    except Exception as e:
        err_console.print(f"[red]Error parsing GitHub remote:[/] {e}")
        raise SystemExit(1) from e

    github = GitHubClient(owner=github_owner, repo=github_repo)

    # Get previous tag for changelog range
    tag_pattern = f"{config.version.tag_prefix}*"
    previous_tag = repo.get_latest_tag(tag_pattern)

    # Generate changelog content for release body
    changelog_content: str | None = None
    contributors: list[str] = []
    github_usernames: list[str] = []

    if config.changelog.use_github_prs:
        try:
            ignore_authors = config.changelog.ignore_authors

            async def fetch_pr_changelog() -> tuple[str, list[str]]:
                pr_changelog = await github.generate_pr_based_changelog(
                    previous_tag, ignore_authors=ignore_authors
                )
                prs = await github.get_merged_prs_between_tags(previous_tag)
                pr_contributors = await github.get_contributors_from_prs(
                    prs, ignore_authors=ignore_authors
                )
                return pr_changelog, pr_contributors

            changelog_content, github_usernames = asyncio.run(fetch_pr_changelog())
        except Exception as e:
            console.print(f"  [yellow]⚠[/] Could not fetch PRs: {e}")
    else:
        try:
            from release_py.core.changelog import generate_changelog

            github_repo_str = f"{github_owner}/{github_repo}"
            changelog_content = generate_changelog(
                repo,
                next_version,
                config,
                github_repo=github_repo_str,
            )
        except Exception as e:
            console.print(
                f"  [yellow]⚠[/] Could not generate changelog: {e}\n"
                "    GitHub release will be created without changelog content."
            )

        contributors = repo.get_contributors_since_tag(previous_tag)
        github_usernames = repo.get_contributor_github_usernames(previous_tag)

    # Generate release body
    release_body = _generate_release_body(
        project_name,
        next_version,
        changelog_content=changelog_content,
        contributors=contributors,
        github_usernames=github_usernames,
    )

    async def create_release() -> str:
        release = await github.create_release(
            tag=tag_name,
            name=f"{project_name} v{next_version}",
            body=release_body,
            draft=config.github.draft_releases,
            prerelease=next_version.is_prerelease,
        )
        return release.url

    try:
        release_url = asyncio.run(create_release())
    except Exception as e:
        err_console.print(f"[red]Error creating GitHub release:[/] {e}")
        raise SystemExit(1) from e
    else:
        console.print("  [green]✓[/] Created GitHub release")
        return release_url


def _generate_release_body(
    project_name: str,
    version: Version,
    changelog_content: str | None = None,
    contributors: list[str] | None = None,
    github_usernames: list[str] | None = None,
) -> str:
    """Generate GitHub release body."""
    import re

    lines: list[str] = []

    if changelog_content:
        content = changelog_content.strip()
        content = re.sub(r"^#+\s*\[?v?\d+\.\d+\.\d+.*?\]?.*?\n+", "", content, flags=re.MULTILINE)
        if content:
            lines.append(content)
            lines.append("")

    if github_usernames:
        lines.append("## Contributors")
        lines.append("")
        username_links = [f"[@{u}](https://github.com/{u})" for u in github_usernames]
        lines.append(" • ".join(username_links))
        lines.append("")
    elif contributors:
        lines.append("## Contributors")
        lines.append("")
        lines.append(", ".join(contributors))
        lines.append("")

    lines.append("## Installation")
    lines.append("")
    lines.append("```bash")
    lines.append(f"pip install {project_name}=={version}")
    lines.append("```")
    lines.append("")
    lines.append("Or with uv:")
    lines.append("")
    lines.append("```bash")
    lines.append(f"uv add {project_name}=={version}")
    lines.append("```")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_Released with [releasio](https://github.com/mikeleppane/release-py)_")

    return "\n".join(lines)
