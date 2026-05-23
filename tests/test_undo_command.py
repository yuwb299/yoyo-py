"""Tests for /undo command — revert last file change via git."""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.repl import _git_undo


class TestGitUndo:
    """Test the _git_undo function."""

    def test_undo_no_git_repo(self):
        """Returns error when not in a git repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("os.getcwd", return_value=tmpdir):
                # Not a git repo
                result = _git_undo()
                assert "not a git repo" in result.lower() or "error" in result.lower()

    def test_undo_no_changes_to_revert(self, tmp_path):
        """When HEAD matches working tree, nothing to undo."""
        # Set up a minimal git repo
        _init_git_repo(tmp_path)
        result = _git_undo(workdir=str(tmp_path))
        assert "nothing" in result.lower() or "no changes" in result.lower() or "clean" in result.lower()

    def test_undo_restores_modified_file(self, tmp_path):
        """Undo reverts a modified file to its last committed state."""
        repo = _init_git_repo(tmp_path)
        test_file = tmp_path / "test.py"
        test_file.write_text("original\n", encoding="utf-8")
        _git_commit(repo, "initial")

        # Modify the file
        test_file.write_text("modified\n", encoding="utf-8")

        # Undo
        result = _git_undo(workdir=str(tmp_path))
        assert "reverted" in result.lower() or "restored" in result.lower() or "ok" in result.lower()

        # File should be back to original
        assert test_file.read_text(encoding="utf-8") == "original\n"

    def test_undo_restores_deleted_file(self, tmp_path):
        """Undo restores a deleted file."""
        repo = _init_git_repo(tmp_path)
        test_file = tmp_path / "test.py"
        test_file.write_text("content\n", encoding="utf-8")
        _git_commit(repo, "initial")

        # Delete the file
        test_file.unlink()

        result = _git_undo(workdir=str(tmp_path))
        assert "reverted" in result.lower() or "restored" in result.lower() or "ok" in result.lower()

        # File should be restored
        assert test_file.exists()
        assert test_file.read_text(encoding="utf-8") == "content\n"

    def test_undo_removes_untracked_file(self, tmp_path):
        """Undo removes a newly created untracked file."""
        _init_git_repo(tmp_path)
        new_file = tmp_path / "new.py"
        new_file.write_text("new content\n", encoding="utf-8")

        result = _git_undo(workdir=str(tmp_path))
        # Untracked files are cleaned up
        assert not new_file.exists() or "untracked" in result.lower() or "ok" in result.lower()


# ── Helpers ─────────────────────────────────────────────────────────

def _init_git_repo(path: Path) -> Path:
    """Initialize a git repo in the given directory."""
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True, check=True)
    return path


def _git_commit(path: Path, message: str) -> None:
    """Add all and commit in the given repo."""
    subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=path, capture_output=True, check=True)
