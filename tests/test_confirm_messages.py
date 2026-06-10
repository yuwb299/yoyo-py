"""Tests for improved tool confirmation messages.

Verifies that edit_file, copy_file, and rename confirmations show useful
summaries of what the tool will do, including diff-like previews for edits.
"""

from src.repl import _make_confirm_fn


class TestConfirmMessages:

    def test_bash_shows_command(self):
        """Bash confirmation shows the command being run."""
        responses = {}

        def mock_input(prompt):
            responses["prompt"] = prompt
            return "y"

        confirm = _make_confirm_fn(input_fn=mock_input)
        confirm("bash", {"command": "rm -rf /tmp/test"})
        assert "$ rm -rf /tmp/test" in responses["prompt"]

    def test_edit_file_shows_diff_preview(self):
        """edit_file confirmation shows old/new string preview like a diff."""
        responses = {}

        def mock_input(prompt):
            responses["prompt"] = prompt
            return "n"

        confirm = _make_confirm_fn(input_fn=mock_input)
        confirm("edit_file", {
            "path": "src/main.py",
            "old_string": "print('hello')",
            "new_string": "print('world')",
        })
        prompt = responses["prompt"]
        assert "edit → src/main.py" in prompt
        # Should show diff-like old/new previews
        assert "print('hello')" in prompt
        assert "print('world')" in prompt

    def test_edit_file_truncates_long_strings(self):
        """Long old/new strings are truncated with ellipsis in preview."""
        responses = {}

        def mock_input(prompt):
            responses["prompt"] = prompt
            return "n"

        confirm = _make_confirm_fn(input_fn=mock_input)
        long_old = "x" * 100
        long_new = "y" * 100
        confirm("edit_file", {
            "path": "big.py",
            "old_string": long_old,
            "new_string": long_new,
        })
        prompt = responses["prompt"]
        # Should be truncated (60 chars + ellipsis)
        assert "…" in prompt or "..." in prompt

    def test_copy_file_shows_source_dest(self):
        """copy_file confirmation shows source → destination."""
        responses = {}

        def mock_input(prompt):
            responses["prompt"] = prompt
            return "n"

        confirm = _make_confirm_fn(input_fn=mock_input)
        confirm("copy_file", {
            "source": "a.txt",
            "destination": "b.txt",
        })
        assert "copy a.txt → b.txt" in responses["prompt"]

    def test_rename_shows_source_dest(self):
        """rename confirmation shows source → destination."""
        responses = {}

        def mock_input(prompt):
            responses["prompt"] = prompt
            return "n"

        confirm = _make_confirm_fn(input_fn=mock_input)
        confirm("rename", {
            "source": "old.py",
            "destination": "new.py",
        })
        assert "rename old.py → new.py" in responses["prompt"]

    def test_write_file_shows_path(self):
        """write_file confirmation shows the target path."""
        responses = {}

        def mock_input(prompt):
            responses["prompt"] = prompt
            return "n"

        confirm = _make_confirm_fn(input_fn=mock_input)
        confirm("write_file", {"path": "/tmp/test.txt"})
        assert "write → /tmp/test.txt" in responses["prompt"]

    def test_auto_approve_always_true(self):
        """auto_approve mode never asks for confirmation."""
        confirm = _make_confirm_fn(auto_approve=True)
        assert confirm("bash", {"command": "dangerous"}) is True
        assert confirm("write_file", {"path": "x"}) is True
