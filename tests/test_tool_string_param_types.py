"""Tests for clear type-error messages on string tool params.

When the LLM sends a non-string where a string is required (e.g. content=123),
the tool should return a clear, param-named error rather than a cryptic Python
internal like "data must be str, not int" (from pathlib) or "replace() argument
2 must be str, not list" (from str.replace). Named errors let the LLM fix the
right argument on retry.
"""

from src.tools import tool_edit_file, tool_write_file


class TestWriteFileContentType:
    def test_int_content_clear_error(self, tmp_path):
        p = str(tmp_path / "f.txt")
        result = tool_write_file(path=p, content=123)
        assert isinstance(result, str)
        assert "[ERROR]" in result
        assert "content" in result
        assert "must be str" in result or "must be a string" in result

    def test_none_content_clear_error(self, tmp_path):
        p = str(tmp_path / "f.txt")
        result = tool_write_file(path=p, content=None)
        assert "[ERROR]" in result
        assert "content" in result

    def test_list_content_clear_error(self, tmp_path):
        p = str(tmp_path / "f.txt")
        result = tool_write_file(path=p, content=["a", "b"])
        assert "[ERROR]" in result
        assert "content" in result


class TestEditFileArgTypes:
    def test_int_old_string_named_error(self, tmp_path):
        p = str(tmp_path / "f.txt")
        tool_write_file(path=p, content="hello\n")
        result = tool_edit_file(path=p, old_string=123, new_string="x")
        assert "[ERROR]" in result
        assert "old_string" in result

    def test_list_new_string_named_error(self, tmp_path):
        p = str(tmp_path / "f.txt")
        tool_write_file(path=p, content="hello\n")
        result = tool_edit_file(path=p, old_string="hello", new_string=[1, 2])
        assert "[ERROR]" in result
        assert "new_string" in result

    def test_none_new_string_named_error(self, tmp_path):
        p = str(tmp_path / "f.txt")
        tool_write_file(path=p, content="hello\n")
        result = tool_edit_file(path=p, old_string="hello", new_string=None)
        assert "[ERROR]" in result
        assert "new_string" in result

    def test_int_path_named_error(self):
        # A non-string path should give a clear error, not a raw AttributeError
        result = tool_edit_file(path=123, old_string="x", new_string="y")
        assert "[ERROR]" in result
