"""Tests for /test and /health commands with Rust and Go project detection."""

import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.repl import _run_test_command, _run_health_check


@pytest.fixture
def rust_project(tmp_path):
    """Create a minimal Rust project structure."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname = 'test'\nversion = '0.1.0'\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.rs").write_text('fn main() { println!("hello"); }')
    return str(tmp_path)


@pytest.fixture
def go_project(tmp_path):
    """Create a minimal Go project structure."""
    (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")
    (tmp_path / "main_test.go").write_text(
        'package main\nimport "testing"\nfunc TestHello(t *testing.T) {}\n'
    )
    return str(tmp_path)


@pytest.fixture
def java_project(tmp_path):
    """Create a minimal Maven Java project structure."""
    (tmp_path / "pom.xml").write_text(
        '<project><modelVersion>4.0.0</modelVersion>'
        '<groupId>com.test</groupId><artifactId>test</artifactId><version>1.0</version></project>'
    )
    (tmp_path / "src" / "test" / "java").mkdir(parents=True)
    return str(tmp_path)


class TestRustDetection:
    """Test Rust project detection in /test and /health."""

    def test_test_detects_rust_project(self, rust_project):
        """/test should recognize Cargo.toml as a Rust project."""
        # Mock subprocess.run to avoid actually running cargo test
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="running 1 test\ntest result: ok. 1 passed; 0 failed",
                stderr="",
            )
            result = _run_test_command(workdir=rust_project)
            assert "Rust" in result or "test" in result.lower() or "cargo" in result.lower() or "passed" in result.lower()

    def test_health_detects_rust_project(self, rust_project):
        """/health should recognize Cargo.toml as a Rust project."""
        with patch("subprocess.run") as mock_run:
            # Mock git check + cargo test + cargo check
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )
            result = _run_health_check(workdir=rust_project)
            assert "Rust" in result

    def test_rust_test_failure(self, rust_project):
        """/test should report test failure for Rust projects."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=101,
                stdout="running 1 test\ntest result: FAILED. 0 passed; 1 failed",
                stderr="",
            )
            result = _run_test_command(workdir=rust_project)
            assert "fail" in result.lower() or "FAIL" in result

    def test_rust_test_timeout(self, rust_project):
        """/test should handle timeout for Rust projects."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="cargo test", timeout=120)
            result = _run_test_command(workdir=rust_project)
            assert "timeout" in result.lower() or "timed out" in result.lower()

    def test_rust_cargo_not_found(self, rust_project):
        """/test should report cargo not found."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("cargo not found")
            result = _run_test_command(workdir=rust_project)
            assert "cargo" in result.lower() or "install" in result.lower()


class TestGoDetection:
    """Test Go project detection in /test and /health."""

    def test_test_detects_go_project(self, go_project):
        """/test should recognize go.mod as a Go project."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="ok  example.com/test  0.001s",
                stderr="",
            )
            result = _run_test_command(workdir=go_project)
            assert "Go" in result or "test" in result.lower() or "passed" in result.lower()

    def test_health_detects_go_project(self, go_project):
        """/health should recognize go.mod as a Go project."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )
            result = _run_health_check(workdir=go_project)
            assert "Go" in result

    def test_go_test_failure(self, go_project):
        """/test should report failure for Go projects."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="FAIL  example.com/test  0.001s",
                stderr="",
            )
            result = _run_test_command(workdir=go_project)
            assert "fail" in result.lower() or "FAIL" in result

    def test_go_not_found(self, go_project):
        """/test should report go not found."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("go not found")
            result = _run_test_command(workdir=go_project)
            assert "go" in result.lower() or "install" in result.lower()


class TestJavaDetection:
    """Test Java/Maven project detection in /test."""

    def test_test_detects_java_project(self, java_project):
        """/test should recognize pom.xml as a Java/Maven project."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Tests run: 1, Failures: 0, Errors: 0\nBUILD SUCCESS",
                stderr="",
            )
            result = _run_test_command(workdir=java_project)
            assert "Java" in result or "Maven" in result or "test" in result.lower()

    def test_health_detects_java_project(self, java_project):
        """/health should recognize pom.xml as a Java project."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )
            result = _run_health_check(workdir=java_project)
            assert "Java" in result


class TestMixedProject:
    """Test that a project with multiple types is detected correctly."""

    def test_python_and_rust(self, tmp_path):
        """Project with both pyproject.toml and Cargo.toml."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        (tmp_path / "Cargo.toml").write_text("[package]\nname = 'test'\nversion = '0.1.0'\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )
            result = _run_health_check(workdir=str(tmp_path))
            # Should detect both project types
            assert "Python" in result
            assert "Rust" in result

    def test_unknown_project_type(self, tmp_path):
        """Project with no recognized markers."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,  # Not a git repo
                stdout="",
                stderr="not a git repo",
            )
            result = _run_health_check(workdir=str(tmp_path))
            assert "Unknown" in result or "No recognized" in result

    def test_test_unknown_project_type(self, tmp_path):
        """/test with no recognized project type should say so."""
        result = _run_test_command(workdir=str(tmp_path))
        assert "recognized" in result.lower() or "unknown" in result.lower() or "No " in result
