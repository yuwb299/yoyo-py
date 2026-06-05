"""Tests for /count command — code statistics."""

import os
import json
import pytest
from pathlib import Path


@pytest.fixture
def python_project(tmp_path):
    """Create a small Python project for testing."""
    # Python files
    (tmp_path / "main.py").write_text("# main\nprint('hello')\n")
    (tmp_path / "utils.py").write_text("def foo():\n    pass\n\n")
    # A file in a subdirectory
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "app.py").write_text("class App:\n    pass\n")

    # Non-code files
    (tmp_path / "README.md").write_text("# Readme\nSome text\n")
    (tmp_path / "data.json").write_text('{"key": "value"}\n')

    return tmp_path


@pytest.fixture
def mixed_project(tmp_path):
    """Create a project with multiple languages."""
    (tmp_path / "app.py").write_text("x = 1\n" * 10)
    (tmp_path / "index.js").write_text("const x = 1;\n" * 5)
    (tmp_path / "style.css").write_text("body { margin: 0; }\n" * 3)
    (tmp_path / "main.rs").write_text("fn main() {}\n")
    sub = tmp_path / "include"
    sub.mkdir()
    (sub / "header.h").write_text("#pragma once\n")
    (tmp_path / "notes.txt").write_text("notes\n")
    return tmp_path


def _run_count(workdir):
    """Run the count command and return the output string."""
    from src.repl import _run_count_command
    return _run_count_command(workdir=str(workdir))


class TestCountCommand:
    def test_python_project_counts(self, python_project):
        result = _run_count(python_project)
        assert "Python" in result
        assert "3 file(s)" in result
        # 2 + 4 + 2 = 8 total lines (but utils.py has trailing newline so 4 lines)
        # main.py: 2 lines, utils.py: 4 lines (def foo, pass, blank, blank), app.py: 2 lines = 8
        assert "line" in result.lower()

    def test_mixed_project(self, mixed_project):
        result = _run_count(mixed_project)
        assert "Python" in result
        assert "JavaScript" in result
        assert "CSS" in result
        assert "Rust" in result

    def test_empty_directory(self, tmp_path):
        result = _run_count(tmp_path)
        assert "No source files found" in result or "0 file" in result

    def test_shows_file_counts(self, python_project):
        result = _run_count(python_project)
        assert "3 file(s)" in result  # 3 Python files

    def test_nonexistent_directory(self):
        result = _run_count("/nonexistent/path/12345")
        assert "ERROR" in result or "not found" in result.lower()

    def test_skips_hidden_dirs(self, tmp_path):
        """Hidden dirs like .git should be skipped."""
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "secret.py").write_text("x = 1\n")
        (tmp_path / "visible.py").write_text("y = 2\n")
        result = _run_count(tmp_path)
        # Should only count the visible file
        assert "1 file(s)" in result or "visible" in result.lower()
        assert "secret" not in result

    def test_skips_common_noise_dirs(self, tmp_path):
        """node_modules, __pycache__, .venv should be skipped."""
        for dirname in ["node_modules", "__pycache__", ".venv", ".git"]:
            d = tmp_path / dirname
            d.mkdir()
            (d / "noise.py").write_text("noise\n")
        (tmp_path / "real.py").write_text("real\n")
        result = _run_count(tmp_path)
        assert "1 file(s)" in result

    def test_total_summary(self, python_project):
        result = _run_count(python_project)
        assert "Total" in result or "total" in result
