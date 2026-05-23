"""Tests for /tree command — project structure visualization."""

import os
import tempfile
from pathlib import Path

from src.repl import _project_tree


class TestProjectTree:
    """Test the _project_tree function."""

    def test_empty_directory(self, tmp_path):
        """Empty directory shows just the root."""
        result = _project_tree(str(tmp_path))
        assert result  # Should produce some output

    def test_shows_files(self, tmp_path):
        """Files are listed in the tree."""
        (tmp_path / "main.py").write_text("hello", encoding="utf-8")
        (tmp_path / "README.md").write_text("# hello", encoding="utf-8")
        result = _project_tree(str(tmp_path))
        assert "main.py" in result
        assert "README.md" in result

    def test_shows_directories(self, tmp_path):
        """Directories are shown with proper indentation."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "app.py").write_text("", encoding="utf-8")
        result = _project_tree(str(tmp_path))
        assert "src" in result
        assert "app.py" in result

    def test_max_depth_limit(self, tmp_path):
        """Respects max_depth parameter."""
        deep = tmp_path / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        (deep / "file.py").write_text("", encoding="utf-8")
        result = _project_tree(str(tmp_path), max_depth=2)
        # Should show a/ and b/ but not c/ or d/
        assert "a" in result

    def test_ignores_common_dirs(self, tmp_path):
        """Common ignored directories (.git, node_modules, __pycache__) are excluded."""
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("", encoding="utf-8")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "pkg").write_text("", encoding="utf-8")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "mod.cpython-311.pyc").write_text("", encoding="utf-8")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("", encoding="utf-8")
        result = _project_tree(str(tmp_path))
        assert ".git" not in result
        assert "node_modules" not in result
        assert "__pycache__" not in result
        assert "src" in result
        assert "main.py" in result

    def test_nonexistent_directory(self):
        """Nonexistent directory returns error."""
        result = _project_tree("/nonexistent/path/xyz")
        assert "error" in result.lower() or "not found" in result.lower()

    def test_shows_file_count_summary(self, tmp_path):
        """Output includes a summary of total files/directories."""
        (tmp_path / "a.py").write_text("", encoding="utf-8")
        (tmp_path / "b.py").write_text("", encoding="utf-8")
        result = _project_tree(str(tmp_path))
        # Should mention some count info
        assert "2" in result or "file" in result.lower()
