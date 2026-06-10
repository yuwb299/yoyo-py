"""Tests for the copy_file tool."""

import os
import tempfile

import pytest

from src.tools import tool_copy_file


class TestCopyFileTool:
    """Test the copy_file tool implementation."""

    def test_copy_file_basic(self, tmp_path):
        """Copy a file to a new location."""
        src = tmp_path / "source.txt"
        src.write_text("hello world")
        dst = tmp_path / "dest.txt"
        result = tool_copy_file(str(src), str(dst))
        assert "[OK]" in result
        assert dst.read_text() == "hello world"

    def test_copy_file_preserves_original(self, tmp_path):
        """Source file is unchanged after copy."""
        src = tmp_path / "original.txt"
        src.write_text("don't modify me")
        dst = tmp_path / "copy.txt"
        tool_copy_file(str(src), str(dst))
        assert src.read_text() == "don't modify me"
        assert dst.read_text() == "don't modify me"

    def test_copy_file_source_not_found(self, tmp_path):
        """Error when source doesn't exist."""
        result = tool_copy_file(str(tmp_path / "nonexistent.txt"), str(tmp_path / "dest.txt"))
        assert "[ERROR]" in result
        assert "not found" in result.lower()

    def test_copy_file_dest_exists(self, tmp_path):
        """Error when destination already exists — prevents accidental overwrite."""
        src = tmp_path / "source.txt"
        src.write_text("new content")
        dst = tmp_path / "existing.txt"
        dst.write_text("old content")
        result = tool_copy_file(str(src), str(dst))
        assert "[ERROR]" in result
        assert "already exists" in result.lower()
        # Verify destination was NOT overwritten
        assert dst.read_text() == "old content"

    def test_copy_file_creates_parent_dirs(self, tmp_path):
        """Creates parent directories of destination if they don't exist."""
        src = tmp_path / "source.txt"
        src.write_text("deep copy")
        dst = tmp_path / "sub" / "dir" / "dest.txt"
        result = tool_copy_file(str(src), str(dst))
        assert "[OK]" in result
        assert dst.read_text() == "deep copy"

    def test_copy_file_binary_content(self, tmp_path):
        """Can copy binary files."""
        src = tmp_path / "binary.bin"
        src.write_bytes(bytes(range(256)))
        dst = tmp_path / "copy.bin"
        result = tool_copy_file(str(src), str(dst))
        assert "[OK]" in result
        assert dst.read_bytes() == bytes(range(256))

    def test_copy_file_empty_file(self, tmp_path):
        """Can copy an empty file."""
        src = tmp_path / "empty.txt"
        src.write_text("")
        dst = tmp_path / "copy.txt"
        result = tool_copy_file(str(src), str(dst))
        assert "[OK]" in result
        assert dst.read_text() == ""

    def test_copy_file_same_path(self, tmp_path):
        """Copying to same path should fail (dest already exists)."""
        src = tmp_path / "file.txt"
        src.write_text("content")
        result = tool_copy_file(str(src), str(src))
        assert "[ERROR]" in result

    def test_copy_file_into_directory(self, tmp_path):
        """Copying a file into an existing directory uses source filename."""
        src = tmp_path / "file.txt"
        src.write_text("into dir")
        dst_dir = tmp_path / "target_dir"
        dst_dir.mkdir()
        result = tool_copy_file(str(src), str(dst_dir))
        assert "[OK]" in result
        expected_dest = dst_dir / "file.txt"
        assert expected_dest.read_text() == "into dir"
