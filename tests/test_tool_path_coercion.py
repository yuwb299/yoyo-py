"""Tests for path-argument coercion across all file tools.

Day 67: every file tool that takes a `path`/`source`/`destination` arg leaked a
cryptic "expected str, bytes or os.PathLike object, not int" message when the
LLM sent a non-string path. This message names NEITHER the offending parameter
nor the tool, so the LLM cannot self-correct — it just retries blindly. Each
tool already coerced its string CONTENT args (old_string, content, pattern) but
forgot the PATH args. Now path args are coerced via _to_str too, producing
param-named errors like "[ERROR] path must be a string, got int".
"""

from src.tools import (
    tool_read_file,
    tool_write_file,
    tool_edit_file,
    tool_mkdir,
    tool_copy_file,
    tool_rename,
    tool_glob,
    tool_list_files,
)

# The cryptic leak from pathlib that we are eliminating.
LEAK_SUBSTRINGS = ("os.PathLike", "expected str, bytes")


def _assert_param_error(result: str, param: str) -> None:
    """Assert the result is a clear param-named error, not a pathlib leak."""
    assert result.startswith("[ERROR]"), f"Expected [ERROR], got: {result!r}"
    for leak in LEAK_SUBSTRINGS:
        assert leak not in result, f"Still leaking pathlib error: {result!r}"
    assert param in result, (
        f"Error must name the param '{param}', got: {result!r}"
    )


class TestReadFilePath:
    def test_int_path(self):
        _assert_param_error(tool_read_file(123), "path")

    def test_list_path(self):
        _assert_param_error(tool_read_file(["src"]), "path")

    def test_none_path(self):
        _assert_param_error(tool_read_file(None), "path")


class TestWriteFilePath:
    def test_int_path(self):
        _assert_param_error(tool_write_file(123, "content"), "path")

    def test_none_path(self):
        _assert_param_error(tool_write_file(None, "content"), "path")

    def test_list_path(self):
        _assert_param_error(tool_write_file(["out.txt"], "content"), "path")


class TestEditFilePath:
    def test_int_path(self):
        _assert_param_error(tool_edit_file(123, "a", "b"), "path")

    def test_none_path(self):
        _assert_param_error(tool_edit_file(None, "a", "b"), "path")


class TestMkdirPath:
    def test_int_path(self):
        _assert_param_error(tool_mkdir(123), "path")

    def test_none_path(self):
        _assert_param_error(tool_mkdir(None), "path")


class TestCopyFilePaths:
    def test_int_source(self):
        _assert_param_error(tool_copy_file(123, "dst"), "source")

    def test_int_destination(self):
        _assert_param_error(tool_copy_file("src", 123), "destination")

    def test_none_source(self):
        _assert_param_error(tool_copy_file(None, "dst"), "source")


class TestRenamePaths:
    def test_int_source(self):
        _assert_param_error(tool_rename(123, "dst"), "source")

    def test_int_destination(self):
        _assert_param_error(tool_rename("src", 123), "destination")


class TestGlobPath:
    def test_int_path(self):
        _assert_param_error(tool_glob("*.py", 123), "path")

    def test_none_path(self):
        _assert_param_error(tool_glob("*.py", None), "path")


class TestListFilesPath:
    def test_int_path(self):
        _assert_param_error(tool_list_files(123), "path")

    def test_none_path(self):
        _assert_param_error(tool_list_files(None), "path")


class TestNormalBehaviorPreserved:
    """Ensure the coercion doesn't break valid string paths."""

    def test_read_file_real_file(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("hello\n")
        result = tool_read_file(str(f))
        assert "hello" in result

    def test_glob_real_dir(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        result = tool_glob("*.py", str(tmp_path))
        assert "a.py" in result

    def test_mkdir_real(self, tmp_path):
        target = tmp_path / "newdir"
        result = tool_mkdir(str(target))
        assert target.is_dir()
