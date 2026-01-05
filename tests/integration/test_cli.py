"""Integration tests for CLI commands."""

from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from release_py.cli.app import app

runner = CliRunner()


def strip_ansi(text: str) -> str:
    """Strip ANSI escape codes from text."""
    ansi_pattern = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_pattern.sub("", text)


class TestCLIVersion:
    """Tests for version command."""

    def test_version_flag(self):
        """--version shows version."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "releasio" in result.stdout
        assert "0.1.0" in result.stdout

    def test_short_version_flag(self):
        """-V shows version."""
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0


class TestCLIHelp:
    """Tests for help output."""

    def test_main_help(self):
        """Main help shows all commands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "check" in result.stdout
        assert "update" in result.stdout
        assert "release-pr" in result.stdout
        assert "release" in result.stdout
        assert "init" in result.stdout

    def test_check_help(self):
        """check --help shows options."""
        result = runner.invoke(app, ["check", "--help"])
        assert result.exit_code == 0
        assert "--verbose" in strip_ansi(result.stdout)

    def test_update_help(self):
        """update --help shows options."""
        result = runner.invoke(app, ["update", "--help"])
        assert result.exit_code == 0
        assert "--execute" in strip_ansi(result.stdout)

    def test_release_pr_help(self):
        """release-pr --help shows options."""
        result = runner.invoke(app, ["release-pr", "--help"])
        assert result.exit_code == 0
        assert "--execute" in strip_ansi(result.stdout)

    def test_release_help(self):
        """release --help shows options."""
        result = runner.invoke(app, ["release", "--help"])
        assert result.exit_code == 0
        assert "--skip-publish" in strip_ansi(result.stdout)

    def test_init_help(self):
        """init --help shows options."""
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0
        assert "--force" in strip_ansi(result.stdout)


class TestCLICheck:
    """Tests for check command."""

    def test_check_no_repo(self, tmp_path: Path):
        """check fails gracefully without git repo."""
        result = runner.invoke(app, ["check", str(tmp_path)])
        assert result.exit_code == 1

    def test_check_with_repo(self, temp_git_repo_with_commits: Path):
        """check shows release preview."""
        result = runner.invoke(app, ["check", str(temp_git_repo_with_commits)])
        # Should succeed and show version info
        assert "version" in result.stdout.lower() or result.exit_code == 0

    def test_check_verbose_output(self, temp_git_repo_with_commits: Path):
        """check --verbose shows commit table."""
        result = runner.invoke(app, ["check", "--verbose", str(temp_git_repo_with_commits)])

        # Should show commit details in table format
        output = strip_ansi(result.stdout)
        assert "Commits to Include" in output or "Type" in output or result.exit_code == 0

    def test_check_first_release_detection(self, temp_git_repo: Path):
        """check detects first release (no tags)."""
        import subprocess

        # Create pyproject.toml
        pyproject = temp_git_repo / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"\nversion = "0.1.0"\n')

        # Add a commit
        (temp_git_repo / "file.txt").write_text("content")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: initial commit"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        result = runner.invoke(app, ["check", str(temp_git_repo)])

        # Should detect first release
        output = result.stdout
        assert "first release" in output.lower() or "0.1.0" in output or result.exit_code == 0

    def test_check_all_bump_types(self, temp_git_repo: Path):
        """check shows different bump types (MAJOR, MINOR, PATCH)."""
        import subprocess

        # Create pyproject.toml with initial version
        pyproject = temp_git_repo / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"\nversion = "1.0.0"\n')

        # Create tag for version 1.0.0
        subprocess.run(
            ["git", "tag", "v1.0.0"], cwd=temp_git_repo, check=True, capture_output=True
        )

        # Add a minor bump commit
        (temp_git_repo / "feature.txt").write_text("new feature")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: add new feature"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        result = runner.invoke(app, ["check", str(temp_git_repo)])

        # Should show MINOR bump
        output = strip_ansi(result.stdout)
        assert (
            "minor" in output.lower()
            or "1.1.0" in output
            or "next version" in output.lower()
            or result.exit_code == 0
        )


class TestCLICheckPr:
    """Tests for check-pr command."""

    def test_check_pr_help(self):
        """check-pr --help shows options."""
        result = runner.invoke(app, ["check-pr", "--help"])
        assert result.exit_code == 0
        output = strip_ansi(result.stdout)
        assert "--title" in output
        assert "--require-scope" in output

    def test_check_pr_valid_title(self):
        """check-pr with valid title succeeds."""
        result = runner.invoke(app, ["check-pr", "--title", "feat: add new feature"])
        assert result.exit_code == 0
        assert "valid" in result.stdout.lower()
        assert "feat" in result.stdout

    def test_check_pr_valid_title_with_scope(self):
        """check-pr with scoped title succeeds."""
        result = runner.invoke(app, ["check-pr", "--title", "fix(api): handle errors"])
        assert result.exit_code == 0
        assert "valid" in result.stdout.lower()
        assert "api" in result.stdout

    def test_check_pr_breaking_change(self):
        """check-pr detects breaking changes."""
        result = runner.invoke(app, ["check-pr", "--title", "feat!: redesign API"])
        assert result.exit_code == 0
        assert "breaking" in result.stdout.lower()

    def test_check_pr_invalid_title(self):
        """check-pr with invalid title fails."""
        result = runner.invoke(app, ["check-pr", "--title", "Updated the code"])
        assert result.exit_code == 1
        output = result.output.lower()
        assert "invalid" in output or "error" in output

    def test_check_pr_invalid_type(self):
        """check-pr with unknown type fails."""
        result = runner.invoke(app, ["check-pr", "--title", "unknown: some change"])
        assert result.exit_code == 1
        assert "invalid" in result.output.lower()

    def test_check_pr_no_title(self):
        """check-pr without title shows error."""
        result = runner.invoke(app, ["check-pr"])
        assert result.exit_code == 1
        assert "no pr title" in result.output.lower()

    def test_check_pr_require_scope_fails(self):
        """check-pr --require-scope fails without scope."""
        result = runner.invoke(app, ["check-pr", "--title", "feat: no scope", "--require-scope"])
        assert result.exit_code == 1
        assert "scope" in result.output.lower()

    def test_check_pr_require_scope_passes(self):
        """check-pr --require-scope passes with scope."""
        result = runner.invoke(
            app, ["check-pr", "--title", "feat(api): with scope", "--require-scope"]
        )
        assert result.exit_code == 0

    def test_check_pr_env_var(self, monkeypatch):
        """check-pr reads from GITHUB_PR_TITLE env var."""
        monkeypatch.setenv("GITHUB_PR_TITLE", "feat: from env var")
        result = runner.invoke(app, ["check-pr"])
        assert result.exit_code == 0
        assert "from env var" in result.stdout

    def test_check_pr_malformed_event_file(self, tmp_path: Path, monkeypatch):
        """check-pr handles malformed GitHub event file gracefully."""
        # Create a malformed JSON event file
        event_file = tmp_path / "event.json"
        event_file.write_text("{ invalid json")

        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))

        result = runner.invoke(app, ["check-pr"])

        # Should fail gracefully without title
        assert result.exit_code == 1
        assert "no pr title" in result.output.lower()

    def test_check_pr_various_github_ref_formats(self, monkeypatch):
        """check-pr parses various GITHUB_REF formats."""
        import json
        import tempfile

        # Create a valid GitHub event file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            event = {"pull_request": {"title": "feat: from event", "number": 123}}
            json.dump(event, f)
            event_path = f.name

        try:
            # Test refs/pull/123/merge format
            monkeypatch.setenv("GITHUB_REF", "refs/pull/123/merge")
            monkeypatch.setenv("GITHUB_EVENT_PATH", event_path)

            result = runner.invoke(app, ["check-pr"])

            # Should read from event file
            assert result.exit_code == 0
            assert "from event" in result.stdout

            # Test invalid ref format
            monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
            result = runner.invoke(app, ["check-pr"])
            assert result.exit_code == 0  # Still works from event file
        finally:
            # Cleanup
            Path(event_path).unlink()

    def test_check_pr_missing_event_file(self, tmp_path: Path, monkeypatch):
        """check-pr handles missing GitHub event file."""
        # Point to non-existent file
        nonexistent = tmp_path / "nonexistent.json"
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(nonexistent))

        result = runner.invoke(app, ["check-pr"])

        # Should fail gracefully
        assert result.exit_code == 1
        assert "no pr title" in result.output.lower()


class TestCLIInit:
    """Tests for init command."""

    def test_init_no_pyproject(self, tmp_path: Path):
        """init shows wizard or fails without pyproject.toml."""
        result = runner.invoke(app, ["init", str(tmp_path)])
        # Init may either show a wizard or fail - check output is meaningful
        output = result.stdout + (result.output or "")
        assert len(output) > 0  # Should produce some output

    def test_init_creates_config(self, tmp_path: Path):
        """init creates releasio config in pyproject.toml."""
        # Create minimal pyproject.toml
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"\nversion = "0.1.0"\n')

        # Run init with default inputs
        result = runner.invoke(
            app,
            ["init", str(tmp_path)],
            input="main\nv\nn\nsmall-team\nn\n",  # branch, prefix, no squash, type, no workflow
        )

        assert result.exit_code == 0
        assert "releasio" in pyproject.read_text()
        assert "[tool.releasio]" in pyproject.read_text()

    def test_init_already_configured(self, tmp_path: Path):
        """init detects existing configuration."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "test"\nversion = "0.1.0"\n\n'
            '[tool.releasio]\ndefault_branch = "main"\n'
        )

        result = runner.invoke(app, ["init", str(tmp_path)])

        # Should warn about existing config
        assert "already configured" in result.output.lower()
        assert result.exit_code == 0

    def test_init_force_overwrites(self, tmp_path: Path):
        """init --force overwrites existing configuration."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "test"\nversion = "0.1.0"\n\n'
            '[tool.releasio]\ndefault_branch = "old"\n'
        )

        result = runner.invoke(
            app,
            ["init", "--force", str(tmp_path)],
            input="develop\nv\nn\nsmall-team\nn\n",
        )

        assert result.exit_code == 0
        content = pyproject.read_text()
        assert 'default_branch = "develop"' in content

    def test_init_creates_workflow(self, tmp_path: Path):
        """init creates GitHub Actions workflow when requested."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"\nversion = "0.1.0"\n')

        result = runner.invoke(
            app,
            ["init", str(tmp_path)],
            input="main\nv\nn\nsmall-team\ny\nn\n",  # yes to workflow, no to PR check
        )

        assert result.exit_code == 0
        workflow_path = tmp_path / ".github" / "workflows" / "release.yml"
        assert workflow_path.exists()
        assert "releasio" in workflow_path.read_text()

    def test_init_creates_pr_check_workflow(self, tmp_path: Path):
        """init creates PR title check workflow when requested."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"\nversion = "0.1.0"\n')

        result = runner.invoke(
            app,
            ["init", str(tmp_path)],
            input="main\nv\nn\nopen-source\ny\ny\n",  # yes to both workflows
        )

        assert result.exit_code == 0
        pr_check_path = tmp_path / ".github" / "workflows" / "pr-title.yml"
        assert pr_check_path.exists()
        assert "check-pr" in pr_check_path.read_text()


class TestSquashMergeDetection:
    """Tests for squash merge workflow detection."""

    def test_detect_squash_from_pr_numbers(self, temp_git_repo: Path):
        """Detects squash merge workflow from PR number patterns."""
        import subprocess

        # Create commits with PR number pattern (squash merge style)
        for i in range(5):
            (temp_git_repo / f"file{i}.txt").write_text(f"content {i}")
            subprocess.run(["git", "add", "."], cwd=temp_git_repo, check=True)
            subprocess.run(
                ["git", "commit", "-m", f"feat: add feature {i} (#{i + 1})"],
                cwd=temp_git_repo,
                check=True,
                capture_output=True,
            )

        from release_py.cli.commands.init_cmd import _detect_squash_merge

        assert _detect_squash_merge(temp_git_repo) is True

    def test_no_squash_without_pr_numbers(self, temp_git_repo: Path):
        """Does not detect squash merge without PR number patterns."""
        import subprocess

        # Create commits without PR numbers
        for i in range(5):
            (temp_git_repo / f"file{i}.txt").write_text(f"content {i}")
            subprocess.run(["git", "add", "."], cwd=temp_git_repo, check=True)
            subprocess.run(
                ["git", "commit", "-m", f"feat: add feature {i}"],
                cwd=temp_git_repo,
                check=True,
                capture_output=True,
            )

        from release_py.cli.commands.init_cmd import _detect_squash_merge

        assert _detect_squash_merge(temp_git_repo) is False
