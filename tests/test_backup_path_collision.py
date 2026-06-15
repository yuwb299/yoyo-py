"""Tests for backup file naming collisions and lossy path restoration.

The backup system flattens file paths to a single name by replacing path
separators with underscores. This is lossy: 'src/agent.py' and 'src_agent.py'
both flatten to 'src_agent.py', so they:
  1. Share the same backup cleanup pool (MAX_BACKUPS_PER_FILE applied jointly)
  2. Restore to the wrong path (underscore → separator is ambiguous)

Files with underscores in their paths (e.g. 'text_helpers.py') restore to
wrong locations ('text/helpers.py'). These are data-integrity bugs in the
safety-net meant to PROTECT against data loss.

The fix mirrors the original directory structure under .yoyo/backups/, so the
original path is fully reconstructable and collisions are impossible.
"""

import os
from pathlib import Path

import pytest

from src.tools import (
    tool_write_file,
    _backup_file,
    _BACKUP_DIR_NAME,
    _BACKUP_SUBDIR,
    _MAX_BACKUPS_PER_FILE,
)
from src.repl import _run_backups_command


@pytest.fixture
def work_dir(tmp_path, monkeypatch):
    """Create a temp directory and cd into it."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _backup_root(work_dir):
    return work_dir / _BACKUP_DIR_NAME / _BACKUP_SUBDIR


def _backup_to_orig_path(backup_path: Path, backup_root: Path) -> str:
    """Reconstruct the original file path from a backup path.

    Works with the mirrored-directory layout (post-fix): the backup lives at
    <backup_root>/<orig_path_relative>_YYYYMMDD_HHMMSS[_N].bak
    """
    import re
    rel = backup_path.relative_to(backup_root)
    # Drop .bak suffix, then strip the timestamp suffix
    stem = rel.with_suffix("").as_posix()
    m = re.match(r"^(.+?)_(\d{8}_\d{6})(?:_\d+)?$", stem)
    if m:
        return m.group(1)
    return stem


class TestBackupPathCollision:
    """Different files that flatten to the same name must not collide."""

    def test_underscore_path_and_slash_path_backups_distinct(self, work_dir):
        """'src/agent.py' and 'src_agent.py' are different files — their backups
        must reconstruct to DISTINCT original paths so restore targets the
        correct file."""
        os.makedirs("src", exist_ok=True)
        Path("src/agent.py").write_text("import sys\n")
        Path("src_agent.py").write_text("print('flat')\n")

        _backup_file(Path("src/agent.py"))
        _backup_file(Path("src_agent.py"))

        root = _backup_root(work_dir)
        backups = list(root.rglob("*.bak"))
        assert len(backups) == 2, (
            f"expected 2 backups, got {len(backups)}: {[b.name for b in backups]}"
        )
        origs = sorted(_backup_to_orig_path(b, root) for b in backups)
        assert origs == ["src/agent.py", "src_agent.py"], (
            f"backups must reconstruct to distinct paths, got {origs}"
        )

    def test_collision_does_not_share_cleanup_pool(self, work_dir):
        """Old backups of 'src/agent.py' must not evict backups of 'src_agent.py'
        (and vice versa), since they are unrelated files."""
        os.makedirs("src", exist_ok=True)
        Path("src/agent.py").write_text("a\n")
        Path("src_agent.py").write_text("b\n")

        # Saturate src/agent.py's backup pool
        for i in range(_MAX_BACKUPS_PER_FILE + 2):
            Path("src/agent.py").write_text(f"a{i}\n")
            _backup_file(Path("src/agent.py"))

        # Now back up src_agent.py once
        _backup_file(Path("src_agent.py"))

        root = _backup_root(work_dir)
        all_backups = list(root.rglob("*.bak"))
        # Group by reconstructed original path
        by_orig: dict[str, int] = {}
        for b in all_backups:
            by_orig[_backup_to_orig_path(b, root)] = by_orig.get(_backup_to_orig_path(b, root), 0) + 1

        # src_agent.py must have exactly 1 backup (not evicted by agent.py's pool)
        assert by_orig.get("src_agent.py", 0) == 1, (
            f"src_agent.py backup count wrong: {by_orig}. "
            f"Collision caused shared cleanup pool."
        )
        # src/agent.py keeps at most MAX backups (its own pool)
        assert by_orig.get("src/agent.py", 0) == _MAX_BACKUPS_PER_FILE, (
            f"src/agent.py should have {_MAX_BACKUPS_PER_FILE} backups, got "
            f"{by_orig.get('src/agent.py', 0)}"
        )


class TestBackupRestoreLossless:
    """Restoring a backup must target the ORIGINAL file path, even when the
    path contains underscores or is nested."""

    def test_restore_nested_underscore_path(self, work_dir):
        """Backing up 'utils/text_helpers.py' and restoring must write back to
        'utils/text_helpers.py', NOT 'utils/text/helpers.py'."""
        # tool_write_file triggers _backup_file
        tool_write_file("utils/text_helpers.py", "ORIGINAL\n")
        tool_write_file("utils/text_helpers.py", "MODIFIED\n")

        # Restore backup #1 (the ORIGINAL)
        result = _run_backups_command("restore 1")
        assert "Restored" in result or "restored" in result.lower(), (
            f"restore failed: {result}"
        )
        # The nested file must contain ORIGINAL
        assert Path("utils/text_helpers.py").read_text() == "ORIGINAL\n", (
            "restore wrote to the wrong path (lossy underscore→separator)"
        )
        # And NO stray 'utils/text/helpers.py' should have been created
        assert not Path("utils/text/helpers.py").exists(), (
            "restore created a wrong nested path from underscores"
        )

    def test_restore_collision_paths_target_correct_file(self, work_dir):
        """With both 'src/agent.py' and 'src_agent.py' backed up, restoring
        must write to the CORRECT file, not a wrong path derived from the other.

        We restore src/agent.py's backup and verify it lands in src/agent.py
        (the nested path), proving underscore-bearing paths round-trip losslessly.
        """
        os.makedirs("src", exist_ok=True)
        tool_write_file("src/agent.py", "AGENT_DIR\n")
        tool_write_file("src_agent.py", "AGENT_FLAT\n")

        # Overwrite both (creates backups of the originals)
        tool_write_file("src/agent.py", "new_dir\n")
        tool_write_file("src_agent.py", "new_flat\n")

        root = _backup_root(work_dir)
        backups_before = sorted(root.rglob("*.bak"), key=lambda b: b.name)
        assert len(backups_before) == 2, f"expected 2 backups, got {len(backups_before)}"

        # The listing uses the same sort as the restore command. src/agent.py
        # sorts first (slash < underscore), so backup #1 targets src/agent.py.
        from src.tools import _backup_to_orig_path
        listing_sorted = sorted(
            backups_before,
            key=lambda b: str(b.relative_to(root)),
        )
        idx_of_dir = listing_sorted.index(
            [b for b in listing_sorted if _backup_to_orig_path(b) == "src/agent.py"][0]
        ) + 1

        result = _run_backups_command(f"restore {idx_of_dir}")
        assert "Restored" in result or "restored" in result.lower(), f"restore failed: {result}"

        # src/agent.py must now hold the ORIGINAL content
        assert Path("src/agent.py").read_text() == "AGENT_DIR\n", (
            "restore wrote to the wrong file or wrong content"
        )
        # src_agent.py must be UNCHANGED by this restore
        assert Path("src_agent.py").read_text() == "new_flat\n", (
            "restore wrongly modified the collision-partner file"
        )

    def test_normal_restore_still_works(self, work_dir):
        """Regression guard: simple single-file backup/restore round-trips."""
        tool_write_file("plain.txt", "v1\n")
        tool_write_file("plain.txt", "v2\n")
        result = _run_backups_command("restore 1")
        assert "Restored" in result or "restored" in result.lower()
        assert Path("plain.txt").read_text() == "v1\n"
