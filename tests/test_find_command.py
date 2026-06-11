"""Tests for the /find slash command."""

import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest


@pytest.fixture
def find_dir(tmp_path):
    """Create a temp directory with some files for /find testing."""
    (tmp_path / "hello.py").write_text("print('hello')")
    (tmp_path / "hello_test.py").write_text("def test_hello(): pass")
    (tmp_path / "README.md").write_text("# Hello")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.py").write_text("# deep")
    (tmp_path / "sub" / "deep_test.py").write_text("# deep test")
    return tmp_path


def _run_find(args: str, cwd: str) -> str:
    """Run _run_find_command with mocked cwd."""
    from src.repl import _run_find_command
    with mock.patch('os.getcwd', return_value=cwd):
        return _run_find_command(args)


class TestFindCommand:
    def test_find_by_name_pattern(self, find_dir):
        result = _run_find("*.py", str(find_dir))
        assert "hello.py" in result
        assert "hello_test.py" in result
        assert "deep.py" in result
        assert "deep_test.py" in result

    def test_find_no_args(self, find_dir):
        result = _run_find("", str(find_dir))
        assert "Usage" in result

    def test_find_no_match(self, find_dir):
        result = _run_find("*.xyz", str(find_dir))
        assert "No files found" in result

    def test_find_specific_file(self, find_dir):
        result = _run_find("README.md", str(find_dir))
        assert "README.md" in result

    def test_find_test_files(self, find_dir):
        result = _run_find("*test*.py", str(find_dir))
        assert "hello_test.py" in result
        assert "deep_test.py" in result

    def test_find_skips_noise_dirs(self, find_dir):
        # Create a .git directory with a file — should be filtered out
        (find_dir / ".git").mkdir()
        (find_dir / ".git" / "config").write_text("[core]")
        result = _run_find("config", str(find_dir))
        assert "config" not in result or ".git" not in result

    def test_find_skips_pycache(self, find_dir):
        (find_dir / "__pycache__").mkdir()
        (find_dir / "__pycache__" / "hello.cpython-311.pyc").write_text("bytecode")
        result = _run_find("*.pyc", str(find_dir))
        assert "pycache" not in result

    def test_find_shows_count(self, find_dir):
        result = _run_find("*.py", str(find_dir))
        assert "file(s)" in result

    def test_find_shows_pattern(self, find_dir):
        result = _run_find("*.py", str(find_dir))
        assert "*.py" in result
