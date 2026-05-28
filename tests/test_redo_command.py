"""Tests for /redo command — re-send last user message."""

from src.agent import Agent, AgentEvent, AgentState
from src.provider import Usage


def _make_mock_provider(responses):
    """Create a mock provider that returns canned responses."""
    class MockProvider:
        def __init__(self):
            self.model = "mock-model"
            self.call_count = 0

        def chat(self, messages, tools=None, stream=True):
            self.call_count += 1
            # Return a simple text response
            return iter([_make_text_chunk("Mock response")])

        @staticmethod
        def parse_usage(response):
            return Usage()

    return MockProvider()


def _make_text_chunk(text):
    """Create a mock stream chunk with text content."""
    class MockDelta:
        def __init__(self, content):
            self.content = content
            self.tool_calls = None

    class MockChoice:
        def __init__(self, delta):
            self.delta = delta
            self.finish_reason = "stop"

    class MockChunk:
        def __init__(self, text):
            self.choices = [MockChoice(MockDelta(text))]
            self.usage = None

    return MockChunk(text)


def test_redo_finds_last_user_message():
    """_find_last_user_message should return the last user message content."""
    from src.repl import _find_last_user_message

    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "second question"},
        {"role": "assistant", "content": "second answer"},
    ]
    result = _find_last_user_message(messages)
    assert result == "second question"


def test_redo_finds_last_user_message_with_tools():
    """_find_last_user_message should skip tool messages and find last user message."""
    from src.repl import _find_last_user_message

    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "read the file"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "1", "function": {"name": "read_file", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "1", "content": "file contents"},
        {"role": "assistant", "content": "Here's the file"},
    ]
    result = _find_last_user_message(messages)
    assert result == "read the file"


def test_redo_returns_none_for_no_user_messages():
    """_find_last_user_message should return None if no user messages exist."""
    from src.repl import _find_last_user_message

    messages = [
        {"role": "system", "content": "system prompt"},
    ]
    result = _find_last_user_message(messages)
    assert result is None


def test_redo_returns_none_for_empty_messages():
    """_find_last_user_message should return None for empty message list."""
    from src.repl import _find_last_user_message

    result = _find_last_user_message([])
    assert result is None


def test_redo_ignores_summary_user_message():
    """_find_last_user_message should skip compact summary messages."""
    from src.repl import _find_last_user_message

    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "[Summary of previous conversation]:\n[system]: stuff"},
        {"role": "user", "content": "real question"},
        {"role": "assistant", "content": "answer"},
    ]
    result = _find_last_user_message(messages)
    assert result == "real question"


def test_redo_ignores_only_summary_messages():
    """If only summary user messages exist, return None (nothing to redo)."""
    from src.repl import _find_last_user_message

    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "[Summary of previous conversation]:\n[system]: stuff"},
    ]
    result = _find_last_user_message(messages)
    assert result is None
