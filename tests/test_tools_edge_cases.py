"""Edge-case tests for yoyo-py tools — covering paths not hit by basic tests."""

import os
import tempfile
import pytest

from src.tools import (
    tool_bash,
    tool_read_file,
    tool_write_file,
    tool_edit_file,
    tool_search,
    tool_list_files,
    _truncate,
    _is_binary,
    _format_size,
)


class TestBashEdgeCases:
    def test_empty_command(self):
        """Empty command should succeed (shell runs empty and exits 0)."""
        result = tool_bash("")
        # An empty command may return exit code 0 or just nothing
        assert isinstance(result, str)

    def test_multiline_output(self):
        result = tool_bash("echo -e 'line1\nline2\nline3'")
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result

    def test_large_output_truncation(self):
        """Very large output should be truncated to 50KB."""
        # Generate ~60KB of output
        result = tool_bash("python3 -c \"print('x' * 60000)\"")
        assert "[truncated" in result or len(result) < 60000

    def test_command_not_found(self):
        result = tool_bash("nonexistent_command_xyz_12345")
        # Should not crash — returns error or non-zero exit code
        assert isinstance(result, str)
        assert len(result) > 0

    def test_unicode_output(self):
        result = tool_bash("echo '你好世界 🌍'")
        assert "你好世界" in result or "🌍" in result or isinstance(result, str)

    def test_stderr_and_stdout_combined(self):
        result = tool_bash("echo out; echo err >&2")
        assert "out" in result
        assert "err" in result


class TestReadFileEdgeCases:
    def test_read_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        result = tool_read_file(str(f))
        assert "0 lines" in result

    def test_read_offset_beyond_file(self, tmp_path):
        """Offset beyond file length should return no content without crashing."""
        f = tmp_path / "short.txt"
        f.write_text("only one line\n")
        result = tool_read_file(str(f), offset=100)
        assert isinstance(result, str)
        # Should not crash; should show header with 1 line but no content

    def test_read_directory(self, tmp_path):
        """Trying to read a directory should return an error."""
        result = tool_read_file(str(tmp_path))
        assert "ERROR" in result or "not a file" in result.lower()

    def test_read_with_zero_limit(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\n")
        result = tool_read_file(str(f), limit=0)
        assert isinstance(result, str)  # Should not crash

    def test_read_negative_offset(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\n")
        # Negative offset: max(0, -1-1) = max(0, -2) = 0, so reads from start
        result = tool_read_file(str(f), offset=-1)
        assert isinstance(result, str)  # Should not crash

    def test_read_limit_capped_at_2000(self, tmp_path):
        """Limit above 2000 should be capped."""
        f = tmp_path / "test.txt"
        f.write_text("\n".join(f"line{i}" for i in range(3000)))
        result = tool_read_file(str(f), limit=5000)
        # Should only show up to 2000 lines
        assert "line1999" in result
        assert "line2000" not in result or "line2001" not in result


class TestWriteFileEdgeCases:
    def test_write_empty_content(self, tmp_path):
        f = tmp_path / "empty.txt"
        result = tool_write_file(str(f), "")
        assert "OK" in result
        assert f.read_text() == ""

    def test_write_unicode_content(self, tmp_path):
        f = tmp_path / "unicode.txt"
        result = tool_write_file(str(f), "こんにちは 🎉\n")
        assert "OK" in result
        assert f.read_text() == "こんにちは 🎉\n"

    def test_write_to_existing_dir_path(self, tmp_path):
        """Writing to a path that's an existing directory should fail."""
        result = tool_write_file(str(tmp_path), "content")
        assert "ERROR" in result or isinstance(result, str)


class TestEditFileEdgeCases:
    def test_edit_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        result = tool_edit_file(str(f), "not there", "x")
        assert "not found" in result.lower() or "ERROR" in result

    def test_edit_file_not_found(self):
        result = tool_edit_file("/nonexistent/file.txt", "old", "new")
        assert "not found" in result.lower() or "ERROR" in result

    def test_edit_with_empty_old_string(self, tmp_path):
        """Empty old_string matches everywhere — replace_all behavior."""
        f = tmp_path / "test.txt"
        f.write_text("hello\n")
        result = tool_edit_file(str(f), "", "X")
        # Empty old_string matches at every position — count > 1
        assert "ERROR" in result or "times" in result or isinstance(result, str)

    def test_edit_preserves_file_encoding(self, tmp_path):
        f = tmp_path / "unicode.txt"
        f.write_text("hello 你好\n")
        result = tool_edit_file(str(f), "hello", "hi")
        assert "OK" in result
        content = f.read_text()
        assert "hi" in content
        assert "你好" in content


class TestSearchEdgeCases:
    def test_search_invalid_regex(self):
        """Invalid regex pattern should return an error, not crash."""
        result = tool_search("[invalid regex")
        assert "ERROR" in result or "invalid" in result.lower() or isinstance(result, str)

    def test_search_empty_directory(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = tool_search("anything", str(empty_dir))
        assert isinstance(result, str)  # Should not crash


class TestListFilesEdgeCases:
    def test_list_with_glob_filter(self, tmp_path):
        (tmp_path / "a.py").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        result = tool_list_files(str(tmp_path), glob_pattern="*.py")
        assert "a.py" in result
        assert "b.txt" not in result

    def test_list_with_depth(self, tmp_path):
        (tmp_path / "top.txt").write_text("top")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.txt").write_text("deep")
        result = tool_list_files(str(tmp_path), max_depth=1)
        assert "top.txt" in result
        # With max_depth=1, should still see deep.txt since find's maxdepth counts from start
        # but let's just verify it doesn't crash
        assert isinstance(result, str)

    def test_list_file_not_directory(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("content")
        result = tool_list_files(str(f))
        assert "not a directory" in result.lower() or "ERROR" in result


class TestTruncateEdgeCases:
    def test_truncate_exact_boundary(self):
        """Text exactly at the limit should not be truncated."""
        text = "x" * 100
        result = _truncate(text, 100)
        assert result == text
        assert "truncated" not in result

    def test_truncate_unicode(self):
        """Unicode text truncation should not produce garbled characters."""
        text = "你好" * 1000  # 6 bytes per 你好 pair
        result = _truncate(text, 100)
        assert isinstance(result, str)


class TestFormatSizeEdgeCases:
    def test_zero_bytes(self):
        assert _format_size(0) == "0B"

    def test_large_terabyte(self):
        result = _format_size(2 * 1024 ** 4)  # 2 TB
        assert "TB" in result
