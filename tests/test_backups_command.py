"""Tests for /backups slash command — list and restore file backups."""

import os
import pytest
from pathlib import Path

from src.tools import tool_write_file, tool_edit_file
from src.repl import _run_backups_command


@pytest.fixture
def work_dir(tmp_path, monkeypatch):
    """Create a temp directory and cd into it."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestBackupsList:
    """/backups lists backup files."""

    def test_no_backups(self, work_dir):
        """No backups yet should show a message."""
        result = _run_backups_command("")
        assert "No backups" in result or "no backups" in result.lower()

    def test_lists_existing_backups(self, work_dir):
        """Should list backups created by write_file."""
        tool_write_file("test.txt", "v1")
        tool_write_file("test.txt", "v2")
        result = _run_backups_command("")
        assert "test.txt" in result
        assert "backup" in result.lower()

    def test_shows_backup_count(self, work_dir):
        """Should show how many backups exist."""
        tool_write_file("file.py", "v1")
        tool_write_file("file.py", "v2")
        tool_write_file("file.py", "v3")
        result = _run_backups_command("")
        # Should mention 2 backups (v1 before v2, v2 before v3)
        assert "2" in result


class TestBackupsRestore:
    """/backups restore restores a backup."""

    def test_restore_by_index(self, work_dir):
        """Should restore a backup by its index number."""
        tool_write_file("test.txt", "original")
        tool_write_file("test.txt", "overwritten")

        result = _run_backups_command("restore 1")
        assert "Restored" in result or "restored" in result.lower()
        assert Path("test.txt").read_text() == "original"

    def test_restore_invalid_index(self, work_dir):
        """Invalid index should show an error."""
        tool_write_file("test.txt", "content")
        tool_write_file("test.txt", "new")
        result = _run_backups_command("restore 99")
        assert "not found" in result.lower() or "invalid" in result.lower()

    def test_restore_no_backups(self, work_dir):
        """Restore with no backups should show a message."""
        result = _run_backups_command("restore 1")
        assert "no backups" in result.lower() or "No" in result


class TestBackupsShow:
    """/backups show displays backup content."""

    def test_show_backup_content(self, work_dir):
        """Should display the content of a backup."""
        tool_write_file("test.txt", "original content here")
        tool_write_file("test.txt", "overwritten")

        result = _run_backups_command("show 1")
        assert "original content here" in result

    def test_show_invalid_index(self, work_dir):
        """Invalid index should show an error."""
        tool_write_file("test.txt", "content")
        tool_write_file("test.txt", "new")
        result = _run_backups_command("show 99")
        assert "not found" in result.lower() or "invalid" in result.lower()
