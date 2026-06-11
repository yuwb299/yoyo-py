"""Test that _tool_summary includes copy_file in its output."""
from src.repl import _tool_summary


def test_tool_summary_copy_file():
    """copy_file should show source → destination, not just 'copy_file'."""
    result = _tool_summary("copy_file", {"source": "a.txt", "destination": "b.txt"})
    assert "a.txt" in result
    assert "b.txt" in result
    assert "→" in result


def test_tool_summary_copy_file_missing_args():
    """copy_file with missing args should still work (no crash)."""
    result = _tool_summary("copy_file", {})
    assert "copy" in result.lower() or "?" in result


def test_tool_summary_rename():
    """rename should show source → destination (regression check)."""
    result = _tool_summary("rename", {"source": "old.py", "destination": "new.py"})
    assert "old.py" in result
    assert "new.py" in result
    assert "→" in result


def test_tool_summary_unknown_tool():
    """Unknown tools should fall through to name-only display."""
    result = _tool_summary("mystery_tool", {"arg": "value"})
    assert result == "mystery_tool"
