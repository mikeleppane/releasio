"""Command-line interface for releasio.

This module provides the Typer-based CLI with commands for:
- check: Preview what would happen (dry-run)
- update: Update version and changelog locally
- release-pr: Create/update a release pull request
- release: Perform the actual release
- init: Initialize configuration
"""

from __future__ import annotations

from release_py.cli.app import app

__all__ = ["app"]
