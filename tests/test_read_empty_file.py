"""Tests for tool_read_file on empty files.

Empty files are valid — reading them should NOT report an error.
Previously, reading an empty file returned:
  "[File: ... (0 lines)]\n[ERROR] Offset 1 is past end of file"
because start=0 >= total=0 triggered the past-end branch. This is
misleading: offset 1 is the default and is the first valid line. An
empty file simply has no content to show.
"""

from src.tools import tool_read_file, tool_write_file


class TestReadEmptyFile:
    def test_empty_file_no_error(self, tmp_path):
        """Reading a freshly-created empty file must not include [ERROR]."""
        f = tmp_path / "empty.txt"
        f.write_text("")
        result = tool_read_file(str(f))
        assert "[ERROR]" not in result
        assert "0 lines" in result

    def test_empty_file_reports_zero_lines(self, tmp_path):
        f = tmp_path / "e2.txt"
        f.write_text("")
        result = tool_read_file(str(f))
        # Header should reflect 0 lines
        assert "(0 lines)" in result

    def test_empty_file_with_explicit_offset(self, tmp_path):
        """Even with an explicit offset=1, an empty file isn't an error."""
        f = tmp_path / "e3.txt"
        f.write_text("")
        result = tool_read_file(str(f), offset=1, limit=100)
        assert "[ERROR]" not in result

    def test_write_then_read_empty_roundtrip(self, tmp_path):
        """A file written with empty content should read back cleanly."""
        p = str(tmp_path / "rt.txt")
        tool_write_file(path=p, content="")
        result = tool_read_file(p)
        assert "[ERROR]" not in result
        assert "0 lines" in result
