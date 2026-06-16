"""Tests for copy_file error messages when destination is a directory with a conflict.

Bug: when copying into an existing directory that already contains a file with
the same name, the error message named the DIRECTORY instead of the conflicting
FILE. The LLM can't act on "already exists: /path/to/dir" — it needs to know
WHICH file inside the dir is the conflict.
"""

import os

from src.tools import tool_copy_file


class TestCopyFileDirCollision:
    def test_copy_into_dir_with_conflict_names_conflicting_file(self, tmp_path):
        """Error message must name the conflicting file, not the directory."""
        src = tmp_path / "data.txt"
        src.write_text("new")
        dst_dir = tmp_path / "subdir"
        dst_dir.mkdir()
        conflicting = dst_dir / "data.txt"
        conflicting.write_text("old")

        result = tool_copy_file(str(src), str(dst_dir))

        assert "[ERROR]" in result
        # The conflicting file path (with its name) must appear in the message
        assert "data.txt" in result
        # Resolved path should reference the file inside the dir, not just the dir
        assert str(conflicting) in result

    def test_copy_into_dir_with_conflict_preserves_existing(self, tmp_path):
        """Existing conflicting file must not be overwritten."""
        src = tmp_path / "data.txt"
        src.write_text("new")
        dst_dir = tmp_path / "subdir"
        dst_dir.mkdir()
        conflicting = dst_dir / "data.txt"
        conflicting.write_text("old")

        tool_copy_file(str(src), str(dst_dir))

        assert conflicting.read_text() == "old"

    def test_copy_into_dir_no_conflict_succeeds(self, tmp_path):
        """Sanity: copying into a dir with no name clash works fine."""
        src = tmp_path / "data.txt"
        src.write_text("new")
        dst_dir = tmp_path / "subdir"
        dst_dir.mkdir()

        result = tool_copy_file(str(src), str(dst_dir))

        assert "[OK]" in result
        assert (dst_dir / "data.txt").read_text() == "new"
