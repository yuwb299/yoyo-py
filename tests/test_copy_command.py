"""Tests for /copy command — copy last assistant response to clipboard."""

from __future__ import annotations

import sys
from unittest.mock import patch, MagicMock

import pytest

from src.repl import _copy_to_clipboard, _find_last_assistant_response


class TestFindLastAssistantResponse:
    """Test the helper that finds the last real assistant response."""

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

    def test_skips_error_messages(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "[error: something broke]"},
        ]
        assert _find_last_assistant_response(messages) is None

    def test_skips_interrupted_messages(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "[interrupted]"},
        ]
        assert _find_last_assistant_response(messages) is None

    def test_skips_compact_summaries(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "[Summary of previous conversation]: stuff"},
            {"role": "user", "content": "hi"},
        ]
        assert _find_last_assistant_response(messages) is None

    def test_skips_empty_content(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": ""},
        ]
        assert _find_last_assistant_response(messages) is None

    def test_skips_none_content(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "1"}]},
        ]
        assert _find_last_assistant_response(messages) is None

    def test_finds_real_response_before_error(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "Real response"},
            {"role": "user", "content": "more"},
            {"role": "assistant", "content": "[error: API failed]"},
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
    def test_linux_xclip_success(self, mock_run):
        with patch.object(sys, "platform", "linux"):
            mock_run.return_value = MagicMock(returncode=0)
            result = _copy_to_clipboard("test text")
            assert result is True

    @patch("subprocess.run")
    def test_linux_no_clipboard_tool(self, mock_run):
        import subprocess as sp
        mock_run.side_effect = FileNotFoundError("xclip not found")
        with patch.object(sys, "platform", "linux"):
            result = _copy_to_clipboard("test text")
            assert result is False

    @patch("subprocess.run")
    def test_windows_clip_success(self, mock_run):
        with patch.object(sys, "platform", "win32"):
            mock_run.return_value = MagicMock(returncode=0)
            result = _copy_to_clipboard("test text")
            assert result is True
            mock_run.assert_called_once_with(
                ["clip"], input="test text", text=True, timeout=5
            )

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
