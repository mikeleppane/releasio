"""Implementation of the 'release' command.

The release command creates a git tag, publishes to PyPI,
and creates a GitHub release.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from rich.panel import Panel

from release_py.config import load_config
from release_py.core.version import Version
from release_py.vcs import GitRepository

if TYPE_CHECKING:
    from rich.console import Console


def run_release(
    path: str | None,
    dry_run: bool,
    skip_publish: bool,
    console: Console,
    err_console: Console,
) -> None:
    """Run the release command.

    Args:
        path: Optional path to project directory
        dry_run: Whether to just preview without releasing
        skip_publish: Whether to skip PyPI publishing
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

    # Check for clean working directory
    if not config.allow_dirty and repo.is_dirty():
        err_console.print(
            "[red]Error:[/] Repository has uncommitted changes.\nCommit or stash them first."
        )
        raise SystemExit(1)

    # Verify we're on the default branch
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

    # Create tag name
    tag_name = current_version.with_tag_prefix(config.effective_tag_prefix)

    # Check if tag already exists
    if repo.tag_exists(tag_name):
        err_console.print(
            f"[red]Error:[/] Tag [cyan]{tag_name}[/] already exists.\n"
            "This version may have already been released."
        )
        raise SystemExit(1)

    if dry_run:
        console.print()
        console.print(
            Panel(
                f"[bold]Package:[/] {project_name}\n"
                f"[bold]Version:[/] {current_version}\n"
                f"[bold]Tag:[/] {tag_name}\n"
                f"[bold]Publish:[/] {'No (--skip-publish)' if skip_publish else 'Yes (PyPI)'}",
                title="[yellow]Release Preview (Dry Run)[/]",
                border_style="yellow",
            )
        )
        console.print()
        console.print("[bold]Actions that would be performed:[/]")
        console.print(f"  1. Create and push git tag [cyan]{tag_name}[/]")
        if not skip_publish:
            console.print("  2. Build package with uv")
            console.print("  3. Publish to PyPI")
        console.print(f"  4. Create GitHub release for [cyan]{tag_name}[/]")
        console.print("\n[dim]Run without [cyan]--dry-run[/] to perform the release.[/]")
        return

    # Actually perform the release
    console.print()
    console.print(f"[bold]Releasing {project_name} v{current_version}...[/]\n")

    try:
        # Step 1: Create and push tag
        console.print(f"  • Creating tag [cyan]{tag_name}[/]...")
        repo.create_tag(tag_name, message=f"Release {tag_name}")
        repo.push_tag(tag_name)
        console.print(f"  [green]✓[/] Created and pushed tag {tag_name}")

        # Step 2: Build package (unless skipping publish)
        if not skip_publish and config.publish.enabled:
            custom_build = config.hooks.build
            if custom_build:
                console.print(f"  • Building package (custom: [dim]{custom_build}[/])...")
            else:
                console.print("  • Building package...")

            from release_py.publish.pypi import build_package

            build_package(
                project_path,
                custom_command=custom_build,
                version=str(current_version),
            )
            console.print("  [green]✓[/] Built package")

            # Step 3: Publish to PyPI
            console.print("  • Publishing to PyPI...")
            from release_py.publish.pypi import publish_package

            publish_package(project_path, config.publish)
            console.print("  [green]✓[/] Published to PyPI")

        # Step 4: Create GitHub release
        console.print("  • Creating GitHub release...")
        owner, repo_name = repo.parse_github_remote()
        github_owner = config.github.owner or owner
        github_repo = config.github.repo or repo_name

        from release_py.forge.github import GitHubClient

        github = GitHubClient(owner=github_owner, repo=github_repo)

        # Get the previous tag to determine changelog range
        tag_pattern = f"{config.effective_tag_prefix}*"
        previous_tag = repo.get_latest_tag(tag_pattern)

        # Generate changelog content and get contributors
        changelog_content = None
        contributors: list[str] = []
        github_usernames: list[str] = []

        if config.changelog.use_github_prs:
            # PR-based changelog (recommended for large open source projects)
            console.print("  • Fetching PRs from GitHub...")
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
                console.print("  [green]✓[/] Fetched PR-based changelog")
            except Exception as e:
                console.print(f"  [yellow]⚠[/] Could not fetch PRs: {e}")
        else:
            # Commit-based changelog via git-cliff (default)
            try:
                from release_py.core.changelog import generate_changelog

                # Pass GitHub repo for richer changelog with PR links and @usernames
                github_repo_str = f"{github_owner}/{github_repo}"
                changelog_content = generate_changelog(
                    repo,
                    current_version,
                    config,
                    github_repo=github_repo_str,
                )
            except Exception:
                pass  # No changelog content available

            # Get contributors from commits
            contributors = repo.get_contributors_since_tag(previous_tag)
            github_usernames = repo.get_contributor_github_usernames(previous_tag)

        # Generate release notes
        release_body = _generate_release_body(
            project_name,
            current_version,
            changelog_content=changelog_content,
            contributors=contributors,
            github_usernames=github_usernames,
        )

        async def create_release() -> str:
            release = await github.create_release(
                tag=tag_name,
                name=f"{project_name} v{current_version}",
                body=release_body,
                draft=config.github.draft_releases,
                prerelease=current_version.is_prerelease,
            )
            return release.url

        release_url = asyncio.run(create_release())
        console.print("  [green]✓[/] Created GitHub release")

        # Success!
        console.print()
        console.print(
            Panel(
                f"[bold green]🎉 Successfully released {project_name} v{current_version}![/]\n\n"
                f"[bold]GitHub Release:[/] {release_url}\n"
                + (
                    f"[bold]PyPI:[/] https://pypi.org/project/{project_name}/{current_version}/\n"
                    if not skip_publish and config.publish.enabled
                    else ""
                )
                + "\n"
                "Thank you for using releasio! ⭐",
                title="[bold green]Release Complete[/]",
                border_style="green",
            )
        )

    except Exception as e:
        err_console.print(f"[red]Error during release:[/] {e}")
        err_console.print(
            "\n[yellow]Note:[/] Some steps may have completed. "
            "Check your repository and PyPI for partial release."
        )
        raise SystemExit(1) from e


def _generate_release_body(
    project_name: str,
    version: Version,
    changelog_content: str | None = None,
    contributors: list[str] | None = None,
    github_usernames: list[str] | None = None,
) -> str:
    """Generate a professional GitHub release body.

    Follows the patterns used by major projects like FastAPI and Ruff:
    - Actual changelog content (categorized changes)
    - Contributors section with GitHub usernames
    - Installation instructions

    Args:
        project_name: Name of the project
        version: Version being released
        changelog_content: Generated changelog content (from git-cliff or fallback)
        contributors: List of contributor names
        github_usernames: List of GitHub usernames (linked in the release)

    Returns:
        Formatted release body markdown
    """
    lines: list[str] = []

    # Add changelog content if available
    if changelog_content:
        # Remove the version header if git-cliff added one (we'll use GitHub's title)
        content = changelog_content.strip()
        # Remove leading "## [version]" or "# [version]" lines
        import re

        content = re.sub(r"^#+\s*\[?v?\d+\.\d+\.\d+.*?\]?.*?\n+", "", content, flags=re.MULTILINE)
        if content:
            lines.append(content)
            lines.append("")

    # Add contributors section (Ruff-style)
    if github_usernames:
        lines.append("## Contributors")
        lines.append("")
        # Format as linked usernames
        username_links = [f"[@{u}](https://github.com/{u})" for u in github_usernames]
        lines.append(" • ".join(username_links))
        lines.append("")
    elif contributors:
        # Fallback to names if no GitHub usernames available
        lines.append("## Contributors")
        lines.append("")
        lines.append(", ".join(contributors))
        lines.append("")

    # Add installation section
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

    # Footer
    lines.append("---")
    lines.append("")
    lines.append("_Released with [releasio](https://github.com/mikeleppane/release-py)_")

    return "\n".join(lines)
