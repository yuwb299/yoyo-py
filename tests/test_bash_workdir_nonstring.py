"""Tests: tool_bash must reject non-string workdir with a clear, param-named error.

Before this fix, tool_bash(command, workdir=123) leaked a cryptic TypeError
("expected str, bytes or os.PathLike object, not int") because `workdir`
bypassed the _to_str coercion applied to command/path in other tools. The
non-string reached Path(workdir) directly. This is the same class of bug
fixed for command (Day 65) and path/file_glob (Days 65-68) — workdir was
simply missed.
"""

import pytest

from src.tools import tool_bash


class TestBashWorkdirNonString:
    def test_int_workdir_returns_error_not_crash(self):
        result = tool_bash("echo hi", workdir=123)
        assert isinstance(result, str)
        assert result.startswith("[ERROR]")
        assert "workdir" in result.lower()

    def test_list_workdir_returns_error_not_crash(self):
        result = tool_bash("echo hi", workdir=["/tmp"])
        assert isinstance(result, str)
        assert result.startswith("[ERROR]")
        assert "workdir" in result.lower()

    def test_dict_workdir_returns_error_not_crash(self):
        result = tool_bash("echo hi", workdir={"x": 1})
        assert isinstance(result, str)
        assert result.startswith("[ERROR]")
        assert "workdir" in result.lower()

    def test_none_workdir_still_works(self):
        # None means "use current working directory" — must keep working.
        result = tool_bash("echo hi", workdir=None)
        assert "hi" in result
        assert "[ERROR]" not in result

    def test_string_workdir_still_works(self, tmp_path):
        result = tool_bash("pwd", workdir=str(tmp_path))
        assert str(tmp_path) in result
        assert "[ERROR]" not in result
