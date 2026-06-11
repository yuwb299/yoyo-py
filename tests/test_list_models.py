"""Test --list-models CLI flag."""
import subprocess
import sys


def test_list_models_flag():
    """--list-models should print model names and context window info."""
    result = subprocess.run(
        [sys.executable, "-m", "src.main", "--list-models"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    output = result.stdout
    # Should contain some known model names
    assert "glm-5" in output
    assert "gpt-4o" in output
    assert "claude" in output
    assert "deepseek" in output
    # Should contain context window info
    assert "context" in output.lower()


def test_list_models_exits_cleanly():
    """--list-models should not print to stderr."""
    result = subprocess.run(
        [sys.executable, "-m", "src.main", "--list-models"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert result.stderr.strip() == ""


def test_list_models_groups_models():
    """Output should group models and show usage hint."""
    result = subprocess.run(
        [sys.executable, "-m", "src.main", "--list-models"],
        capture_output=True, text=True, timeout=10,
    )
    assert "--model" in result.stdout
