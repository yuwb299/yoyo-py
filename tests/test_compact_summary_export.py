"""Tests for compact summary handling in export and /redo."""

import pytest
from src.repl import (
    _export_conversation_markdown,
    _find_last_user_message,
)


class TestCompactSummaryExport:
    """Compact summaries should not appear as raw messages in exports."""

    def test_user_role_summary_skipped_in_export(self):
        """User-role compact summaries should be shown as '(compacted summary)'."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "[Summary of previous conversation]:\n[user]: hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        md = _export_conversation_markdown(messages)
        assert "hello" not in md
        assert "compacted" in md.lower() or "summary" in md.lower()

    def test_assistant_role_summary_skipped_in_export(self):
        """Assistant-role compact summaries should also be shown as '(compacted summary)'."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "assistant", "content": "[Summary of previous conversation]:\n[user]: hello"},
            {"role": "user", "content": "What's next?"},
            {"role": "assistant", "content": "Nothing much"},
        ]
        md = _export_conversation_markdown(messages)
        # The raw summary content should not appear as a regular assistant message
        assert "[Summary of previous conversation]" not in md or "compacted" in md.lower()

    def test_normal_assistant_message_preserved(self):
        """Non-summary assistant messages should be exported normally."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there! How can I help?"},
        ]
        md = _export_conversation_markdown(messages)
        assert "Hi there! How can I help?" in md

    def test_normal_user_message_preserved(self):
        """Non-summary user messages should be exported normally."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello world"},
            {"role": "assistant", "content": "Hi"},
        ]
        md = _export_conversation_markdown(messages)
        assert "Hello world" in md


class TestFindLastUserMessage:
    """Ensure _find_last_user_message skips compact summaries."""

    def test_skips_user_role_summary(self):
        """Should skip user-role compact summaries."""
        messages = [
            {"role": "user", "content": "first message"},
            {"role": "assistant", "content": "response"},
            {"role": "user", "content": "[Summary of previous conversation]:\nstuff"},
            {"role": "assistant", "content": "more response"},
        ]
        result = _find_last_user_message(messages)
        assert result == "first message"

    def test_skips_assistant_role_summary(self):
        """Assistant-role summaries aren't user messages, so they're naturally skipped."""
        messages = [
            {"role": "user", "content": "first message"},
            {"role": "assistant", "content": "[Summary of previous conversation]:\nstuff"},
            {"role": "user", "content": "second message"},
            {"role": "assistant", "content": "response"},
        ]
        result = _find_last_user_message(messages)
        assert result == "second message"

    def test_no_real_user_message(self):
        """Returns None if only summaries exist."""
        messages = [
            {"role": "user", "content": "[Summary of previous conversation]:\nstuff"},
            {"role": "assistant", "content": "response"},
        ]
        result = _find_last_user_message(messages)
        assert result is None
