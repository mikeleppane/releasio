<p align="center">
  <img src="images/logo.png" alt="releasio logo" width="200">
</p>

<h1 align="center">releasio</h1>

<p align="center">
  <strong>Automated releases for Python projects</strong><br>
  <em>Version bumping, changelog generation, and PyPI publishing powered by conventional commits</em>
</p>

<p align="center">
  <a href="https://pypi.org/project/releasio/"><img src="https://img.shields.io/pypi/v/releasio.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/releasio/"><img src="https://img.shields.io/pypi/pyversions/releasio.svg" alt="Python versions"></a>
  <a href="https://github.com/mikeleppane/release-py/blob/main/LICENSE"><img src="https://img.shields.io/github/license/mikeleppane/release-py.svg" alt="License"></a>
  <a href="https://github.com/mikeleppane/release-py/actions/workflows/ci.yml"><img src="https://github.com/mikeleppane/release-py/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://codecov.io/gh/mikeleppane/release-py"><img src="https://codecov.io/gh/mikeleppane/release-py/branch/main/graph/badge.svg" alt="codecov"></a>
</p>

<p align="center">
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
  <a href="https://mypy-lang.org/"><img src="https://www.mypy-lang.org/static/mypy_badge.svg" alt="Checked with mypy"></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv"></a>
</p>

---

Inspired by [release-plz](https://github.com/MarcoIeni/release-plz), releasio brings the same powerful release automation to the Python ecosystem. It analyzes your [Conventional Commits](https://www.conventionalcommits.org/) to automatically determine version bumps, generate beautiful changelogs, and publish to PyPI.

## Features

- **Release PR Workflow** - Automatically creates and maintains a release PR with version bump and changelog
- **Conventional Commits** - Automatic version bumping based on commit types (`feat:`, `fix:`, etc.)
- **Beautiful Changelogs** - Professional changelog generation with PR links and author attribution
- **Zero Config** - Works out of the box with sensible defaults
- **GitHub Actions** - First-class GitHub Actions support with outputs
- **PyPI Trusted Publishing** - Native OIDC support, no tokens required
- **Pre-1.0.0 Semver** - Proper handling of 0.x.y versions (breaking changes bump minor, not major)
- **Pre-release Versions** - Support for alpha, beta, and rc versions
- **Fully Typed** - Complete type annotations with `py.typed` marker

## Installation

```bash
# Using uv (recommended)
uv tool install releasio

# Using pip
pip install releasio

# Using pipx
pipx install releasio
```

### Prerequisites: git-cliff

releasio requires [git-cliff](https://git-cliff.org/) for changelog generation. **This must be installed separately** as it's a Rust binary:

```bash
# Using uv (recommended)
uv tool install git-cliff

# Using cargo (if you have Rust installed)
cargo install git-cliff

# Using Homebrew (macOS/Linux)
brew install git-cliff

# Using scoop (Windows)
scoop install git-cliff
```

## Quick Start

```bash
# 1. Check what would happen (always safe)
releasio check

# 2. Preview a release PR (safe - dry-run by default)
releasio release-pr

# 3. Create the release PR
releasio release-pr --execute

# 4. After merging the PR, preview the release
releasio release

# 5. Perform the actual release
releasio release --execute
```

All commands that make changes default to **dry-run mode** for safety. Use `--execute` to apply changes.

releasio handles version bumping, changelog generation, git tagging, PyPI publishing, and GitHub release creation.

## CLI Commands

| Command | Description |
|---------|-------------|
| `releasio check` | Preview what would happen during a release |
| `releasio update` | Update version and changelog locally |
| `releasio release-pr` | Create or update a release pull request |
| `releasio release` | Tag, publish to PyPI, and create GitHub release |
| `releasio do-release` | **Complete workflow**: update + commit + tag + publish (recommended) |
| `releasio check-pr` | Validate PR title follows conventional commits |
| `releasio init` | Initialize releasio configuration |

### Common Options

```bash
# All commands that make changes default to dry-run (safe mode)
releasio update                        # Preview changes (dry-run)
releasio update --execute              # Apply changes
releasio release-pr                    # Preview PR (dry-run)
releasio release-pr --execute          # Create/update PR
releasio release                       # Preview release (dry-run)
releasio release --execute             # Perform release

# Complete release workflow (recommended for simple projects)
releasio do-release                    # Preview complete release (dry-run)
releasio do-release --execute          # Update + commit + tag + publish

# Version control
releasio update --version 2.0.0        # Force specific version
releasio update --prerelease alpha     # Create pre-release (1.2.0a1)
releasio do-release --execute --version 2.0.0  # One-command release with version override
releasio release --execute --skip-publish  # Skip PyPI publishing
releasio check-pr --require-scope      # Require scope in PR title
```

## GitHub Actions

releasio provides a GitHub Action for seamless CI/CD integration.

### Required Repository Settings

Before using releasio in GitHub Actions, enable this setting:

1. Go to **Settings → Actions → General → Workflow permissions**
2. Enable **"Allow GitHub Actions to create and approve pull requests"**
3. Click **Save**

This allows the `GITHUB_TOKEN` to create release PRs.

### CI on Release PRs

**Note:** PRs created by `github-actions[bot]` using `GITHUB_TOKEN` won't automatically trigger CI workflows (this is a GitHub security feature to prevent infinite loops).

Options to run CI on release PRs:

- **Manually trigger CI** via the Actions tab
- **Use a Personal Access Token (PAT)** instead of `GITHUB_TOKEN` - store it as `secrets.RELEASE_TOKEN` and pass it via `github-token` input
- **Push to the release branch** to trigger CI

### Recommended Workflow

Create `.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    branches: [main]
  pull_request:
    types: [closed]
    branches: [main]

permissions:
  contents: write
  pull-requests: write
  id-token: write  # For PyPI trusted publishing

jobs:
  # Create/update release PR on every push to main
  release-pr:
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: mikeleppane/release-py@v1
        with:
          command: release-pr

  # Perform release when release PR is merged
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

      - uses: mikeleppane/release-py@v1
        with:
          command: release
        # PyPI trusted publishing - no token needed!
```

### Action Inputs

| Input | Description | Default |
|-------|-------------|---------|
| `command` | Command: `release-pr`, `release`, `check`, `check-pr` | *required* |
| `github-token` | GitHub token for API access | `github.token` |
| `python-version` | Python version to use | `3.11` |
| `dry-run` | Run without making changes | `false` |
| `skip-publish` | Skip PyPI publishing | `false` |

### Action Outputs

| Output | Description |
|--------|-------------|
| `version` | The version released/to be released |
| `pr-number` | Created/updated PR number |
| `pr-url` | Created/updated PR URL |
| `release-url` | GitHub release URL |
| `tag` | Git tag created |

## Required Credentials

Releasio needs credentials for PyPI publishing and GitHub releases.

### PyPI Publishing

For publishing to PyPI, set one of these (in order of precedence):

| Method | Environment Variable | Notes |
|--------|---------------------|-------|
| **Trusted Publishing** (recommended) | None | Works automatically in GitHub Actions with OIDC |
| **PyPI Token** | `PYPI_TOKEN` | API token from pypi.org |
| **UV Token** | `UV_PUBLISH_TOKEN` | Alternative for uv |
| **pypirc file** | None | Configure `~/.pypirc` |

**Getting a PyPI Token:**
1. Go to [pypi.org/manage/account](https://pypi.org/manage/account/)
2. Create an API token (project-scoped recommended)
3. Set it as `PYPI_TOKEN` environment variable

### GitHub Releases

For creating GitHub releases, set one of these:

| Method | Environment Variable | Notes |
|--------|---------------------|-------|
| **GitHub Actions** | `GITHUB_TOKEN` | Automatically available via `secrets.GITHUB_TOKEN` |
| **Personal Token** | `GITHUB_TOKEN` or `GH_TOKEN` | PAT with `contents: write` permission |

**Required Permissions:**
- `contents: write` - Create releases and push tags

### Local Development Example

```bash
# Set credentials for local releases
export PYPI_TOKEN="pypi-..."
export GITHUB_TOKEN="ghp_..."

# Now run the release
releasio do-release --execute
```

### GitHub Actions Example

```yaml
- uses: mikeleppane/release-py@v2
  with:
    command: release
    execute: true
    github-token: ${{ secrets.GITHUB_TOKEN }}
  # PyPI uses trusted publishing - no token needed!
```

## How It Works

```text
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Push to main  │────▶│  release-pr     │────▶│  Release PR     │
│   (commits)     │     │  (automated)    │     │  Created/Updated│
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         │ Merge PR
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  GitHub Release │◀────│    release      │◀────│   PR Merged     │
│  + PyPI Publish │     │   (automated)   │     │   (manual)      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### Version Bumping Rules

| Commit Type | Version Bump | Example |
|-------------|--------------|---------|
| `feat:` | Minor (0.1.0 → 0.2.0) | `feat: add user authentication` |
| `fix:` | Patch (0.1.0 → 0.1.1) | `fix: handle null response` |
| `perf:` | Patch | `perf: optimize database queries` |
| `feat!:` or `BREAKING CHANGE:` | Major* | `feat!: redesign API` |

*For 0.x.y versions, breaking changes bump minor instead of major to prevent accidental 1.0.0 releases.

## Configuration

Configuration is optional. releasio works out of the box with sensible defaults.

### Custom Configuration Files

releasio supports standalone TOML configuration files in addition to `pyproject.toml`. This is useful for projects that prefer dedicated config files or need monorepo-style configurations.

**Configuration file precedence** (highest to lowest):

1. `.releasio.toml` (dotfile, hidden)
2. `releasio.toml` (visible file)
3. `pyproject.toml` under `[tool.releasio]` section

Create a `.releasio.toml` or `releasio.toml` file in your project root:

```toml
# .releasio.toml
# Note: Custom config files use flattened structure (no [tool.releasio] wrapper)

default_branch = "main"

[version]
tag_prefix = "v"

[commits]
types_minor = ["feat"]
types_patch = ["fix", "perf", "docs"]

[changelog]
path = "CHANGELOG.md"
use_github_prs = false

[github]
release_pr_labels = ["release"]
draft_releases = false

[publish]
tool = "uv"
trusted_publishing = true
```

**Important notes:**

- Custom config files (`.releasio.toml` and `releasio.toml`) use **top-level keys** (no `[tool.releasio]` wrapper)
- You still need `pyproject.toml` for project metadata (name, version)
- Custom configs are only searched in the current directory
- `pyproject.toml` configs walk up the directory tree (existing behavior)
- See [`.releasio.toml.example`](.releasio.toml.example) for a complete example

### pyproject.toml Configuration

Add to `pyproject.toml` if you prefer traditional configuration:

```toml
[tool.releasio]
default_branch = "main"

[tool.releasio.version]
tag_prefix = "v"

[tool.releasio.commits]
types_minor = ["feat"]
types_patch = ["fix", "perf", "docs"]

[tool.releasio.changelog]
path = "CHANGELOG.md"
use_github_prs = false  # Set to true for squash merge workflows

[tool.releasio.github]
release_pr_labels = ["release"]
draft_releases = false

[tool.releasio.publish]
tool = "uv"  # or "poetry", "pdm", "twine"
trusted_publishing = true
```

### Using Poetry

If your project uses Poetry, configure releasio to use it for building and publishing:

```toml
[tool.releasio.publish]
tool = "poetry"
```

Configure authentication:

```bash
poetry config pypi-token.pypi your-token-here
```

### Using PDM

If your project uses PDM, configure releasio to use it for building and publishing:

```toml
[tool.releasio.publish]
tool = "pdm"
```

Configure authentication:

```bash
export PDM_PUBLISH_PASSWORD=your-token-here
# or
pdm config pypi.token your-token-here
```

### Multi-branch Release Channels

Automatically create pre-release versions based on the branch you're releasing from. This is useful for projects that maintain multiple release channels (e.g., stable, beta, alpha).

```toml
[tool.releasio.branches.main]
match = "main"
prerelease = false  # Stable releases from main

[tool.releasio.branches.beta]
match = "beta"
prerelease = true
prerelease_token = "beta"  # 1.2.0 → 1.2.0-beta.1

[tool.releasio.branches.alpha]
match = "alpha"
prerelease = true
prerelease_token = "alpha"  # 1.2.0 → 1.2.0-alpha.1

[tool.releasio.branches.release]
match = "release/*"  # Wildcard pattern
prerelease = true
prerelease_token = "rc"  # 1.2.0 → 1.2.0-rc.1
```

When releasing from the `beta` branch, releasio will automatically detect it and append the pre-release token:

```bash
$ git checkout beta
$ releasio update --execute
Auto-detected pre-release channel beta from branch beta
Updating from 1.1.0 to 1.2.0-beta.1
```

### Custom Changelog Templates

Customize how your changelog entries are formatted with section headers, author attribution, and custom templates.

```toml
[tool.releasio.changelog]
enabled = true
path = "CHANGELOG.md"
show_authors = true       # Include author name: "- Add feature (@username)"
show_commit_hash = true   # Include commit hash: "- Add feature (abc1234)"

# Custom template with all available variables
commit_template = "{description} by @{author} ({hash})"

# Customize section headers
[tool.releasio.changelog.section_headers]
feat = "🚀 New Features"
fix = "🐛 Bug Fixes"
perf = "⚡ Performance"
docs = "📚 Documentation"
refactor = "♻️ Refactoring"
breaking = "💥 Breaking Changes"
```

Available template variables:

- `{description}` - Commit description
- `{scope}` - Commit scope (if present)
- `{author}` - Author name
- `{hash}` - Short commit hash
- `{body}` - Full commit body
- `{type}` - Commit type (feat, fix, etc.)

### Custom Commit Parsers

Support non-conventional commit formats like Gitmoji, Angular, or your own custom patterns. Custom parsers are tried first, with conventional commits as a fallback.

```toml
[tool.releasio.commits]
# Custom parsers for Gitmoji commits
commit_parsers = [
    { pattern = "^:sparkles:\\s*(?P<description>.+)$", type = "feat", group = "✨ Features" },
    { pattern = "^:bug:\\s*(?P<description>.+)$", type = "fix", group = "🐛 Bug Fixes" },
    { pattern = "^:boom:\\s*(?P<description>.+)$", type = "breaking", group = "💥 Breaking Changes", breaking_indicator = ":boom:" },
    { pattern = "^:recycle:\\s*(?P<description>.+)$", type = "refactor", group = "♻️ Refactoring" },
    { pattern = "^:memo:\\s*(?P<description>.+)$", type = "docs", group = "📚 Documentation" },
]

# Fall back to conventional commits if no custom parser matches (default: true)
use_conventional_fallback = true
```

Each parser supports:

- `pattern` - Regex with named capture groups (must include `description` group)
- `type` - Commit type for version bumping (e.g., "feat", "fix")
- `group` - Changelog section header
- `scope_group` - Optional: name of regex group containing scope
- `description_group` - Group name for description (default: "description")
- `breaking_indicator` - If set, marks commits as breaking changes

### Native Changelog Fallback

releasio can generate changelogs natively when git-cliff is not installed. This uses your `section_headers` and `commit_template` settings.

```toml
[tool.releasio.changelog]
# Generate changelog natively if git-cliff unavailable (default: true)
native_fallback = true

# Auto-generate git-cliff config from releasio settings
generate_cliff_config = false
```

### Build Command Hook

Customize the build command used during release. By default, releasio uses `uv build`, but you can specify any build command.

```toml
[tool.releasio.hooks]
# Custom build command (replaces default uv build)
build = "python -m build --sdist --wheel"

# Or use template variables
build = "hatch build -t wheel && echo 'Built version {version}'"
```

Available template variables:

- `{version}` - Version being built
- `{project_path}` - Path to the project directory

### Version File Management

By default, releasio updates the version in `pyproject.toml`. You can also update version strings in other files.

#### Explicit Version Files

Specify additional files that contain version strings:

```toml
[tool.releasio.version]
version_files = [
    "src/mypackage/__init__.py",      # __version__ = "1.0.0"
    "src/mypackage/__version__.py",   # __version__ = "1.0.0"
    "VERSION",                         # Plain text file with just the version
]
```

Supported patterns in Python files:

- `__version__ = "1.0.0"`
- `VERSION = "1.0.0"`
- `version = "1.0.0"`

#### Auto-Detection

Enable automatic detection of version files in your package:

```toml
[tool.releasio.version]
auto_detect_version_files = true
```

When enabled, releasio automatically finds and updates version strings in:

- `src/<package>/__init__.py`
- `src/<package>/__version__.py`
- `src/<package>/_version.py`
- `<package>/__init__.py` (flat layout)
- `VERSION` (plain text file in project root)

### Lock File Updates

releasio automatically updates your lock file after bumping the version to keep dependencies in sync. This works with multiple package managers:

| Package Manager | Lock File      | Command                   |
| --------------- | -------------- | ------------------------- |
| **uv**          | `uv.lock`      | `uv lock`                 |
| **Poetry**      | `poetry.lock`  | `poetry lock --no-update` |
| **PDM**         | `pdm.lock`     | `pdm lock --no-update`    |
| **Hatch**       | *none*         | *skipped*                 |

The package manager is auto-detected based on:

1. Existing lock files (e.g., `uv.lock`, `poetry.lock`)
2. Tool configuration in `pyproject.toml` (e.g., `[tool.poetry]`)

To disable lock file updates:

```toml
[tool.releasio.version]
update_lock_file = false
```

<details>
<summary><strong>Full Configuration Reference</strong></summary>

```toml
[tool.releasio]
default_branch = "main"          # Branch for releases
allow_dirty = false              # Allow releases from dirty working directory

[tool.releasio.version]
tag_prefix = "v"                 # Git tag prefix (v1.0.0)
initial_version = "0.1.0"        # Version for first release
version_files = []               # Additional files to update version in
auto_detect_version_files = false  # Auto-detect __init__.py, __version__.py, etc.
update_lock_file = true          # Update uv.lock/poetry.lock/pdm.lock after bump

[tool.releasio.commits]
types_minor = ["feat"]           # Commit types triggering minor bump
types_patch = ["fix", "perf"]    # Commit types triggering patch bump
breaking_pattern = "BREAKING[ -]CHANGE:"
skip_release_patterns = ["[skip release]", "[release skip]"]
commit_parsers = []              # Custom parsers for non-conventional commits
use_conventional_fallback = true # Fall back to conventional if no parser matches

[tool.releasio.changelog]
enabled = true
path = "CHANGELOG.md"
header = ""                      # Custom header text for changelog
use_github_prs = false           # Use PR-based changelog (for squash merges)
show_authors = false             # Include author in changelog entries
show_commit_hash = false         # Include commit hash in changelog entries
show_first_time_contributors = false  # Highlight first-time contributors
first_contributor_badge = "🎉"   # Badge for first-time contributors
include_dependency_updates = false    # Include dependency changes section
commit_template = ""             # Custom template: "{description} by @{author}"
native_fallback = true           # Generate natively if git-cliff unavailable
generate_cliff_config = false    # Auto-generate git-cliff config

[tool.releasio.changelog.section_headers]
feat = "✨ Features"
fix = "🐛 Bug Fixes"
breaking = "⚠️ Breaking Changes"

[tool.releasio.github]
owner = ""                       # Auto-detected from git remote
repo = ""                        # Auto-detected from git remote
api_url = "https://api.github.com"
release_pr_branch = "releasio/release"
release_pr_labels = ["release"]
draft_releases = false

[tool.releasio.publish]
enabled = true
registry = "https://upload.pypi.org/legacy/"
tool = "uv"                      # Options: "uv", "poetry", "pdm", "twine"
trusted_publishing = true

[tool.releasio.hooks]
pre_bump = []                    # Commands before version bump
post_bump = []                   # Commands after version bump
pre_release = []                 # Commands before release
post_release = []                # Commands after release
build = ""                       # Custom build command (replaces uv build)

[tool.releasio.security]
enabled = false                  # Enable security commit detection
auto_create_advisory = false     # Create GitHub Security Advisory
security_patterns = [            # Patterns to detect security commits
    "fix\\(security\\):",
    "security:",
    "CVE-\\d{4}-\\d+",
]

# Multi-branch release channels (optional)
[tool.releasio.branches.main]
match = "main"
prerelease = false

[tool.releasio.branches.beta]
match = "beta"
prerelease = true
prerelease_token = "beta"
```

</details>

## Advanced Features

### Release Asset Uploads

Upload files to GitHub releases automatically (e.g., binaries, documentation archives, wheel files).

```toml
[tool.releasio.github]
release_assets = [
    "dist/*.whl",           # Upload all wheel files
    "dist/*.tar.gz",        # Upload source distributions
    "docs/build/html.zip",  # Upload documentation archive
]
```

Supports glob patterns for flexible file matching. Assets are uploaded after the GitHub release is created. If an upload fails, a warning is shown but the release continues.

**Example use cases:**

- Upload compiled binaries for different platforms
- Attach documentation archives
- Include license files or additional resources
- Publish distribution files directly to GitHub releases

### Package Validation

Validate distribution files before publishing to PyPI using `twine check`.

```toml
[tool.releasio.publish]
validate_before_publish = true  # Run twine check before publishing
check_existing_version = true   # Check if version already exists on PyPI
```

**What it does:**

- `validate_before_publish`: Runs `twine check` on built packages to ensure metadata is valid and follows PyPI requirements
- `check_existing_version`: Queries PyPI API to verify the version hasn't been published yet, preventing accidental republishing

Falls back to basic checks (file existence, extension validation) if `twine` is not installed.

### First-Time Contributor Recognition

Highlight first-time contributors in changelogs with a customizable badge:

```toml
[tool.releasio.changelog]
show_first_time_contributors = true
first_contributor_badge = "🎉 First contribution!"
```

When enabled, releasio checks the git history to identify authors who are contributing for the first time in this release. Their changelog entries will include the badge.

### Dependency Update Tracking

Automatically detect and include dependency updates in the changelog:

```toml
[tool.releasio.changelog]
include_dependency_updates = true
```

Releasio compares lock files between releases to identify dependency changes. Supports:

- `uv.lock` (uv)
- `poetry.lock` (Poetry)
- `pdm.lock` (PDM)
- `requirements.txt`

Example changelog output:

```markdown
### 📦 Dependencies

- httpx: 0.27.0 → 0.28.0
- Added pydantic 2.5.0
- Removed deprecated-package 1.0.0
```

### Release Hooks

Run custom commands at specific points during the release process:

```toml
[tool.releasio.hooks]
pre_release = ["npm run lint", "pytest"]
post_release = ["./scripts/notify-slack.sh"]
```

Hooks support template variables:

- `{version}` - The version being released
- `{tag}` - The git tag (e.g., `v1.2.0`)
- `{project_path}` - Path to the project directory

Example with templates:

```toml
[tool.releasio.hooks]
pre_release = ["echo 'Releasing {version}'"]
post_release = ["curl -X POST https://hooks.slack.com/... -d 'Released {tag}'"]
```

If any pre-release hook fails, the release is aborted. Post-release hooks run after the release completes (warnings shown on failure but release continues).

### Security Advisory Integration

Automatically detect security-related commits and optionally create GitHub Security Advisories:

```toml
[tool.releasio.security]
enabled = true
auto_create_advisory = true
security_patterns = [
    "fix\\(security\\):",
    "security:",
    "CVE-\\d{4}-\\d+",
]
```

**Detection:** Commits matching any pattern are flagged as security fixes. CVE identifiers are automatically extracted from commit messages.

**Advisory Creation:** When `auto_create_advisory = true` and security commits are detected, releasio creates a GitHub Security Advisory with:

- Summary of security fixes
- CVE IDs (if found in commits)
- Recommendation to upgrade

### Custom Changelog Header

Add a custom header to your changelog:

```toml
[tool.releasio.changelog]
header = "All notable changes to this project will be documented in this file."
```

### Custom Registry URL

Publish to a private PyPI registry or test.pypi.org:

```toml
[tool.releasio.publish]
registry = "https://test.pypi.org/legacy/"
```

### Trusted Publishing Control

Control OIDC trusted publishing behavior:

```toml
[tool.releasio.publish]
trusted_publishing = true   # Default: auto-detect OIDC environment
```

When enabled:

- In GitHub Actions with OIDC: Uses `--trusted-publishing=always`
- Outside GitHub Actions: Falls back to `--trusted-publishing=automatic`

Set to `false` to always require a PyPI token.

## Requirements

- Python 3.11+
- Git repository with conventional commits
- `pyproject.toml` with `[project]` section

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

```bash
git clone https://github.com/mikeleppane/release-py.git
cd release-py
uv sync --all-extras
uv run pytest
```

## License

MIT License - see [LICENSE](LICENSE) for details.

---

<p align="center">
  <a href="https://github.com/mikeleppane/release-py/issues">Report Bug</a> · <a href="https://github.com/mikeleppane/release-py/issues">Request Feature</a> · <a href="https://github.com/mikeleppane/release-py/discussions">Discussions</a>
</p>
