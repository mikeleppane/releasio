# Contributing to releasio

Thank you for your interest in contributing to releasio! This document provides
guidelines and instructions to help you contribute effectively.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Development Workflow](#development-workflow)
- [Code Style](#code-style)
- [Testing](#testing)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)
- [Release Process](#release-process)
- [Getting Help](#getting-help)

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
By participating, you are expected to uphold this code. Please report unacceptable
behavior to the project maintainers.

## Getting Started

### Finding Something to Work On

- Check the [issue tracker](https://github.com/mikeleppane/release-py/issues) for
  open issues
- Look for issues labeled [`good first issue`](https://github.com/mikeleppane/release-py/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
  if you're new to the project
- Issues labeled [`help wanted`](https://github.com/mikeleppane/release-py/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22)
  are great opportunities to contribute

### Before You Start

1. **Check existing issues** - Someone might already be working on your idea
2. **Open an issue first** - For significant changes, discuss your approach before
   investing time in implementation
3. **Fork the repository** - Create your own fork to work on

## Development Setup

### Prerequisites

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Git

### Setting Up Your Environment

1. **Clone your fork:**

   ```bash
   git clone https://github.com/YOUR_USERNAME/release-py.git
   cd release-py
   ```

2. **Install dependencies:**

   ```bash
   # Using uv (recommended)
   uv sync --all-extras

   # Or using pip
   pip install -e ".[dev]"
   ```

3. **Install pre-commit hooks:**

   ```bash
   # Using uv
   uv run pre-commit install --install-hooks

   # Or directly
   pre-commit install --install-hooks
   ```

4. **Verify your setup:**

   ```bash
   # Run tests
   uv run pytest

   # Run linting
   uv run ruff check src/ tests/

   # Run type checking
   uv run mypy src/
   ```

## Development Workflow

### Creating a Branch

Create a descriptive branch name following this pattern:

```bash
git checkout -b <type>/<short-description>
```

Examples:

- `feat/add-monorepo-support`
- `fix/changelog-parsing-error`
- `docs/improve-configuration-guide`

### Making Changes

1. Write your code following the [code style guidelines](#code-style)
2. Add or update tests as needed
3. Update documentation if your changes affect user-facing behavior
4. Run the full test suite before committing

### Running Checks Locally

Before pushing, ensure all checks pass:

```bash
# Run all pre-commit hooks
uv run pre-commit run --all-files

# Run tests with coverage
uv run pytest --cov=src/release_py --cov-report=term-missing

# Run type checking
uv run mypy src/
```

## Code Style

### Python Style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.
The configuration is in `pyproject.toml`.

Key principles:

- **Line length:** 100 characters maximum
- **Imports:** Sorted automatically by Ruff (isort-compatible)
- **Type hints:** Required for all public functions and methods
- **Docstrings:** Use Google-style docstrings for public APIs

### Type Annotations

All code must pass strict mypy type checking:

```python
# Good
def calculate_version(commits: list[Commit], current: Version) -> Version:
    ...

# Bad - missing type annotations
def calculate_version(commits, current):
    ...
```

### Code Organization

- Keep modules focused and single-purpose
- Prefer composition over inheritance
- Write self-documenting code; add comments only when the "why" isn't obvious

## Testing

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/release_py --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_version.py

# Run tests matching a pattern
uv run pytest -k "test_bump"

# Run with verbose output
uv run pytest -v
```

### Writing Tests

- Place tests in the `tests/` directory mirroring the source structure
- Use descriptive test names: `test_<function>_<scenario>_<expected_result>`
- Use pytest fixtures for common setup
- Aim for high coverage, but prioritize meaningful tests over coverage numbers

Example:

```python
def test_calculate_bump_with_breaking_change_returns_major() -> None:
    """Breaking changes should trigger a major version bump."""
    commits = [Commit(message="feat!: redesign API")]
    result = calculate_bump(commits)
    assert result == BumpType.MAJOR
```

### Test Categories

- **Unit tests:** Test individual functions and classes in isolation
- **Integration tests:** Test component interactions
- **End-to-end tests:** Test CLI commands and full workflows

## Commit Messages

This project follows [Conventional Commits](https://www.conventionalcommits.org/).
The pre-commit hook validates commit message format.

### Format

```text
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

### Types

| Type       | Description                                      |
| ---------- | ------------------------------------------------ |
| `feat`     | A new feature                                    |
| `fix`      | A bug fix                                        |
| `docs`     | Documentation changes                            |
| `style`    | Code style changes (formatting, no logic change) |
| `refactor` | Code changes that neither fix bugs nor add features |
| `perf`     | Performance improvements                         |
| `test`     | Adding or updating tests                         |
| `build`    | Build system or dependency changes               |
| `ci`       | CI configuration changes                         |
| `chore`    | Other changes that don't modify src or test      |

### Examples

```bash
# Feature
git commit -m "feat: add support for pre-release versions"

# Bug fix with scope
git commit -m "fix(changelog): handle commits without PR references"

# Breaking change
git commit -m "feat!: redesign configuration schema

BREAKING CHANGE: The [tool.releasio.version] section has been renamed
to [tool.releasio.versioning]."

# Documentation
git commit -m "docs: add monorepo configuration examples"
```

## Pull Request Process

### Before Submitting

1. **Ensure all checks pass:**
   - Linting (`ruff check`)
   - Formatting (`ruff format --check`)
   - Type checking (`mypy`)
   - Tests (`pytest`)

2. **Update documentation** if needed

3. **Write a clear PR description** explaining:
   - What changes you made
   - Why you made them
   - How to test them

### PR Title

PR titles should follow the conventional commit format as they're used for the
changelog:

```text
feat: add monorepo support
fix(cli): correct version display in check command
docs: improve GitHub Actions examples
```

### Review Process

1. A maintainer will review your PR
2. Address any feedback or requested changes
3. Once approved, a maintainer will merge your PR

### After Merge

- Delete your feature branch
- Sync your fork with upstream

## Release Process

Releases are automated using releasio itself! When changes are merged to `main`:

1. The `release-pr` workflow creates/updates a release PR
2. When the release PR is merged, the `release` workflow:
   - Creates a git tag
   - Publishes to PyPI
   - Creates a GitHub release

## Getting Help

- **Questions:** Open a [GitHub Discussion](https://github.com/mikeleppane/release-py/discussions)
  or file an issue with the `question` label
- **Bugs:** File an issue using the [bug report template](https://github.com/mikeleppane/release-py/issues/new?template=bug-report.yml)
- **Features:** File an issue using the [feature request template](https://github.com/mikeleppane/release-py/issues/new?template=feature-request.yml)

---

Thank you for contributing to releasio!
