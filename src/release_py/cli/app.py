"""Main Typer application for releasio CLI."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from release_py import __version__

# Create the main Typer app
app = typer.Typer(
    name="releasio",
    help="Best-in-class Python release automation, inspired by release-plz.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)

# Console for rich output
console = Console()
err_console = Console(stderr=True)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"[bold blue]releasio[/] version [green]{__version__}[/]")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """releasio: Automated releases for Python projects.

    [bold]Commands:[/]

    • [cyan]check[/]      Preview what would happen (dry-run)
    • [cyan]check-pr[/]   Validate PR title follows conventional commit format
    • [cyan]update[/]     Update version and changelog locally
    • [cyan]release-pr[/] Create or update a release pull request
    • [cyan]release[/]    Tag, publish to PyPI, and create GitHub release
    • [cyan]init[/]       Initialize releasio configuration

    [bold]Quick Start:[/]

    1. Add conventional commits to your repository
    2. Run [cyan]releasio release-pr[/] to create a release PR
    3. Merge the PR to trigger the release

    [bold]Documentation:[/] https://github.com/mikeleppane/release-py
    """


@app.command()
def check(
    path: Annotated[
        str | None,
        typer.Argument(
            help="Path to the project directory.",
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Show detailed output.",
        ),
    ] = False,
) -> None:
    """Preview what would happen without making changes.

    This command analyzes your repository and shows:

    • Current version and calculated next version
    • Commits that would be included in the release
    • Changelog preview
    • Files that would be modified

    [bold]Example:[/]

        $ releasio check
        $ releasio check --verbose
    """
    from release_py.cli.commands.check import run_check

    run_check(path=path, verbose=verbose, console=console, err_console=err_console)


@app.command()
def update(
    path: Annotated[
        str | None,
        typer.Argument(
            help="Path to the project directory.",
        ),
    ] = None,
    execute: Annotated[
        bool,
        typer.Option(
            "--execute",
            "-x",
            help="Actually apply the changes (default is dry-run).",
        ),
    ] = False,
    version_override: Annotated[
        str | None,
        typer.Option(
            "--version",
            "-v",
            help="Override calculated version (e.g., '2.0.0').",
        ),
    ] = None,
    prerelease: Annotated[
        str | None,
        typer.Option(
            "--prerelease",
            "--pre",
            help="Create a pre-release version (e.g., 'alpha', 'beta', 'rc').",
        ),
    ] = None,
) -> None:
    """Update version and changelog locally.

    By default, this runs in dry-run mode showing what would change.
    Use [cyan]--execute[/] to apply the changes.

    [bold]Changes made:[/]

    • Updates version in pyproject.toml
    • Generates/updates CHANGELOG.md via git-cliff
    • Updates any additional version files configured

    [bold]Version Override:[/]

    Use [cyan]--version[/] to set a specific version instead of calculating
    from commits. Useful for major version bumps or first releases.

    [bold]Pre-release Versions:[/]

    Use [cyan]--prerelease[/] to create alpha, beta, or rc versions:
    • --prerelease alpha → 1.2.0a1
    • --prerelease beta  → 1.2.0b1
    • --prerelease rc    → 1.2.0rc1

    [bold]Example:[/]

        $ releasio update                    # Preview changes
        $ releasio update --execute          # Apply changes
        $ releasio update --version 2.0.0    # Force version
        $ releasio update --prerelease alpha # Create alpha release
    """
    from release_py.cli.commands.update import run_update

    run_update(
        path=path,
        execute=execute,
        version_override=version_override,
        prerelease=prerelease,
        console=console,
        err_console=err_console,
    )


@app.command("release-pr")
def release_pr(
    path: Annotated[
        str | None,
        typer.Argument(
            help="Path to the project directory.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Preview without creating/updating the PR.",
        ),
    ] = False,
) -> None:
    """Create or update a release pull request.

    This command:

    1. Calculates the next version from conventional commits
    2. Generates changelog via git-cliff
    3. Creates a branch with version bump and changelog
    4. Creates or updates a pull request

    When the PR is merged, use [cyan]releasio release[/] to publish.

    [bold]Example:[/]

        $ releasio release-pr
        $ releasio release-pr --dry-run
    """
    from release_py.cli.commands.release_pr import run_release_pr

    run_release_pr(
        path=path,
        dry_run=dry_run,
        console=console,
        err_console=err_console,
    )


@app.command()
def release(
    path: Annotated[
        str | None,
        typer.Argument(
            help="Path to the project directory.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Preview without releasing.",
        ),
    ] = False,
    skip_publish: Annotated[
        bool,
        typer.Option(
            "--skip-publish",
            help="Skip publishing to PyPI.",
        ),
    ] = False,
) -> None:
    """Perform the release: tag, publish, and create GitHub release.

    This command:

    1. Creates a git tag for the current version
    2. Builds the package with uv/hatch
    3. Publishes to PyPI (unless --skip-publish)
    4. Creates a GitHub release with changelog

    [bold]Prerequisites:[/]

    • Version must be updated (via release-pr or update)
    • Repository must be clean
    • Must be on the default branch

    [bold]Example:[/]

        $ releasio release
        $ releasio release --dry-run
        $ releasio release --skip-publish
    """
    from release_py.cli.commands.release import run_release

    run_release(
        path=path,
        dry_run=dry_run,
        skip_publish=skip_publish,
        console=console,
        err_console=err_console,
    )


@app.command("init")
def init_config(
    path: Annotated[
        str | None,
        typer.Argument(
            help="Path to the project directory.",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Overwrite existing configuration.",
        ),
    ] = False,
) -> None:
    """Initialize releasio configuration.

    This command:

    1. Adds [tool.releasio] section to pyproject.toml
    2. Creates a git-cliff configuration
    3. Optionally creates GitHub Actions workflow

    [bold]Example:[/]

        $ releasio init
        $ releasio init --force  # Overwrite existing config
    """
    from release_py.cli.commands.init_cmd import run_init

    run_init(
        path=path,
        force=force,
        console=console,
        err_console=err_console,
    )


@app.command("check-pr")
def check_pr(
    title: Annotated[
        str | None,
        typer.Option(
            "--title",
            "-t",
            help="PR title to validate (auto-detected in GitHub Actions).",
        ),
    ] = None,
    path: Annotated[
        str | None,
        typer.Argument(
            help="Path to the project directory.",
        ),
    ] = None,
    require_scope: Annotated[
        bool,
        typer.Option(
            "--require-scope",
            help="Require a scope in the PR title.",
        ),
    ] = False,
) -> None:
    """Validate PR title follows conventional commit format.

    This command validates that a PR title follows the conventional
    commit format, making it suitable for CI pipelines.

    [bold]In GitHub Actions:[/]

    The PR title is automatically detected from the event context.

    [bold]Conventional Commit Format:[/]

        <type>[(scope)][!]: <description>

    [bold]Examples:[/]

        feat: add user authentication
        fix(api): handle null responses
        feat!: redesign config format

    [bold]Usage:[/]

        $ releasio check-pr --title "feat: add feature"
        $ releasio check-pr  # Auto-detect in GitHub Actions
    """
    from release_py.cli.commands.check_pr import run_check_pr

    run_check_pr(
        title=title,
        path=path,
        require_scope=require_scope,
        console=console,
        err_console=err_console,
    )


if __name__ == "__main__":
    app()
