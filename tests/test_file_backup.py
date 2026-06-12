"""Tests for file backup on write_file and edit_file.

When write_file or edit_file overwrites an existing file, the old content
should be backed up to .yoyo/backups/ so users can recover from mistakes.
"""

import os
import json
import pytest
from pathlib import Path

from src.tools import tool_write_file, tool_edit_file


@pytest.fixture
def tmp_dir(tmp_path, monkeypatch):
    """Create a temp directory and cd into it."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestWriteFileBackup:
    """write_file should back up existing files before overwriting."""

    def test_new_file_no_backup(self, tmp_dir):
        """Writing a new file should NOT create a backup."""
        result = tool_write_file("newfile.txt", "hello")
        assert "[OK]" in result
        assert not (tmp_dir / ".yoyo" / "backups").exists()

    def test_overwrite_creates_backup(self, tmp_dir):
        """Overwriting an existing file should create a backup."""
        tool_write_file("test.txt", "original content")
        result = tool_write_file("test.txt", "new content")
        assert "[OK]" in result

        backup_dir = tmp_dir / ".yoyo" / "backups"
        assert backup_dir.exists()
        backups = list(backup_dir.iterdir())
        # Should have at least one backup file
        assert len(backups) >= 1

        # Backup should contain original content
        backup_content = backups[0].read_text(encoding="utf-8")
        assert backup_content == "original content"

    def test_multiple_overwrites_multiple_backups(self, tmp_dir):
        """Each overwrite should create a separate backup."""
        tool_write_file("test.txt", "v1")
        tool_write_file("test.txt", "v2")
        tool_write_file("test.txt", "v3")

        backup_dir = tmp_dir / ".yoyo" / "backups"
        backups = sorted(backup_dir.iterdir())
        # Should have 2 backups (v1 before v2, v2 before v3)
        assert len(backups) == 2
        assert backups[0].read_text(encoding="utf-8") == "v1"
        assert backups[1].read_text(encoding="utf-8") == "v2"

    def test_backup_preserves_current_file(self, tmp_dir):
        """After overwrite, the current file should have new content."""
        tool_write_file("test.txt", "old")
        tool_write_file("test.txt", "new")
        assert (tmp_dir / "test.txt").read_text(encoding="utf-8") == "new"

    def test_backup_with_subdirectory_file(self, tmp_dir):
        """Backup should work for files in subdirectories."""
        (tmp_dir / "sub").mkdir()
        tool_write_file("sub/test.py", "original")
        result = tool_write_file("sub/test.py", "modified")
        assert "[OK]" in result

        backup_dir = tmp_dir / ".yoyo" / "backups"
        assert backup_dir.exists()

    def test_backup_max_count(self, tmp_dir):
        """Should not create more than 10 backups per file."""
        for i in range(15):
            tool_write_file("test.txt", f"version {i}")

        backup_dir = tmp_dir / ".yoyo" / "backups"
        backups = list(backup_dir.iterdir())
        # Should cap at 10 backups
        assert len(backups) <= 10

    def test_empty_file_overwrite_still_backs_up(self, tmp_dir):
        """Overwriting an empty file should still back it up."""
        tool_write_file("empty.txt", "")
        result = tool_write_file("empty.txt", "not empty")
        assert "[OK]" in result
        backup_dir = tmp_dir / ".yoyo" / "backups"
        backups = list(backup_dir.iterdir())
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == ""


class TestEditFileBackup:
    """edit_file should back up existing files before modifying."""

    def test_edit_creates_backup(self, tmp_dir):
        """edit_file should back up before editing."""
        tool_write_file("test.txt", "hello world")
        result = tool_edit_file("test.txt", "hello", "goodbye")
        assert "[OK]" in result

        backup_dir = tmp_dir / ".yoyo" / "backups"
        assert backup_dir.exists()
        backups = list(backup_dir.iterdir())
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == "hello world"

    def test_edit_no_match_no_backup(self, tmp_dir):
        """If edit doesn't match, no backup should be created."""
        tool_write_file("test.txt", "hello")
        result = tool_edit_file("test.txt", "not_found", "replacement")
        assert "[ERROR]" in result
        assert not (tmp_dir / ".yoyo" / "backups").exists()
