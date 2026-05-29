"""Tests for the mkdir tool."""

import os
import tempfile
from pathlib import Path

import pytest

from src.tools import tool_write_file


class TestMkdirTool:
    """Tests for the mkdir (create directory) tool."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _import_mkdir(self):
        from src.tools import tool_mkdir
        return tool_mkdir

    def test_creates_single_directory(self):
        """mkdir should create a single directory."""
        tool_mkdir = self._import_mkdir()
        target = os.path.join(self.tmpdir, "newdir")
        result = tool_mkdir(path=target)
        assert "[OK]" in result
        assert os.path.isdir(target)

    def test_creates_nested_directories(self):
        """mkdir with parents=True should create nested directories."""
        tool_mkdir = self._import_mkdir()
        target = os.path.join(self.tmpdir, "a", "b", "c")
        result = tool_mkdir(path=target, parents=True)
        assert "[OK]" in result
        assert os.path.isdir(target)

    def test_nested_fails_without_parents(self):
        """mkdir without parents should fail on nested path."""
        tool_mkdir = self._import_mkdir()
        target = os.path.join(self.tmpdir, "x", "y", "z")
        result = tool_mkdir(path=target, parents=False)
        assert "[ERROR]" in result
        assert not os.path.exists(target)

    def test_existing_directory_ok(self):
        """mkdir on existing directory should succeed (idempotent)."""
        tool_mkdir = self._import_mkdir()
        target = os.path.join(self.tmpdir, "existing")
        os.makedirs(target)
        result = tool_mkdir(path=target)
        assert "[OK]" in result

    def test_conflicts_with_file(self):
        """mkdir should error if path is an existing file."""
        tool_mkdir = self._import_mkdir()
        target = os.path.join(self.tmpdir, "file.txt")
        Path(target).write_text("data")
        result = tool_mkdir(path=target)
        assert "[ERROR]" in result
