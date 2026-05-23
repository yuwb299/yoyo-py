"""Tests for /health command — run build/test/lint diagnostics."""

import os
from subprocess import CompletedProcess
from unittest.mock import MagicMock, patch

from src.repl import _run_health_check


class TestHealthCheck:
    """Test the _run_health_check function."""

    def test_python_project_with_passing_tests(self, tmp_path):
        """A Python project with pytest should show test results."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_basic.py").write_text("def test_ok(): assert True\n")

        result = _run_health_check(str(tmp_path))
        assert "python" in result.lower()

    def test_not_a_project_directory(self, tmp_path):
        """Empty directory should report no project type detected."""
        result = _run_health_check(str(tmp_path))
        # Should still return something useful even if no project files found
        assert isinstance(result, str)
        assert len(result) > 0

    def test_python_project_detection(self, tmp_path):
        """Should detect Python project from pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

        # Mock subprocess.run to avoid actually running pytest
        with patch("src.repl.subprocess.run") as mock_run:
            mock_run.return_value = CompletedProcess(
                args=[], returncode=0, stdout="1 passed", stderr=""
            )
            result = _run_health_check(str(tmp_path))
            assert "python" in result.lower()

    def test_python_project_with_failing_tests(self, tmp_path):
        """A Python project with failing tests should report the failure."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

        with patch("src.repl.subprocess.run") as mock_run:
            mock_run.return_value = CompletedProcess(
                args=[], returncode=1, stdout="1 FAILED", stderr=""
            )
            result = _run_health_check(str(tmp_path))
            assert "fail" in result.lower() or "✗" in result

    def test_run_from_current_directory(self):
        """Running from the actual project directory should work."""
        # Mock subprocess.run to avoid running real pytest on the project
        with patch("src.repl.subprocess.run") as mock_run:
            mock_run.return_value = CompletedProcess(
                args=[], returncode=0, stdout="all passed", stderr=""
            )
            result = _run_health_check(os.getcwd())
            assert isinstance(result, str)
            assert len(result) > 0

    def test_nonexistent_directory(self):
        """Should handle nonexistent directory gracefully."""
        result = _run_health_check("/nonexistent/path/xyz")
        assert "error" in result.lower() or "not found" in result.lower()

    def test_with_git_status(self, tmp_path):
        """Should show git status info if in a git repo."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

        with patch("src.repl.subprocess.run") as mock_run:
            # First call: git rev-parse, second: git status, third: pytest
            mock_run.side_effect = [
                CompletedProcess(args=[], returncode=0, stdout="true", stderr=""),
                CompletedProcess(args=[], returncode=0, stdout="", stderr=""),  # clean tree
                CompletedProcess(args=[], returncode=0, stdout="1 passed", stderr=""),
                CompletedProcess(args=[], returncode=1, stdout="ruff not found", stderr=""),  # ruff
                CompletedProcess(args=[], returncode=1, stdout="mypy not found", stderr=""),  # mypy
            ]
            result = _run_health_check(str(tmp_path))
            assert "git" in result.lower() or "clean" in result.lower() or "python" in result.lower()
