"""Tests for --think CLI flag and /think tab completion."""

import subprocess
import sys


def test_think_in_help():
    """--think should appear in --help output."""
    result = subprocess.run(
        [sys.executable, "-m", "src.main", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--think" in result.stdout
    assert "reasoning effort" in result.stdout.lower()


def test_think_choices_rejected():
    """--think should reject invalid choices."""
    result = subprocess.run(
        [sys.executable, "-m", "src.main", "--think", "invalid"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_think_valid_choices():
    """--think should accept low, medium, high."""
    for level in ("low", "medium", "high"):
        result = subprocess.run(
            [sys.executable, "-m", "src.main", "--think", level, "--help"],
            capture_output=True,
            text=True,
        )
        # --help exits 0 regardless of --think, but no error about --think
        assert result.returncode == 0


def test_slash_commands_includes_think():
    """/think should be in the tab completion list."""
    from src.repl import _SLASH_COMMANDS
    assert "/think" in _SLASH_COMMANDS


def test_slash_completer_matches_think():
    """Tab completer should match /th to /think."""
    from src.repl import _slash_completer
    # state=0 returns first match
    result = _slash_completer("/th", 0)
    assert result == "/think"
    # state=1 returns None (no more matches)
    result = _slash_completer("/th", 1)
    assert result is None
