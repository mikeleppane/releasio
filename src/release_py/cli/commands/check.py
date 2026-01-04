"""Implementation of the 'check' command.

The check command performs a dry-run analysis of what would happen
during a release, without making any changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table

from release_py.config import load_config
from release_py.core.commits import calculate_bump, filter_skip_release_commits, parse_commits
from release_py.core.version import BumpType, Version
from release_py.vcs import GitRepository

if TYPE_CHECKING:
    from rich.console import Console


def run_check(
    path: str | None,
    verbose: bool,
    console: Console,
    err_console: Console,
) -> None:
    """Run the check command.

    Args:
        path: Optional path to project directory
        verbose: Whether to show detailed output
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
    from release_py.config.loader import get_project_version

    try:
        current_version_str = get_project_version(project_path)
        current_version = Version.parse(current_version_str)
    except Exception as e:
        err_console.print(f"[red]Error getting version:[/] {e}")
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
        # Prevent empty releases (no meaningful changes)
        if bump_type == BumpType.NONE:
            console.print(
                Panel(
                    "[yellow]No releasable changes found.[/]\n\n"
                    "Only non-release commit types (docs, chore, etc.) since last release.\n"
                    "Use [cyan]releasio update --version X.Y.Z[/] to force a specific version.",
                    title="No Changes",
                    border_style="yellow",
                )
            )
            return

        next_version = current_version.bump(bump_type)

    # Display results
    console.print()

    if is_first_release:
        panel_content = (
            f"[bold yellow]🎉 First Release![/]\n\n"
            f"[bold]Initial version:[/] [green]{next_version}[/]\n"
            f"[bold]Commits:[/]         {len(commits)}"
        )
        panel_title = "[bold blue]First Release Preview[/]"
    else:
        panel_content = (
            f"[bold]Current version:[/] [cyan]{current_version}[/]\n"
            f"[bold]Next version:[/]    [green]{next_version}[/]\n"
            f"[bold]Bump type:[/]       [magenta]{bump_type}[/]\n"
            f"[bold]Commits:[/]         {len(commits)}"
        )
        panel_title = "[bold blue]Release Preview[/]"

    console.print(
        Panel(
            panel_content,
            title=panel_title,
            border_style="blue",
        )
    )

    if verbose:
        # Show commit table
        console.print()
        table = Table(title="Commits to Include", show_header=True)
        table.add_column("SHA", style="dim", width=8)
        table.add_column("Type", style="cyan", width=10)
        table.add_column("Scope", style="magenta", width=12)
        table.add_column("Description")
        table.add_column("Breaking", style="red", width=8)

        for pc in parsed:
            table.add_row(
                pc.commit.short_sha,
                pc.commit_type or "-",
                pc.scope or "-",
                pc.description,
                "Yes" if pc.is_breaking else "",
            )

        console.print(table)

    # Show what would change
    console.print()
    console.print("[bold]Files that would be modified:[/]")
    console.print(f"  • [cyan]pyproject.toml[/] (version: {current_version} → {next_version})")
    console.print(f"  • [cyan]{config.effective_changelog_path}[/] (changelog entry)")

    if config.version.version_files:
        for vf in config.version.version_files:
            console.print(f"  • [cyan]{vf}[/] (version update)")

    console.print()
    console.print("[dim]Run [cyan]releasio update --execute[/] to apply these changes.[/]")
