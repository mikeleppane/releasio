"""Implementation of the 'init' command.

The init command sets up releasio configuration in a project.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.prompt import Confirm, Prompt

if TYPE_CHECKING:
    from rich.console import Console


def _detect_squash_merge(project_path: Path) -> bool:
    """Detect if the project likely uses squash merging.

    Looks at recent commit messages for patterns like "(#123)" which
    indicate squash-merged PRs.

    Args:
        project_path: Path to the project directory.

    Returns:
        True if squash merging is likely used.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(project_path), "log", "--oneline", "-20"],
            capture_output=True,
            text=True,
            check=True,
        )
        commits = result.stdout.strip()

        # Count commits with "(#123)" pattern (squash merge signature)
        squash_pattern = re.compile(r"\(#\d+\)")
        squash_count = len(squash_pattern.findall(commits))

        # If more than 30% of recent commits have PR numbers, likely squash merge
        total_commits = len(commits.split("\n")) if commits else 0
        if total_commits > 0 and squash_count / total_commits > 0.3:
            return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return False


def run_init(
    path: str | None,
    force: bool,
    console: Console,
    err_console: Console,
) -> None:
    """Run the init command.

    Args:
        path: Optional path to project directory
        force: Whether to overwrite existing configuration
        console: Console for standard output
        err_console: Console for error output
    """
    project_path = Path(path) if path else Path.cwd()
    pyproject_path = project_path / "pyproject.toml"

    console.print()
    console.print(
        Panel(
            "[bold]Welcome to releasio![/]\n\n"
            "This wizard will help you set up automated releases for your project.",
            title="[blue]Setup Wizard[/]",
            border_style="blue",
        )
    )
    console.print()

    # Check if pyproject.toml exists
    if not pyproject_path.exists():
        err_console.print(
            "[red]Error:[/] No pyproject.toml found.\n"
            "Run this command from your project root, or use [cyan]uv init[/] first."
        )
        raise SystemExit(1)

    # Check if already configured
    import tomllib

    with pyproject_path.open("rb") as f:
        pyproject_data = tomllib.load(f)

    tool_config = pyproject_data.get("tool", {}).get("releasio")

    if tool_config and not force:
        console.print(
            "[yellow]releasio is already configured in this project.[/]\n"
            "Use [cyan]--force[/] to overwrite the existing configuration."
        )
        return

    # Interactive configuration
    console.print("[bold]Configuration Options[/]\n")

    default_branch = Prompt.ask(
        "Default branch",
        default="main",
    )

    tag_prefix = Prompt.ask(
        "Tag prefix (e.g., 'v' for 'v1.0.0')",
        default="v",
    )

    # Detect if using squash merge workflow
    use_squash_merge = Confirm.ask(
        "Does your project use squash merging for PRs?",
        default=_detect_squash_merge(project_path),
    )

    if use_squash_merge:
        console.print("  [dim]Using PR-based changelog (better for squash merge workflows)[/]")

    # Ask about project type
    console.print()
    project_type = Prompt.ask(
        "Project type",
        choices=["small-team", "open-source", "enterprise"],
        default="small-team",
    )

    is_large_oss = project_type == "open-source"
    if is_large_oss:
        console.print("  [dim]Configuring for open source with contributor tracking[/]")

    console.print()
    create_workflow = Confirm.ask(
        "Create GitHub Actions workflow?",
        default=True,
    )

    add_pr_check = False
    if create_workflow:
        add_pr_check = Confirm.ask(
            "Add PR title validation workflow?",
            default=is_large_oss,
        )

    console.print()

    # Generate configuration
    changelog_section = ""
    if use_squash_merge:
        changelog_section = """
[tool.releasio.changelog]
# Use GitHub PR-based changelog (recommended for squash merge workflows)
use_github_prs = true
"""

    config_toml = f"""
[tool.releasio]
default_branch = "{default_branch}"
tag_prefix = "{tag_prefix}"
changelog_path = "CHANGELOG.md"

[tool.releasio.commits]
# Commit types that trigger a minor version bump
types_minor = ["feat"]
# Commit types that trigger a patch version bump
types_patch = ["fix", "perf", "docs", "refactor", "style", "test", "build", "ci"]
{changelog_section}
[tool.releasio.github]
release_pr_branch = "releasio/release"
release_pr_labels = ["release"]

[tool.releasio.publish]
enabled = true
tool = "uv"
"""

    # Git-cliff configuration
    cliff_config = '''
[tool.git-cliff.changelog]
header = """
# Changelog

All notable changes to this project will be documented in this file.

"""
body = """
{% if version %}\\
    ## [{{ version | trim_start_matches(pat="v") }}] - {{ timestamp | date(format="%Y-%m-%d") }}
{% else %}\\
    ## [Unreleased]
{% endif %}\\
{% for group, commits in commits | group_by(attribute="group") %}
    ### {{ group | striptags | trim | upper_first }}
    {% for commit in commits %}
        - {% if commit.scope %}*({{ commit.scope }})* {% endif %}\\
            {% if commit.breaking %}[**breaking**] {% endif %}\\
            {{ commit.message | upper_first }}\\
    {% endfor %}
{% endfor %}\\n
"""
trim = true

[tool.git-cliff.git]
conventional_commits = true
filter_unconventional = true
commit_parsers = [
    { message = "^feat", group = "✨ Features" },
    { message = "^fix", group = "🐛 Bug Fixes" },
    { message = "^doc", group = "📚 Documentation" },
    { message = "^perf", group = "⚡ Performance" },
    { message = "^refactor", group = "♻️ Refactoring" },
    { message = "^style", group = "💄 Style" },
    { message = "^test", group = "🧪 Testing" },
    { message = "^build", group = "📦 Build" },
    { message = "^ci", group = "🔧 CI" },
    { message = "^chore\\\\(release\\\\)", skip = true },
    { message = "^chore", group = "🔨 Chores" },
]
tag_pattern = "v[0-9].*"
'''

    # Append to pyproject.toml
    console.print("[bold]Writing configuration...[/]\n")

    with pyproject_path.open("a") as f:
        f.write("\n")
        f.write(config_toml.strip())
        f.write("\n")
        f.write(cliff_config.strip())
        f.write("\n")

    console.print(f"  [green]✓[/] Updated [cyan]{pyproject_path}[/]")

    # Create GitHub Actions workflow
    if create_workflow:
        workflows_dir = project_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)

        workflow_path = workflows_dir / "release.yml"
        workflow_content = f"""name: Release

on:
  push:
    branches: [{default_branch}]
  pull_request:
    types: [closed]
    branches: [{default_branch}]

permissions:
  contents: write
  pull-requests: write
  id-token: write  # For PyPI trusted publishing

jobs:
  # Create/update Release PR on every push to {default_branch}
  release-pr:
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history for changelog

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install uv
        uses: astral-sh/setup-uv@v5

      - name: Install releasio
        run: uv tool install releasio

      - name: Create Release PR
        env:
          GITHUB_TOKEN: ${{{{ secrets.GITHUB_TOKEN }}}}
        run: releasio release-pr

  # Perform release when Release PR is merged
  release:
    if: |
      github.event_name == 'pull_request' &&
      github.event.pull_request.merged == true &&
      contains(github.event.pull_request.labels.*.name, 'release')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install uv
        uses: astral-sh/setup-uv@v5

      - name: Install releasio
        run: uv tool install releasio

      - name: Perform Release
        env:
          GITHUB_TOKEN: ${{{{ secrets.GITHUB_TOKEN }}}}
        run: releasio release
"""

        workflow_path.write_text(workflow_content)
        console.print(f"  [green]✓[/] Created [cyan]{workflow_path}[/]")

        # Create PR title check workflow if requested
        if add_pr_check:
            pr_check_path = workflows_dir / "pr-title.yml"
            pr_check_content = """name: PR Title Check

on:
  pull_request:
    types: [opened, edited, synchronize, reopened]

jobs:
  check-title:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install uv
        uses: astral-sh/setup-uv@v5

      - name: Install releasio
        run: uv tool install releasio

      - name: Check PR Title
        env:
          GITHUB_PR_TITLE: ${{ github.event.pull_request.title }}
        run: releasio check-pr
"""
            pr_check_path.write_text(pr_check_content)
            console.print(f"  [green]✓[/] Created [cyan]{pr_check_path}[/]")

    console.print()
    console.print(
        Panel(
            "[bold green]Setup complete![/]\n\n"
            "[bold]Next steps:[/]\n"
            "  1. Review the configuration in [cyan]pyproject.toml[/]\n"
            "  2. Make some commits using conventional commit format\n"
            "  3. Run [cyan]releasio check[/] to preview your first release\n"
            "  4. Run [cyan]releasio release-pr[/] to create a release PR\n\n"
            "[bold]Conventional Commit Format:[/]\n"
            "  [cyan]feat:[/] A new feature (minor version bump)\n"
            "  [cyan]fix:[/]  A bug fix (patch version bump)\n"
            "  [cyan]feat!:[/] Breaking change (major version bump)\n\n"
            "[dim]Documentation: https://github.com/mikeleppane/release-py[/]",
            title="[green]Success[/]",
            border_style="green",
        )
    )
