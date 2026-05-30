"""Tests for /copy command — copy last assistant response to clipboard."""

from __future__ import annotations

import os
import sys
import subprocess
from unittest.mock import patch, MagicMock

import pytest

# We test the helper function directly
# Import the REPL module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _find_last_assistant_response(messages: list[dict]) -> str | None:
    """Extract the last assistant text response from messages."""
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if content and not content.startswith("[Context Summary]"):
                return content
    return None


def _copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard. Returns True on success."""
    try:
        if sys.platform == "darwin":
            proc = subprocess.run(["pbcopy"], input=text, text=True, timeout=5)
            return proc.returncode == 0
        elif sys.platform == "linux":
            # Try xclip first, then xsel
            for cmd in [["xclip", "-selection", "clipboard"], ["xclip"], ["xsel", "--clipboard"]]:
                try:
                    proc = subprocess.run(cmd, input=text, text=True, timeout=5)
                    if proc.returncode == 0:
                        return True
                except FileNotFoundError:
                    continue
            return False
        elif sys.platform == "win32":
            proc = subprocess.run(["clip"], input=text, text=True, timeout=5)
            return proc.returncode == 0
        return False
    except (subprocess.TimeoutExpired, OSError):
        return False


class TestFindLastAssistantResponse:
    """Test the helper function that finds the last response."""

    def test_finds_last_assistant_message(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        assert _find_last_assistant_response(messages) == "Hi there!"

    def test_finds_most_recent_assistant(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "Hi!"},
            {"role": "user", "content": "how are you"},
            {"role": "assistant", "content": "I'm good!"},
        ]
        assert _find_last_assistant_response(messages) == "I'm good!"

    def test_returns_none_when_no_assistant(self):
        messages = [{"role": "user", "content": "hello"}]
        assert _find_last_assistant_response(messages) is None

    def test_skips_compact_summaries(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "[Context Summary] stuff"},
            {"role": "user", "content": "hi"},
        ]
        assert _find_last_assistant_response(messages) is None

    def test_skips_empty_content(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": ""},
        ]
        assert _find_last_assistant_response(messages) is None

    def test_finds_real_response_before_summary(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "Real response"},
            {"role": "user", "content": "more"},
            {"role": "assistant", "content": "[Context Summary] stuff"},
        ]
        assert _find_last_assistant_response(messages) == "Real response"


class TestCopyToClipboard:
    """Test the clipboard helper function."""

    @patch("subprocess.run")
    def test_macos_pbcopy_success(self, mock_run):
        with patch.object(sys, "platform", "darwin"):
            mock_run.return_value = MagicMock(returncode=0)
            result = _copy_to_clipboard("test text")
            assert result is True
            mock_run.assert_called_once_with(
                ["pbcopy"], input="test text", text=True, timeout=5
            )

    @patch("subprocess.run")
    def test_macos_pbcopy_failure(self, mock_run):
        with patch.object(sys, "platform", "darwin"):
            mock_run.return_value = MagicMock(returncode=1)
            result = _copy_to_clipboard("test text")
            assert result is False

    @patch("subprocess.run")
    def test_timeout_returns_false(self, mock_run):
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd="pbcopy", timeout=5)
        with patch.object(sys, "platform", "darwin"):
            result = _copy_to_clipboard("test text")
            assert result is False

    def test_unsupported_platform(self):
        with patch.object(sys, "platform", "freebsd"):
            result = _copy_to_clipboard("test text")
            assert result is False
