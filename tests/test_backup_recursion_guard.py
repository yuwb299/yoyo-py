"""Test that _backup_file skips files inside .yoyo/ directory."""

import pytest
from pathlib import Path

from src.tools import tool_write_file, _backup_file


@pytest.fixture
def work_dir(tmp_path, monkeypatch):
    """Create a temp directory and cd into it."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestBackupRecursionGuard:
    """Files inside .yoyo/ should never be backed up (prevents recursion)."""

    def test_no_backup_for_yoyo_files(self, work_dir):
        """Writing to .yoyo/ should not create backups of .yoyo/ files."""
        # Write a file inside .yoyo/
        tool_write_file(".yoyo/test.json", '{"key": "v1"}')
        result = tool_write_file(".yoyo/test.json", '{"key": "v2"}')
        assert "[OK]" in result

        # No backups should be created for files inside .yoyo/
        backup_dir = work_dir / ".yoyo" / "backups"
        if backup_dir.exists():
            backups = list(backup_dir.iterdir())
            # Should have zero backups of the .yoyo/test.json file
            yoyo_backups = [b for b in backups if "test.json" in b.name]
            assert len(yoyo_backups) == 0

    def test_backup_function_skips_yoyo_dir(self, work_dir):
        """_backup_file should silently skip files in .yoyo/."""
        test_file = work_dir / ".yoyo" / "dummy.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("content")

        # Should not raise or create backups
        _backup_file(test_file)

        backup_dir = work_dir / ".yoyo" / "backups"
        if backup_dir.exists():
            backups = list(backup_dir.iterdir())
            assert len(backups) == 0

    def test_normal_files_still_backed_up(self, work_dir):
        """Normal files outside .yoyo/ should still get backups."""
        tool_write_file("normal.txt", "v1")
        tool_write_file("normal.txt", "v2")

        backup_dir = work_dir / ".yoyo" / "backups"
        assert backup_dir.exists()
        backups = list(backup_dir.iterdir())
        assert len(backups) == 1
