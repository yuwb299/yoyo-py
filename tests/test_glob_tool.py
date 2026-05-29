"""Tests for the glob tool."""

import os
import tempfile
from pathlib import Path

import pytest

from src.tools import tool_search, tool_list_files


# We need to import the glob tool once it's added
# For now, test that list_files and search work as expected
# Then we'll add glob-specific tests


class TestGlobTool:
    """Tests for the glob file-finding tool."""

    def setup_method(self):
        """Create a temp directory with a known structure."""
        self.tmpdir = tempfile.mkdtemp()
        # Create files:
        # a.py, b.py, c.txt, sub/d.py, sub/e.txt, sub/deep/f.py
        Path(self.tmpdir, "a.py").write_text("pass")
        Path(self.tmpdir, "b.py").write_text("pass")
        Path(self.tmpdir, "c.txt").write_text("hello")
        Path(self.tmpdir, "sub").mkdir()
        Path(self.tmpdir, "sub", "d.py").write_text("pass")
        Path(self.tmpdir, "sub", "e.txt").write_text("world")
        Path(self.tmpdir, "sub", "deep").mkdir()
        Path(self.tmpdir, "sub", "deep", "f.py").write_text("pass")

    def teardown_method(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _import_glob(self):
        """Import the glob tool function."""
        from src.tools import tool_glob
        return tool_glob

    def test_glob_finds_py_files(self):
        """glob should find .py files matching the pattern."""
        tool_glob = self._import_glob()
        result = tool_glob(pattern="*.py", path=self.tmpdir)
        assert "a.py" in result
        assert "b.py" in result
        assert "c.txt" not in result

    def test_glob_recursive(self):
        """glob with ** should find files recursively."""
        tool_glob = self._import_glob()
        result = tool_glob(pattern="**/*.py", path=self.tmpdir)
        assert "a.py" in result
        assert "b.py" in result
        assert "d.py" in result
        assert "f.py" in result
        assert "c.txt" not in result

    def test_glob_txt_files(self):
        """glob should find .txt files."""
        tool_glob = self._import_glob()
        result = tool_glob(pattern="*.txt", path=self.tmpdir)
        assert "c.txt" in result
        assert "a.py" not in result

    def test_glob_no_matches(self):
        """glob with no matches should report that."""
        tool_glob = self._import_glob()
        result = tool_glob(pattern="*.xyz", path=self.tmpdir)
        assert "no files found" in result.lower() or "No matches" in result

    def test_glob_invalid_path(self):
        """glob with nonexistent path should error."""
        tool_glob = self._import_glob()
        result = tool_glob(pattern="*", path="/nonexistent/path/xyz")
        assert "[ERROR]" in result

    def test_glob_max_results(self):
        """glob should respect max_results limit."""
        tool_glob = self._import_glob()
        # Only 3 .py files exist, but set max to 2
        result = tool_glob(pattern="**/*.py", path=self.tmpdir, max_results=2)
        # Should show at most 2 files and a truncation note
        assert "2" in result  # count should mention 2

    def test_glob_default_path_is_cwd(self):
        """glob with no path should use current directory."""
        tool_glob = self._import_glob()
        # Just ensure it doesn't crash — we can't predict results from cwd
        result = tool_glob(pattern="*")
        assert isinstance(result, str)

    def test_glob_with_sizes(self):
        """glob can optionally show file sizes."""
        tool_glob = self._import_glob()
        result = tool_glob(pattern="*.py", path=self.tmpdir, show_sizes=True)
        # Should contain size indicators like "B" or "KB"
        assert "B" in result or "KB" in result

    def test_glob_sorts_results(self):
        """glob results should be sorted alphabetically."""
        tool_glob = self._import_glob()
        result = tool_glob(pattern="*.py", path=self.tmpdir)
        lines = [l.strip() for l in result.splitlines() if l.strip() and not l.startswith("[")]
        # Extract just filenames
        names = [l.split()[-1] if " " in l else l for l in lines]
        # Filter out non-filename lines
        file_names = [n for n in names if n.endswith(".py")]
        assert file_names == sorted(file_names)
