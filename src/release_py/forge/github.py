"""GitHub API client implementation.

This module provides an async client for the GitHub API using httpx.
It implements the Forge protocol for creating PRs and releases.

Authentication is handled via:
1. GITHUB_TOKEN environment variable
2. gh CLI auth token (fallback)
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from typing import Any

import httpx

from release_py.exceptions import AuthenticationError, ForgeError, RateLimitError
from release_py.forge.base import MergeRequest, MergeRequestState, Release

# Retry configuration for rate limiting
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds
RETRY_MAX_DELAY = 60.0  # seconds


class GitHubClient:
    """Async GitHub API client.

    Implements the Forge protocol for GitHub-specific operations.

    Args:
        owner: Repository owner (user or organization)
        repo: Repository name
        token: GitHub token (optional, uses env var if not provided)
        api_url: GitHub API base URL (for GitHub Enterprise support)

    Example:
        >>> client = GitHubClient(owner="user", repo="project")
        >>> pr = await client.create_pull_request(
        ...     title="Release v1.0.0",
        ...     body="Changelog here",
        ...     head="release",
        ...     base="main",
        ... )

        # GitHub Enterprise
        >>> client = GitHubClient(
        ...     owner="user",
        ...     repo="project",
        ...     api_url="https://github.mycompany.com/api/v3",
        ... )
    """

    DEFAULT_API_URL = "https://api.github.com"

    def __init__(
        self,
        owner: str,
        repo: str,
        token: str | None = None,
        api_url: str | None = None,
    ) -> None:
        self.owner = owner
        self.repo = repo
        self.base_url = (api_url or self.DEFAULT_API_URL).rstrip("/")
        self._token = token or self._get_token()

    def _get_token(self) -> str:
        """Get GitHub token from environment or gh CLI."""
        # Try environment variable first
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token:
            return token

        # Try gh CLI
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        raise AuthenticationError(
            "No GitHub token found. Set GITHUB_TOKEN environment variable "
            "or authenticate with: gh auth login"
        )

    def _get_headers(self) -> dict[str, str]:
        """Get headers for API requests."""
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make an API request with retry logic for rate limits.

        Args:
            method: HTTP method
            path: API path (without base URL)
            **kwargs: Additional arguments for httpx

        Returns:
            JSON response as dictionary

        Raises:
            AuthenticationError: If authentication fails
            RateLimitError: If rate limit exceeded after retries
            ForgeError: For other API errors
        """
        url = f"{self.base_url}{path}"
        headers = self._get_headers()
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.request(
                        method,
                        url,
                        headers=headers,
                        **kwargs,
                    )

                # Handle errors
                if response.status_code == 401:
                    raise AuthenticationError("GitHub authentication failed. Check your token.")
                if response.status_code == 403:
                    # Check for rate limit
                    if "rate limit" in response.text.lower():
                        reset_at = response.headers.get("X-RateLimit-Reset")
                        if attempt < MAX_RETRIES:
                            delay = self._calculate_rate_limit_delay(reset_at, attempt)
                            await asyncio.sleep(delay)
                            continue
                        raise RateLimitError(reset_at=reset_at)
                    raise ForgeError(f"GitHub API forbidden: {response.text}")
                if response.status_code == 404:
                    return {}  # Return empty dict for not found
                if response.status_code == 429:
                    # Secondary rate limit (abuse detection)
                    retry_after = response.headers.get("Retry-After", "60")
                    if attempt < MAX_RETRIES:
                        delay = min(float(retry_after), RETRY_MAX_DELAY)
                        await asyncio.sleep(delay)
                        continue
                    raise RateLimitError(reset_at=str(int(time.time()) + int(retry_after)))
                if response.status_code >= 400:
                    raise ForgeError(f"GitHub API error ({response.status_code}): {response.text}")

                if response.status_code == 204:  # No content
                    return {}

                result: dict[str, Any] = response.json()
                return result  # noqa: TRY300

            except httpx.RequestError as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    delay = min(
                        RETRY_BASE_DELAY * (2**attempt),
                        RETRY_MAX_DELAY,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise ForgeError(f"Network error: {e}") from e

        # Should not reach here, but just in case
        if last_error:
            raise ForgeError(f"Request failed after retries: {last_error}") from last_error
        raise ForgeError("Request failed after retries")

    def _calculate_rate_limit_delay(
        self,
        reset_at: str | None,
        attempt: int,
    ) -> float:
        """Calculate delay for rate limit retry.

        Uses reset time from headers if available, otherwise exponential backoff.

        Args:
            reset_at: Unix timestamp when rate limit resets
            attempt: Current retry attempt (0-indexed)

        Returns:
            Delay in seconds
        """
        if reset_at:
            try:
                reset_time = int(reset_at)
                delay = max(0, reset_time - int(time.time()) + 1)
                return float(min(delay, RETRY_MAX_DELAY))
            except ValueError:
                pass
        # Fallback to exponential backoff
        return float(min(RETRY_BASE_DELAY * (2**attempt), RETRY_MAX_DELAY))

    # =========================================================================
    # Pull Request Operations
    # =========================================================================

    async def find_pull_request(
        self,
        head: str,
        base: str,
    ) -> MergeRequest | None:
        """Find an open pull request for the given branches.

        Args:
            head: Source branch name
            base: Target branch name

        Returns:
            MergeRequest if found, None otherwise
        """
        path = f"/repos/{self.owner}/{self.repo}/pulls"
        params = {
            "head": f"{self.owner}:{head}",
            "base": base,
            "state": "open",
        }

        data = await self._request("GET", path, params=params)

        if not data or not isinstance(data, list) or len(data) == 0:
            return None

        return self._parse_pull_request(data[0])

    async def create_pull_request(
        self,
        title: str,
        body: str,
        head: str,
        base: str,
        labels: list[str] | None = None,
    ) -> MergeRequest:
        """Create a new pull request.

        Args:
            title: PR title
            body: PR description
            head: Source branch
            base: Target branch
            labels: Optional labels to apply

        Returns:
            The created MergeRequest
        """
        path = f"/repos/{self.owner}/{self.repo}/pulls"
        payload = {
            "title": title,
            "body": body,
            "head": head,
            "base": base,
        }

        data = await self._request("POST", path, json=payload)
        pr = self._parse_pull_request(data)

        # Add labels if provided
        if labels:
            await self._add_labels(pr.number, labels)

        return pr

    async def update_pull_request(
        self,
        number: int,
        title: str | None = None,
        body: str | None = None,
    ) -> MergeRequest:
        """Update an existing pull request.

        Args:
            number: PR number to update
            title: New title (optional)
            body: New description (optional)

        Returns:
            The updated MergeRequest
        """
        path = f"/repos/{self.owner}/{self.repo}/pulls/{number}"
        payload: dict[str, str] = {}

        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body

        data = await self._request("PATCH", path, json=payload)
        return self._parse_pull_request(data)

    async def _add_labels(self, issue_number: int, labels: list[str]) -> None:
        """Add labels to an issue or PR."""
        path = f"/repos/{self.owner}/{self.repo}/issues/{issue_number}/labels"
        await self._request("POST", path, json={"labels": labels})

    def _parse_pull_request(self, data: dict[str, Any]) -> MergeRequest:
        """Parse API response into MergeRequest."""
        state_str = data.get("state", "open")
        if data.get("merged"):
            state = MergeRequestState.MERGED
        elif state_str == "closed":
            state = MergeRequestState.CLOSED
        else:
            state = MergeRequestState.OPEN

        labels = [label["name"] for label in data.get("labels", [])]

        return MergeRequest(
            number=data["number"],
            title=data["title"],
            body=data.get("body") or "",
            head_branch=data["head"]["ref"],
            base_branch=data["base"]["ref"],
            url=data["html_url"],
            state=state,
            labels=labels,
        )

    # =========================================================================
    # Release Operations
    # =========================================================================

    async def create_release(
        self,
        tag: str,
        name: str,
        body: str,
        draft: bool = False,
        prerelease: bool = False,
    ) -> Release:
        """Create a new GitHub release.

        Args:
            tag: Git tag for the release
            name: Release name
            body: Release notes
            draft: Create as draft
            prerelease: Mark as pre-release

        Returns:
            The created Release
        """
        path = f"/repos/{self.owner}/{self.repo}/releases"
        payload = {
            "tag_name": tag,
            "name": name,
            "body": body,
            "draft": draft,
            "prerelease": prerelease,
        }

        data = await self._request("POST", path, json=payload)
        return self._parse_release(data)

    async def get_release_by_tag(self, tag: str) -> Release | None:
        """Get a release by its tag.

        Args:
            tag: Tag to look up

        Returns:
            Release if found, None otherwise
        """
        path = f"/repos/{self.owner}/{self.repo}/releases/tags/{tag}"
        data = await self._request("GET", path)

        if not data:
            return None

        return self._parse_release(data)

    def _parse_release(self, data: dict[str, Any]) -> Release:
        """Parse API response into Release."""
        assets = [asset["browser_download_url"] for asset in data.get("assets", [])]

        return Release(
            tag=data["tag_name"],
            name=data["name"],
            body=data.get("body") or "",
            url=data["html_url"],
            draft=data.get("draft", False),
            prerelease=data.get("prerelease", False),
            assets=assets,
        )

    # =========================================================================
    # PR-based Changelog & Contributors (for large open source projects)
    # =========================================================================

    async def get_merged_prs_between_tags(
        self,
        base_tag: str | None,
        head_tag: str | None = None,
        batch_size: int = 10,
    ) -> list[dict[str, Any]]:
        """Get all merged PRs between two tags.

        This is the key method for large open source projects that use
        squash merging. Instead of analyzing individual commits, we
        analyze the PRs that were merged.

        Uses parallel fetching with asyncio.gather() for performance,
        processing PRs in batches to avoid overwhelming the API.

        Args:
            base_tag: Starting tag (exclusive). None = from beginning.
            head_tag: Ending tag (inclusive). None = up to HEAD.
            batch_size: Number of PRs to fetch in parallel (default: 10).

        Returns:
            List of PR data dicts with keys:
            - number: PR number
            - title: PR title
            - body: PR description
            - user: Author username
            - merged_at: Merge timestamp
            - labels: List of label names
            - url: HTML URL to PR
        """
        import re

        # Get commits between tags to find merge commits
        compare_path = f"/repos/{self.owner}/{self.repo}/compare/"
        if base_tag:
            compare_path += f"{base_tag}..."
        compare_path += head_tag if head_tag else "HEAD"

        compare_data = await self._request("GET", compare_path)
        commits = compare_data.get("commits", [])

        # Extract PR numbers from commit messages (squash merge format)
        # Pattern: "Title (#123)" or "Merge pull request #123"
        pr_numbers: set[int] = set()

        for commit in commits:
            message = commit.get("commit", {}).get("message", "")
            # Match "(#123)" pattern (squash merge)
            for match in re.finditer(r"\(#(\d+)\)", message):
                pr_numbers.add(int(match.group(1)))
            # Match "Merge pull request #123" pattern
            for match in re.finditer(r"Merge pull request #(\d+)", message):
                pr_numbers.add(int(match.group(1)))

        # Fetch PR details in parallel batches
        sorted_pr_numbers = sorted(pr_numbers)
        prs: list[dict[str, Any]] = []

        for i in range(0, len(sorted_pr_numbers), batch_size):
            batch = sorted_pr_numbers[i : i + batch_size]
            tasks = [self._get_pr_details(pr_number) for pr_number in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Filter valid results (ignore exceptions and None)
            prs.extend(result for result in results if isinstance(result, dict) and result)

        return prs

    async def _get_pr_details(self, pr_number: int) -> dict[str, Any] | None:
        """Get details for a specific PR."""
        path = f"/repos/{self.owner}/{self.repo}/pulls/{pr_number}"
        data = await self._request("GET", path)

        if not data:
            return None

        return {
            "number": data["number"],
            "title": data["title"],
            "body": data.get("body") or "",
            "user": data["user"]["login"],
            "merged_at": data.get("merged_at"),
            "labels": [label["name"] for label in data.get("labels", [])],
            "url": data["html_url"],
        }

    async def get_pr_for_commit(self, commit_sha: str) -> dict[str, Any] | None:
        """Get the PR associated with a commit.

        Uses GitHub's API to find PRs that contain a specific commit.
        This works for both merge commits and squash commits.

        Args:
            commit_sha: The commit SHA to look up.

        Returns:
            PR data dict or None if no PR found.
        """
        path = f"/repos/{self.owner}/{self.repo}/commits/{commit_sha}/pulls"
        data = await self._request("GET", path)

        if not data or not isinstance(data, list) or len(data) == 0:
            return None

        # Return the first (most relevant) PR
        pr = data[0]
        return {
            "number": pr["number"],
            "title": pr["title"],
            "body": pr.get("body") or "",
            "user": pr["user"]["login"],
            "merged_at": pr.get("merged_at"),
            "labels": [label["name"] for label in pr.get("labels", [])],
            "url": pr["html_url"],
        }

    async def get_contributors_from_prs(
        self,
        prs: list[dict[str, Any]],
        ignore_authors: list[str] | None = None,
    ) -> list[str]:
        """Extract unique contributor usernames from PRs.

        Args:
            prs: List of PR data dicts (from get_merged_prs_between_tags).
            ignore_authors: List of usernames to exclude (e.g., bots).

        Returns:
            Sorted list of unique GitHub usernames.
        """
        ignore_set = set(ignore_authors or [])
        contributors: set[str] = set()

        for pr in prs:
            user = pr.get("user")
            if user and user not in ignore_set:
                contributors.add(user)

        return sorted(contributors, key=str.lower)

    async def generate_pr_based_changelog(
        self,
        base_tag: str | None,
        head_tag: str | None = None,
        ignore_authors: list[str] | None = None,
    ) -> str:
        """Generate changelog from merged PRs.

        This creates a changelog similar to FastAPI/Ruff style with
        PR links and author attribution.

        Args:
            base_tag: Starting tag (exclusive).
            head_tag: Ending tag (inclusive).
            ignore_authors: List of usernames to exclude (e.g., bots).

        Returns:
            Markdown formatted changelog.
        """
        import re

        ignore_set = set(ignore_authors or [])
        prs = await self.get_merged_prs_between_tags(base_tag, head_tag)

        # Filter out bot PRs
        prs = [pr for pr in prs if pr.get("user") not in ignore_set]

        if not prs:
            return ""

        # Categorize PRs by conventional commit prefix in title
        categories: dict[str, list[dict[str, Any]]] = {
            "breaking": [],
            "feat": [],
            "fix": [],
            "perf": [],
            "docs": [],
            "refactor": [],
            "test": [],
            "ci": [],
            "chore": [],
            "other": [],
        }

        category_labels = {
            "breaking": "⚠️ Breaking Changes",
            "feat": "✨ Features",
            "fix": "🐛 Bug Fixes",
            "perf": "⚡ Performance",
            "docs": "📚 Documentation",
            "refactor": "♻️ Refactoring",
            "test": "🧪 Tests",
            "ci": "🔧 CI/CD",
            "chore": "🔨 Maintenance",
            "other": "📝 Other Changes",
        }

        # Categorize each PR
        for pr in prs:
            title = pr["title"]
            labels = [label.lower() for label in pr.get("labels", [])]

            # Check for breaking changes
            if "breaking" in labels or title.startswith("!") or "BREAKING" in title.upper():
                categories["breaking"].append(pr)
                continue

            # Match conventional commit prefix
            match = re.match(r"^(\w+)(?:\([^)]+\))?!?:\s*", title)
            if match:
                prefix = match.group(1).lower()
                if prefix in categories:
                    categories[prefix].append(pr)
                    continue

            categories["other"].append(pr)

        # Build changelog
        lines: list[str] = []

        for category, category_prs in categories.items():
            if not category_prs:
                continue

            lines.append(f"### {category_labels[category]}")
            lines.append("")

            for pr in category_prs:
                title = pr["title"]
                # Remove conventional commit prefix for cleaner display
                clean_title = re.sub(r"^(\w+)(?:\([^)]+\))?!?:\s*", "", title)
                pr_link = f"[#{pr['number']}]({pr['url']})"
                user_link = f"[@{pr['user']}](https://github.com/{pr['user']})"
                lines.append(f"- {clean_title} {pr_link} by {user_link}")

            lines.append("")

        return "\n".join(lines)
