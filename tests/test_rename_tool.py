"""Tests for the rename tool."""

import os
import tempfile

from src.tools import tool_rename


class TestToolRename:
    """Tests for the rename tool."""

    def test_rename_file(self, tmp_path):
        """Basic file rename in the same directory."""
        src = tmp_path / "old.txt"
        src.write_text("hello")
        result = tool_rename(str(src), str(tmp_path / "new.txt"))
        assert "[OK]" in result
        assert not src.exists()
        assert (tmp_path / "new.txt").read_text() == "hello"

    def test_rename_file_cross_directory(self, tmp_path):
        """Move a file to a different directory."""
        src = tmp_path / "old.txt"
        src.write_text("hello")
        dest_dir = tmp_path / "subdir"
        dest_dir.mkdir()
        result = tool_rename(str(src), str(dest_dir / "new.txt"))
        assert "[OK]" in result
        assert not src.exists()
        assert (dest_dir / "new.txt").read_text() == "hello"

    def test_rename_nonexistent_source(self, tmp_path):
        """Should error when source doesn't exist."""
        result = tool_rename(str(tmp_path / "nope.txt"), str(tmp_path / "new.txt"))
        assert "[ERROR]" in result

    def test_rename_dest_already_exists(self, tmp_path):
        """Should error when destination already exists."""
        src = tmp_path / "old.txt"
        dst = tmp_path / "new.txt"
        src.write_text("hello")
        dst.write_text("existing")
        result = tool_rename(str(src), str(dst))
        assert "[ERROR]" in result

    def test_rename_directory(self, tmp_path):
        """Can rename a directory."""
        src = tmp_path / "old_dir"
        src.mkdir()
        (src / "file.txt").write_text("content")
        result = tool_rename(str(src), str(tmp_path / "new_dir"))
        assert "[OK]" in result
        assert not src.exists()
        assert (tmp_path / "new_dir" / "file.txt").read_text() == "content"

    def test_rename_empty_source_path(self):
        """Should error with empty source path."""
        result = tool_rename("", "/some/dest")
        assert "[ERROR]" in result

    def test_rename_empty_dest_path(self):
        """Should error with empty destination path."""
        result = tool_rename("/some/src", "")
        assert "[ERROR]" in result

    def test_rename_same_path(self, tmp_path):
        """Renaming to the same path should be a no-op or error."""
        src = tmp_path / "same.txt"
        src.write_text("hello")
        result = tool_rename(str(src), str(src))
        # Either OK (no-op) or error — both acceptable
        # Most importantly, the file should still exist
        assert src.exists()
