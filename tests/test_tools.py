"""Tests for yoyo-py tools."""

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


class TestBash:
    def test_simple_echo(self):
        result = tool_bash("echo hello")
        assert "hello" in result

    def test_exit_code(self):
        result = tool_bash("exit 1")
        assert "exit code: 1" in result

    def test_stderr(self):
        result = tool_bash("echo error >&2")
        assert "error" in result

    def test_timeout(self):
        result = tool_bash("sleep 10", timeout=1)
        assert "TIMEOUT" in result

    def test_workdir(self, tmp_path):
        result = tool_bash("pwd", workdir=str(tmp_path))
        assert str(tmp_path) in result


class TestReadFile:
    def test_read_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello\nworld\n")
        result = tool_read_file(str(f))
        assert "hello" in result
        assert "world" in result
        assert "2 lines" in result

    def test_read_with_offset(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3\n")
        result = tool_read_file(str(f), offset=2)
        assert "line2" in result
        assert "line1" not in result

    def test_read_with_limit(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("\n".join(f"line{i}" for i in range(100)))
        result = tool_read_file(str(f), limit=10)
        assert "line0" in result
        assert "line99" not in result

    def test_read_nonexistent_file(self):
        result = tool_read_file("/nonexistent/file.txt")
        assert "not found" in result.lower() or "ERROR" in result

    def test_read_binary_file(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"\x00\x01\x02\x03")
        result = tool_read_file(str(f))
        assert "binary" in result.lower() or "ERROR" in result


class TestWriteFile:
    def test_write_new_file(self, tmp_path):
        f = tmp_path / "new.txt"
        result = tool_write_file(str(f), "hello world\n")
        assert "OK" in result
        assert f.read_text() == "hello world\n"

    def test_write_creates_dirs(self, tmp_path):
        f = tmp_path / "sub" / "dir" / "test.txt"
        result = tool_write_file(str(f), "content")
        assert "OK" in result
        assert f.read_text() == "content"

    def test_write_overwrites(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("old content")
        result = tool_write_file(str(f), "new content")
        assert "OK" in result
        assert f.read_text() == "new content"


class TestEditFile:
    def test_simple_replace(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world\n")
        result = tool_edit_file(str(f), "world", "python")
        assert "OK" in result
        assert f.read_text() == "hello python\n"

    def test_multiline_replace(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3\n")
        result = tool_edit_file(str(f), "line1\nline2", "LINE_A\nLINE_B")
        assert "OK" in result
        assert "LINE_A" in f.read_text()

    def test_delete_text(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("keep\ndelete\nkeep\n")
        result = tool_edit_file(str(f), "delete\n", "")
        assert "OK" in result
        assert f.read_text() == "keep\nkeep\n"

    def test_not_found(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello\n")
        result = tool_edit_file(str(f), "not present", "x")
        assert "not found" in result.lower() or "ERROR" in result

    def test_duplicate_without_replace_all(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("dup\ndup\n")
        result = tool_edit_file(str(f), "dup", "new")
        assert "2 times" in result or "replace_all" in result

    def test_replace_all(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("aaa\nbbb\naaa\n")
        result = tool_edit_file(str(f), "aaa", "ccc", replace_all=True)
        assert "OK" in result
        assert f.read_text() == "ccc\nbbb\nccc\n"


class TestSearch:
    def test_search_in_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("def hello():\n    pass\n")
        result = tool_search("hello", str(tmp_path))
        assert "hello" in result

    def test_search_no_match(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("nothing here\n")
        result = tool_search("xyzzy_not_found", str(tmp_path))
        assert "no match" in result.lower() or result.strip() == ""


class TestListFiles:
    def test_list_directory(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.py").write_text("b")
        result = tool_list_files(str(tmp_path))
        assert "a.txt" in result
        assert "b.py" in result

    def test_list_empty_directory(self, tmp_path):
        result = tool_list_files(str(tmp_path))
        assert "empty" in result.lower() or "0 files" in result

    def test_list_nonexistent(self):
        result = tool_list_files("/nonexistent/path")
        assert "not found" in result.lower() or "ERROR" in result


class TestHelpers:
    def test_truncate_short(self):
        assert _truncate("hello", 100) == "hello"

    def test_truncate_long(self):
        result = _truncate("x" * 200, 100)
        assert "truncated" in result
        assert len(result) < 200

    def test_is_binary_text(self, tmp_path):
        f = tmp_path / "text.txt"
        f.write_text("hello world")
        assert not _is_binary(f)

    def test_is_binary_data(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00\x01\x02")
        assert _is_binary(f)

    def test_format_size(self):
        assert _format_size(500) == "500B"
        assert _format_size(1500) == "1KB"
        assert _format_size(1500000) == "1MB"
