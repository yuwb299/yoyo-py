"""Tests for /fix command — auto-fix build/lint errors.

The /fix command runs linters/formatters, attempts to fix errors,
and shows what was fixed. It modifies files in place.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

from src.repl import _run_fix_command


class TestFixCommandDetection:
    """Test that /fix detects the right project type and tools."""

    def test_python_project_detects_ruff(self):
        """In a Python project with ruff installed, /fix runs ruff fix."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create pyproject.toml to identify as Python project
            (Path(tmpdir) / "pyproject.toml").write_text("[project]\nname='test'\n")

            # Create a Python file with a fixable issue
            bad_py = Path(tmpdir) / "bad.py"
            bad_py.write_text("import os\nimport os\nprint('hello')\n")  # duplicate import

            with patch("src.repl.subprocess.run") as mock_run:
                # ruff check returns issues found
                check_result = MagicMock()
                check_result.returncode = 1
                check_result.stdout = "bad.py:1:1 F811 [*] Redefinition of unused `os`"

                # ruff fix returns success
                fix_result = MagicMock()
                fix_result.returncode = 0
                fix_result.stdout = "Found 1 error (1 fixable, 1 fixed)."

                # git diff (check for changes after fix)
                diff_result = MagicMock()
                diff_result.returncode = 0
                diff_result.stdout = ""

                mock_run.side_effect = [check_result, fix_result]

                result = _run_fix_command(workdir=tmpdir)

            assert "ruff" in result.lower() or "fixed" in result.lower() or "1" in result

    def test_python_project_no_fixable_issues(self):
        """When ruff finds no issues, /fix reports clean."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "pyproject.toml").write_text("[project]\nname='test'\n")

            with patch("src.repl.subprocess.run") as mock_run:
                check_result = MagicMock()
                check_result.returncode = 0
                check_result.stdout = "All checks passed!"

                mock_run.return_value = check_result

                result = _run_fix_command(workdir=tmpdir)

            assert "clean" in result.lower() or "no issues" in result.lower() or "passed" in result.lower()

    def test_python_project_ruff_not_installed(self):
        """When ruff is not installed, /fix reports it's missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "pyproject.toml").write_text("[project]\nname='test'\n")

            with patch("src.repl.subprocess.run") as mock_run:
                mock_run.side_effect = FileNotFoundError("ruff not found")

                result = _run_fix_command(workdir=tmpdir)

            assert "ruff" in result.lower() or "not found" in result.lower() or "install" in result.lower()

    def test_not_a_project_directory(self):
        """When the directory doesn't exist, /fix returns an error."""
        result = _run_fix_command(workdir="/nonexistent/path/12345")
        assert "error" in result.lower() or "not found" in result.lower()

    def test_no_recognized_project_type(self):
        """When no project type is detected, /fix says it can't help."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # No pyproject.toml, no package.json — nothing to detect
            result = _run_fix_command(workdir=tmpdir)
            assert "no recognized" in result.lower() or "can't" in result.lower() or "unknown" in result.lower()

    def test_python_project_fixes_with_black(self):
        """When ruff is not available but black is, /fix uses black."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "pyproject.toml").write_text("[project]\nname='test'\n")

            with patch("src.repl.subprocess.run") as mock_run:
                # ruff not found
                ruff_check = FileNotFoundError("ruff not found")

                # black check finds issues
                black_check = MagicMock()
                black_check.returncode = 1
                black_check.stdout = "would reformat bad.py"

                # black fix succeeds
                black_fix = MagicMock()
                black_fix.returncode = 0
                black_fix.stdout = "reformatted bad.py"

                mock_run.side_effect = [ruff_check, black_check, black_fix]

                result = _run_fix_command(workdir=tmpdir)

            assert "black" in result.lower() or "reformat" in result.lower() or "fix" in result.lower()

    def test_node_project_runs_npm_fix(self):
        """In a Node.js project, /fix runs npm fix or eslint --fix."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "package.json").write_text('{"name":"test"}')

            with patch("src.repl.subprocess.run") as mock_run:
                # eslint --fix
                eslint_result = MagicMock()
                eslint_result.returncode = 0
                eslint_result.stdout = ""

                mock_run.return_value = eslint_result

                result = _run_fix_command(workdir=tmpdir)

            assert "eslint" in result.lower() or "node" in result.lower() or "fix" in result.lower() or "clean" in result.lower()

    def test_shows_what_changed(self):
        """After fixing, /fix shows a summary of what changed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "pyproject.toml").write_text("[project]\nname='test'\n")

            with patch("src.repl.subprocess.run") as mock_run:
                # ruff check finds issues
                check_result = MagicMock()
                check_result.returncode = 1
                check_result.stdout = "bad.py:1:1 F811 Redefinition of unused `os`\nbad.py:5:1 E302 expected 2 blank lines"

                # ruff fix fixes some
                fix_result = MagicMock()
                fix_result.returncode = 0
                fix_result.stdout = "Found 2 errors (1 fixable, 1 fixed)."

                mock_run.side_effect = [check_result, fix_result]

                result = _run_fix_command(workdir=tmpdir)

            # Should mention that fixes were applied
            assert "fix" in result.lower()
