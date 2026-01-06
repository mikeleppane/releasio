"""Implementation of the 'release' command.

The release command creates a git tag, publishes to PyPI,
and creates a GitHub release.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.panel import Panel

from releasio.config import load_config
from releasio.core.version import Version
from releasio.exceptions import (
    ConfigError,
    GitError,
    InvalidVersionError,
    ProjectError,
)
from releasio.vcs import GitRepository

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
    except ConfigError as e:
        err_console.print(f"[red]Error loading config:[/] {e}")
        raise SystemExit(1) from e

    # Initialize git repository
    try:
        repo = GitRepository(project_path)
    except GitError as e:
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
    from releasio.config.loader import get_project_name, get_project_version

    try:
        project_name = get_project_name(project_path)
        current_version_str = get_project_version(project_path)
        current_version = Version.parse(current_version_str)
    except (ProjectError, InvalidVersionError) as e:
        err_console.print(f"[red]Error getting project info:[/] {e}")
        raise SystemExit(1) from e

    # Create tag name
    tag_name = current_version.with_tag_prefix(config.version.tag_prefix)

    # Check if tag already exists
    if repo.tag_exists(tag_name):
        err_console.print(
            f"[red]Error:[/] Tag [cyan]{tag_name}[/] already exists.\n"
            "This version may have already been released."
        )
        raise SystemExit(1)

    # Get the previous tag BEFORE creating the new one (for changelog generation)
    # This is critical: we need to capture this before create_tag() runs
    tag_pattern = f"{config.version.tag_prefix}*"
    previous_tag = repo.get_latest_tag(tag_pattern)

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
            step = 2
            console.print(f"  {step}. Build package with {config.publish.tool}")
            step += 1
            if config.publish.validate_before_publish:
                console.print(f"  {step}. Validate distribution files with twine")
                step += 1
            if config.publish.check_existing_version:
                console.print(f"  {step}. Check if version exists on PyPI")
                step += 1
            console.print(f"  {step}. Publish to PyPI")
            step += 1
            console.print(f"  {step}. Create GitHub release for [cyan]{tag_name}[/]")
            if config.github.release_assets:
                step += 1
                console.print(
                    f"  {step}. Upload {len(config.github.release_assets)} release asset(s)"
                )
        else:
            console.print(f"  2. Create GitHub release for [cyan]{tag_name}[/]")
        console.print("\n[dim]Run with [cyan]--execute[/] to perform the release.[/]")
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
                console.print(f"  • Building package with {config.publish.tool}...")

            from releasio.publish.pypi import build_package

            dist_files = build_package(
                project_path,
                custom_command=custom_build,
                version=str(current_version),
                tool=config.publish.tool,
                console=console,
            )
            console.print("  [green]✓[/] Built package")

            # Step 2.5: Validate distribution files
            if config.publish.validate_before_publish:
                console.print("  • Validating distribution files...")
                from releasio.publish.pypi import validate_dist_files

                is_valid, validation_message = validate_dist_files(dist_files)
                if not is_valid:
                    err_console.print(
                        f"[red]Error:[/] Package validation failed:\n{validation_message}"
                    )
                    raise SystemExit(1)
                console.print("  [green]✓[/] Distribution files validated")

            # Step 2.6: Check if version already exists on PyPI
            if config.publish.check_existing_version:
                console.print("  • Checking if version exists on PyPI...")
                from releasio.publish.pypi import check_pypi_version_exists

                if check_pypi_version_exists(project_name, str(current_version)):
                    err_console.print(
                        f"[red]Error:[/] Version {current_version} already exists on PyPI.\n"
                        "This version may have already been published."
                    )
                    raise SystemExit(1)
                console.print("  [green]✓[/] Version not yet published")

            # Step 3: Publish to PyPI
            console.print("  • Publishing to PyPI...")
            from releasio.publish.pypi import publish_package

            publish_package(project_path, config.publish, dist_files=dist_files, console=console)
            console.print("  [green]✓[/] Published to PyPI")

        # Step 4: Create GitHub release
        console.print("  • Creating GitHub release...")
        owner, repo_name = repo.parse_github_remote()
        github_owner = config.github.owner or owner
        github_repo = config.github.repo or repo_name

        from releasio.forge.github import GitHubClient

        github = GitHubClient(owner=github_owner, repo=github_repo)

        # Generate changelog content and get contributors
        # Note: previous_tag was captured earlier, before creating the new tag
        changelog_content = None
        contributors: list[str] = []
        github_usernames: list[str] = []
        parsed_commits: list[Any] = []
        sha_to_username: dict[str, str | None] = {}
        github_url = f"https://github.com/{github_owner}/{github_repo}"

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
        elif config.github.release_body_use_commit_changelog:
            # Commit-based changelog with PR links and author attribution (FastAPI-style)
            try:
                from releasio.core.commits import ParsedCommit

                # Get commits since previous tag
                commits = repo.get_commits_since_tag(previous_tag)
                parsed_commits = [
                    ParsedCommit.from_commit(
                        c,
                        breaking_pattern=config.commits.breaking_pattern,
                        custom_parsers=config.commits.commit_parsers,
                        use_conventional_fallback=config.commits.use_conventional_fallback,
                    )
                    for c in commits
                ]

                # Resolve GitHub usernames if configured
                if config.github.release_body_resolve_usernames and parsed_commits:
                    console.print("  • Resolving GitHub usernames...")
                    try:
                        commit_shas = [pc.commit.sha for pc in parsed_commits]
                        sha_to_username = asyncio.run(github.get_commits_authors(commit_shas))
                        console.print("  [green]✓[/] Resolved GitHub usernames")
                    except Exception as e:
                        console.print(f"  [yellow]⚠[/] Could not resolve usernames: {e}")

                # Extract unique contributor usernames for the Contributors section
                github_usernames = list({u for u in sha_to_username.values() if u is not None})
            except Exception as e:
                console.print(
                    f"  [yellow]⚠[/] Could not parse commits: {e}\n"
                    "    Falling back to git-cliff changelog."
                )
                # Fall back to git-cliff
                parsed_commits = []
        else:
            # Commit-based changelog via git-cliff (default)
            try:
                from releasio.core.changelog import generate_changelog

                # Pass GitHub repo for richer changelog with PR links and @usernames
                github_repo_str = f"{github_owner}/{github_repo}"
                changelog_content = generate_changelog(
                    repo,
                    current_version,
                    config,
                    github_repo=github_repo_str,
                    console=console,
                )
            except Exception as e:
                console.print(
                    f"  [yellow]⚠[/] Could not generate changelog: {e}\n"
                    "    GitHub release will be created without changelog content."
                )

            # Get contributors from commits
            contributors = repo.get_contributors_since_tag(previous_tag)
            github_usernames = repo.get_contributor_github_usernames(previous_tag)

        # Collect asset filenames for the release body
        asset_filenames: list[str] = []
        if config.github.release_assets:
            for pattern in config.github.release_assets:
                asset_filenames.extend(p.name for p in project_path.glob(pattern) if p.exists())

        # Generate release notes
        release_body = _generate_release_body(
            project_name,
            current_version,
            parsed_commits=parsed_commits if parsed_commits else None,
            sha_to_username=sha_to_username if sha_to_username else None,
            github_url=github_url,
            changelog_content=changelog_content,
            contributors=contributors,
            github_usernames=github_usernames,
            assets=asset_filenames if asset_filenames else None,
            show_authors=config.github.release_body_show_authors,
            include_contributors=config.github.release_body_include_contributors,
            include_installation=config.github.release_body_include_installation,
            include_assets=config.github.release_body_include_assets,
            use_emojis=config.github.release_body_use_emojis,
        )

        async def create_release_with_assets() -> tuple[str, list[str]]:
            from mimetypes import guess_type

            # Create release
            release = await github.create_release(
                tag=tag_name,
                name=f"{project_name} v{current_version}",
                body=release_body,
                draft=config.github.draft_releases,
                prerelease=current_version.is_prerelease,
            )

            asset_urls = []
            # Upload assets if configured
            if config.github.release_assets and release.id:
                for pattern in config.github.release_assets:
                    # Use Path.glob() for better pathlib integration
                    asset_paths = list(project_path.glob(pattern))
                    for asset_path in asset_paths:
                        if asset_path.exists():
                            content_type = (
                                guess_type(str(asset_path))[0] or "application/octet-stream"
                            )
                            try:
                                url = await github.upload_release_asset(
                                    release.id, asset_path, content_type=content_type
                                )
                                asset_urls.append(url)
                            except Exception as e:
                                console.print(
                                    f"  [yellow]⚠[/] Failed to upload {asset_path.name}: {e}"
                                )

            return release.url, asset_urls

        release_url, uploaded_assets = asyncio.run(create_release_with_assets())
        console.print("  [green]✓[/] Created GitHub release")
        if uploaded_assets:
            console.print(f"  [green]✓[/] Uploaded {len(uploaded_assets)} asset(s)")

        # TODO: Future Feature - Security Advisory Integration
        # ========================================================
        # Configuration fields already added to SecurityConfig:
        # - enabled: bool
        # - auto_create_advisory: bool
        # - security_patterns: list[str]
        #
        # Implementation tasks:
        # 1. Scan commits for security-related patterns:
        #    - Default patterns: r"fix\(security\):", r"security:", r"CVE-\d{4}-\d+"
        #    - Use regex matching against commit messages
        #    - Respect config.security.security_patterns
        # 2. If security fixes detected and config.security.auto_create_advisory:
        #    - Create GitHub Security Advisory via GitHub API
        #    - API endpoint: POST /repos/{owner}/{repo}/security-advisories
        #    - Extract CVE info, severity, and affected versions from commits
        # 3. Link advisory to the release:
        #    - Add advisory URL to release notes
        #    - Tag commits with security labels
        # 4. Handle private security advisories:
        #    - Support private advisories (default for security)
        #    - Option to publish advisory immediately or keep private
        # 5. Extract structured security information:
        #    - CVE IDs from commit messages
        #    - Severity level (critical, high, medium, low)
        #    - Affected versions range
        #    - CVSS scores if provided
        # 6. Add tests for security detection and advisory creation
        #
        # Related files:
        # - src/releasio/forge/github.py - Add create_security_advisory() method
        # - src/releasio/core/commits.py - Add security pattern detection
        # - src/releasio/cli/commands/release.py - Call advisory creation here
        # - tests/unit/test_security.py (new) - Tests for security detection
        #
        # GitHub API Reference:
        # https://docs.github.com/en/rest/security-advisories/repository-advisories
        # ========================================================

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
    parsed_commits: list[Any] | None = None,
    sha_to_username: dict[str, str | None] | None = None,
    github_url: str | None = None,
    changelog_content: str | None = None,
    contributors: list[str] | None = None,
    github_usernames: list[str] | None = None,
    assets: list[str] | None = None,
    *,
    show_authors: bool = True,
    include_contributors: bool = True,
    include_installation: bool = True,
    include_assets: bool = True,
    use_emojis: bool = True,
) -> str:
    """Generate a professional GitHub release body.

    Creates a well-formatted release page with:
    - Version header with date
    - Changes grouped by type (Features, Bug Fixes, etc.)
    - Author attribution with GitHub profile links
    - Contributors section
    - Installation instructions
    - Assets list (if provided)

    Args:
        project_name: Name of the project
        version: Version being released
        parsed_commits: List of ParsedCommit instances for structured changelog
        sha_to_username: Mapping of commit SHA to GitHub username
        github_url: Base GitHub URL for links
        changelog_content: Fallback changelog content (if parsed_commits not available)
        contributors: List of contributor names
        github_usernames: List of GitHub usernames
        assets: List of asset filenames
        show_authors: Whether to show author attribution
        include_contributors: Whether to include contributors section
        include_installation: Whether to include installation instructions
        include_assets: Whether to include assets section
        use_emojis: Whether to use emojis in section headers

    Returns:
        Formatted release body markdown
    """
    from datetime import UTC, datetime

    lines: list[str] = []

    # Version header with date
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    lines.append(f"## [{version}] - {today}")
    lines.append("")

    # If we have parsed commits, generate structured changelog like release PR
    if parsed_commits:
        lines.extend(
            _generate_changelog_from_commits(
                parsed_commits,
                sha_to_username or {},
                github_url,
                show_authors=show_authors,
                use_emojis=use_emojis,
            )
        )
    elif changelog_content:
        # Fallback to provided changelog content
        content = changelog_content.strip()
        # Remove leading version headers (we already added one)
        import re

        content = re.sub(r"^#+\s*\[?v?\d+\.\d+\.\d+.*?\]?.*?\n+", "", content, flags=re.MULTILINE)
        if content:
            lines.append(content)
            lines.append("")

    # Contributors section
    if include_contributors:
        if github_usernames:
            lines.append("## Contributors")
            lines.append("")
            lines.extend(f"- [@{u}](https://github.com/{u})" for u in github_usernames)
            lines.append("")
        elif contributors:
            lines.append("## Contributors")
            lines.append("")
            lines.extend(f"- {c}" for c in contributors)
            lines.append("")

    # Assets section (if any)
    if include_assets and assets:
        lines.append("## Assets")
        lines.append("")
        lines.extend(f"- `{asset}`" for asset in assets)
        lines.append("")

    # Installation section
    if include_installation:
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


def _generate_changelog_from_commits(
    parsed_commits: list[Any],
    sha_to_username: dict[str, str | None],
    github_url: str | None,
    *,
    show_authors: bool = True,
    use_emojis: bool = True,
) -> list[str]:
    """Generate changelog lines from parsed commits (FastAPI-style).

    Args:
        parsed_commits: List of ParsedCommit instances
        sha_to_username: Mapping of commit SHA to GitHub username
        github_url: Base GitHub URL for links
        show_authors: Whether to show author attribution
        use_emojis: Whether to use emojis in section headers

    Returns:
        List of markdown lines for the changelog section
    """
    import re

    lines: list[str] = []

    # Group commits by type
    by_type: dict[str, list[Any]] = {}
    breaking: list[Any] = []

    for pc in parsed_commits:
        if pc.is_breaking:
            breaking.append(pc)
        commit_type = pc.commit_type or "other"
        by_type.setdefault(commit_type, []).append(pc)

    # Type labels with and without emojis
    type_labels_with_emoji = {
        "feat": "✨ Features",
        "fix": "🐛 Bug Fixes",
        "perf": "⚡ Performance",
        "docs": "📝 Docs",
        "refactor": "♻️ Refactors",
        "test": "🧪 Tests",
        "build": "📦 Build",
        "ci": "👷 Internal",
        "style": "💄 Style",
        "chore": "🔧 Chores",
        "other": "📋 Other",
    }
    type_labels_plain = {
        "feat": "Features",
        "fix": "Bug Fixes",
        "perf": "Performance",
        "docs": "Documentation",
        "refactor": "Refactors",
        "test": "Tests",
        "build": "Build",
        "ci": "Internal",
        "style": "Style",
        "chore": "Chores",
        "other": "Other",
    }
    type_labels = type_labels_with_emoji if use_emojis else type_labels_plain

    # Pattern to extract PR number from description
    pr_pattern = re.compile(r"\(#(\d+)\)\s*$")

    def format_entry(pc: Any) -> str:
        """Format a single commit entry (FastAPI-style).

        Format: description. PR #123 by @username.
        """
        parts = []

        # Add scope if present (bold)
        if pc.scope:
            parts.append(f"**{pc.scope}**: ")

        # Extract PR number and clean description
        description = pc.description
        pr_match = pr_pattern.search(description)
        pr_number = None
        if pr_match:
            pr_number = int(pr_match.group(1))
            description = pr_pattern.sub("", description).strip()

        # Capitalize first letter
        if description:
            description = description[0].upper() + description[1:]

        parts.append(description)

        # Add PR/commit link and optionally author
        if show_authors:
            # Format author link (FastAPI-style: @username as link)
            github_username = sha_to_username.get(pc.commit.sha)
            if github_username:
                author_link = f"[@{github_username}](https://github.com/{github_username})"
            else:
                author_link = pc.commit.author_name

            if pr_number and github_url:
                pr_url = f"{github_url}/pull/{pr_number}"
                parts.append(f". PR [#{pr_number}]({pr_url}) by {author_link}.")
            elif pr_number:
                parts.append(f". PR #{pr_number} by {author_link}.")
            else:
                short_sha = pc.commit.short_sha
                if github_url:
                    commit_url = f"{github_url}/commit/{pc.commit.sha}"
                    parts.append(f". Commit [{short_sha}]({commit_url}) by {author_link}.")
                else:
                    parts.append(f". Commit {short_sha} by {author_link}.")
        elif pr_number and github_url:
            # No author, just PR/commit link
            pr_url = f"{github_url}/pull/{pr_number}"
            parts.append(f". PR [#{pr_number}]({pr_url}).")
        elif pr_number:
            parts.append(f". PR #{pr_number}.")
        else:
            short_sha = pc.commit.short_sha
            if github_url:
                commit_url = f"{github_url}/commit/{pc.commit.sha}"
                parts.append(f". Commit [{short_sha}]({commit_url}).")
            else:
                parts.append(f". Commit {short_sha}.")

        return "".join(parts)

    # Breaking changes first (highlighted section)
    if breaking:
        breaking_label = "⚠️ Breaking Changes" if use_emojis else "Breaking Changes"
        lines.append(f"### {breaking_label}")
        lines.append("")
        lines.extend(f"* {format_entry(pc)}" for pc in breaking)
        lines.append("")

    # Other changes by type
    for commit_type, label in type_labels.items():
        commits_of_type = by_type.get(commit_type, [])
        # Filter out breaking (already listed)
        commits_of_type = [c for c in commits_of_type if not c.is_breaking]

        if commits_of_type:
            lines.append(f"### {label}")
            lines.append("")
            lines.extend(f"* {format_entry(pc)}" for pc in commits_of_type)
            lines.append("")

    return lines
