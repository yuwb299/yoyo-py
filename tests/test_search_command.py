"""Tests for /search command — conversation keyword search."""

import pytest


def _make_messages():
    """Create a sample conversation for testing."""
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "How do I read a file in Python?"},
        {"role": "assistant", "content": "You can use open() or pathlib.Path.read_text()."},
        {"role": "user", "content": "What about writing files?"},
        {"role": "assistant", "content": "Use open() with 'w' mode or pathlib.Path.write_text()."},
        {"role": "tool", "tool_call_id": "tc1", "content": "file.txt contents here"},
    ]


def _run_search(messages, keyword, case_sensitive=False):
    """Helper to call _search_conversation directly."""
    from src.repl import _search_conversation
    return _search_conversation(messages, keyword, case_sensitive=case_sensitive)


class TestSearchConversation:
    """Test the _search_conversation helper function."""

    def test_basic_keyword_match(self):
        msgs = _make_messages()
        result = _run_search(msgs, "file")
        assert "read a file" in result
        assert "writing files" in result

    def test_case_insensitive_by_default(self):
        msgs = _make_messages()
        result = _run_search(msgs, "python")
        assert "Python" in result

    def test_case_sensitive_mode(self):
        msgs = _make_messages()
        result = _run_search(msgs, "Python", case_sensitive=True)
        # "Python" appears in user msg, "python" doesn't appear with exact case
        assert "Python" in result

    def test_no_matches(self):
        msgs = _make_messages()
        result = _run_search(msgs, "nonexistent_keyword")
        assert "No matches" in result

    def test_empty_messages(self):
        result = _run_search([], "anything")
        assert "No messages" in result or "No matches" in result

    def test_empty_keyword(self):
        msgs = _make_messages()
        result = _run_search(msgs, "")
        assert "keyword" in result.lower() or "usage" in result.lower()

    def test_tool_message_content_searched(self):
        msgs = _make_messages()
        result = _run_search(msgs, "contents")
        assert "contents" in result

    def test_system_message_searched(self):
        msgs = _make_messages()
        result = _run_search(msgs, "helpful")
        assert "helpful" in result

    def test_result_includes_role_info(self):
        msgs = _make_messages()
        result = _run_search(msgs, "file")
        assert "user" in result or "👤" in result


class TestSearchSlashCommand:
    """Test /search slash command dispatch."""

    def test_search_dispatch(self):
        """Verify /search is dispatched correctly (not 'Unknown command')."""
        from src.repl import _SLASH_COMMANDS
        assert "/search" in _SLASH_COMMANDS
