"""Test /grep --context flag for showing surrounding lines."""
import os
import tempfile
from src.repl import _run_grep


def test_grep_context_flag():
    """The -C flag should show surrounding lines around matches."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "sample.txt")
        with open(test_file, "w") as f:
            f.write("line 1\nline 2\ntarget line\nline 4\nline 5\n")

        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            # Without context: just the match
            result = _run_grep("target")
            assert "target line" in result
            assert "line 1" not in result
            assert "line 4" not in result

            # With -C 1: should show 1 line before and after
            result = _run_grep("target -C 1")
            assert "target line" in result
            # Context lines should appear
            assert "line 2" in result
            assert "line 4" in result
            # Lines too far away should not appear
            assert "line 1" not in result
            assert "line 5" not in result
        finally:
            os.chdir(old_cwd)


def test_grep_context_longform():
    """The --context N long form should work the same as -C N."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "sample.txt")
        with open(test_file, "w") as f:
            f.write("aaa\nbbb\nccc\nddd\neee\n")

        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            result = _run_grep("ccc --context 2")
            assert "ccc" in result
            assert "aaa" in result
            assert "bbb" in result
            assert "ddd" in result
            assert "eee" in result
        finally:
            os.chdir(old_cwd)


def test_grep_context_zero():
    """The -C 0 should behave like no context (just the match)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "sample.txt")
        with open(test_file, "w") as f:
            f.write("aaa\nbbb\nccc\nddd\n")

        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            result = _run_grep("ccc -C 0")
            assert "ccc" in result
            assert "bbb" not in result
            assert "ddd" not in result
        finally:
            os.chdir(old_cwd)


def test_grep_context_boundary():
    """Context lines should not go beyond file boundaries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "sample.txt")
        with open(test_file, "w") as f:
            f.write("first\nsecond\nthird\n")

        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            # Match on first line with -C 5 should not crash
            result = _run_grep("first -C 5")
            assert "first" in result
            assert "second" in result
            assert "third" in result
        finally:
            os.chdir(old_cwd)


def test_grep_context_respects_max_results():
    """Even with context, max_results should still limit total output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a file with many matches
        test_file = os.path.join(tmpdir, "many.txt")
        with open(test_file, "w") as f:
            for i in range(100):
                f.write(f"line {i} match\n")

        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            result = _run_grep("match -C 1")
            # Should be truncated at 50 results
            assert "truncated at 50" in result
        finally:
            os.chdir(old_cwd)
