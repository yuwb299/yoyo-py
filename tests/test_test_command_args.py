"""Tests for /test command with arguments support.

Verifies that /test accepts arguments to run specific test files,
test patterns, or pass extra flags through to the test runner.
"""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.repl import _run_test_command


def _make_path_exists(python=True, node=False, rust=False, go=False, java=False):
    """Create a mock for Path.exists that simulates a specific project type.

    Always returns True for directory checks (no file extension),
    and returns True for marker files that are configured.
    """
    markers = set()
    if python:
        markers.add("pyproject.toml")
    if node:
        markers.add("package.json")
    if rust:
        markers.add("Cargo.toml")
    if go:
        markers.add("go.mod")
    if java:
        markers.add("pom.xml")

    def exists(self):
        name = str(self).split("/")[-1]
        # Root directory (no dot in name) always exists
        if "." not in name:
            return True
        # Marker files
        return name in markers

    return exists


def _is_dir_always_true(self):
    return True


@pytest.fixture
def mock_python_project():
    """Patch Path for a Python project with subprocess.run mocked separately."""
    with patch("os.getcwd", return_value="/project"), \
         patch.object(Path, "exists", _make_path_exists()), \
         patch.object(Path, "is_dir", _is_dir_always_true):
        yield


@pytest.fixture
def mock_node_project():
    with patch("os.getcwd", return_value="/project"), \
         patch.object(Path, "exists", _make_path_exists(python=False, node=True)), \
         patch.object(Path, "is_dir", _is_dir_always_true):
        yield


@pytest.fixture
def mock_rust_project():
    with patch("os.getcwd", return_value="/project"), \
         patch.object(Path, "exists", _make_path_exists(python=False, rust=True)), \
         patch.object(Path, "is_dir", _is_dir_always_true):
        yield


@pytest.fixture
def mock_go_project():
    with patch("os.getcwd", return_value="/project"), \
         patch.object(Path, "exists", _make_path_exists(python=False, go=True)), \
         patch.object(Path, "is_dir", _is_dir_always_true):
        yield


class TestTestCommandWithArgsPython:
    """Test /test with argument passthrough for Python projects."""

    @patch("subprocess.run")
    def test_with_specific_file(self, mock_run, mock_python_project):
        """'/test tests/test_foo.py' should pass the file to pytest."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="3 passed in 0.5s", stderr="",
        )
        result = _run_test_command(args="tests/test_foo.py")

        cmd = mock_run.call_args[0][0]
        assert "tests/test_foo.py" in cmd

    @patch("subprocess.run")
    def test_with_pytest_flags(self, mock_run, mock_python_project):
        """'/test -k test_something' should pass flags through to pytest."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="1 passed in 0.1s", stderr="",
        )
        result = _run_test_command(args="-k test_something")

        cmd = mock_run.call_args[0][0]
        assert "-k" in cmd
        assert "test_something" in cmd

    @patch("subprocess.run")
    def test_with_multiple_args(self, mock_run, mock_python_project):
        """'/test tests/test_a.py tests/test_b.py -v' should pass all through."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="5 passed in 0.3s", stderr="",
        )
        result = _run_test_command(args="tests/test_a.py tests/test_b.py -v")

        cmd = mock_run.call_args[0][0]
        assert "tests/test_a.py" in cmd
        assert "tests/test_b.py" in cmd
        assert "-v" in cmd

    @patch("subprocess.run")
    def test_no_args_runs_full_suite(self, mock_run, mock_python_project):
        """'/test' with no args should run full test suite (current behavior)."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="100 passed in 5.0s", stderr="",
        )
        result = _run_test_command(args="")

        cmd = mock_run.call_args[0][0]
        assert "python" in cmd[0]
        assert "pytest" in cmd
        test_specific = [a for a in cmd if a.endswith(".py") and a != "pytest"]
        assert len(test_specific) == 0

    @patch("subprocess.run")
    def test_with_exitfirst_flag(self, mock_run, mock_python_project):
        """'/test -x' should pass -x (exit first) to pytest."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="1 failed in 0.2s", stderr="",
        )
        result = _run_test_command(args="-x")

        cmd = mock_run.call_args[0][0]
        assert "-x" in cmd

    @patch("subprocess.run")
    def test_failed_shows_failure(self, mock_run, mock_python_project):
        """'/test tests/test_foo.py' shows failure output."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="FAILED tests/test_foo.py::test_bar - AssertionError",
            stderr="",
        )
        result = _run_test_command(args="tests/test_foo.py")
        assert "fail" in result.lower()

    @patch("subprocess.run")
    def test_passed_shows_success(self, mock_run, mock_python_project):
        """'/test tests/test_foo.py' shows pass output."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="3 passed in 0.5s", stderr="",
        )
        result = _run_test_command(args="tests/test_foo.py")
        assert "pass" in result.lower()

    @patch("subprocess.run")
    def test_backward_compat_no_args_param(self, mock_run, mock_python_project):
        """Calling _run_test_command() with no args parameter still works."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="50 passed in 2.0s", stderr="",
        )
        result = _run_test_command()
        assert "pass" in result.lower()

    @patch("subprocess.run")
    def test_with_last_failed_flag(self, mock_run, mock_python_project):
        """'/test --lf' should pass --lf (last failed) to pytest."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="1 passed in 0.1s", stderr="",
        )
        result = _run_test_command(args="--lf")

        cmd = mock_run.call_args[0][0]
        assert "--lf" in cmd


class TestTestCommandWithArgsNode:
    """Test /test with argument passthrough for Node.js projects."""

    @patch("subprocess.run")
    def test_node_with_args(self, mock_run, mock_node_project):
        """'/test --grep pattern' should pass args after -- to npm."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Tests: 2 passed", stderr="",
        )
        result = _run_test_command(args="--grep pattern")

        cmd = mock_run.call_args[0][0]
        assert cmd == ["npm", "test", "--", "--grep", "pattern"]

    @patch("subprocess.run")
    def test_node_without_args(self, mock_run, mock_node_project):
        """'/test' for Node runs plain npm test."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="All tests passed", stderr="",
        )
        result = _run_test_command(args="")

        cmd = mock_run.call_args[0][0]
        assert cmd == ["npm", "test"]


class TestTestCommandWithArgsRust:
    """Test /test with argument passthrough for Rust projects."""

    @patch("subprocess.run")
    def test_rust_with_test_filter(self, mock_run, mock_rust_project):
        """'/test test_foo' for Rust passes filter to cargo test."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="test result: ok", stderr="",
        )
        result = _run_test_command(args="test_foo")

        cmd = mock_run.call_args[0][0]
        assert "cargo" in cmd
        assert "test_foo" in cmd

    @patch("subprocess.run")
    def test_rust_without_args(self, mock_run, mock_rust_project):
        """'/test' for Rust runs plain cargo test."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="test result: ok", stderr="",
        )
        result = _run_test_command(args="")

        cmd = mock_run.call_args[0][0]
        assert cmd == ["cargo", "test", "--quiet"]


class TestTestCommandWithArgsGo:
    """Test /test with argument passthrough for Go projects."""

    @patch("subprocess.run")
    def test_go_with_package(self, mock_run, mock_go_project):
        """'/test ./pkg/...' for Go passes package to go test."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="ok  pkg  0.5s", stderr="",
        )
        result = _run_test_command(args="./pkg/...")

        cmd = mock_run.call_args[0][0]
        assert cmd == ["go", "test", "./pkg/..."]

    @patch("subprocess.run")
    def test_go_without_args(self, mock_run, mock_go_project):
        """'/test' for Go defaults to ./..."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="ok  all packages", stderr="",
        )
        result = _run_test_command(args="")

        cmd = mock_run.call_args[0][0]
        assert cmd == ["go", "test", "./..."]


class TestTestCommandArgsWiring:
    """Test the REPL wiring — /test <args> passes through correctly."""

    def test_extracts_args_from_line(self):
        """'/test tests/foo.py -v' extracts 'tests/foo.py -v'."""
        line = "/test tests/test_foo.py -v"
        args = line[5:].strip()
        assert args == "tests/test_foo.py -v"

    def test_no_args_from_line(self):
        """'/test' extracts empty string."""
        line = "/test"
        args = line[5:].strip()
        assert args == ""
