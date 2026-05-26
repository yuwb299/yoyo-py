"""Tests for improved _estimate_tokens that includes tool_calls arguments."""

import json
import pytest
from src.agent import Agent


class TestEstimateTokensWithToolCalls:
    """Token estimation should account for tool_calls arguments, not just content."""

    def test_basic_text_only(self):
        """Simple text messages: estimation works as before."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello world"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        tokens = Agent._estimate_tokens(messages)
        assert tokens > 0
        # Should be roughly content length / 3
        total_chars = sum(len(m.get("content") or "") for m in messages)
        assert abs(tokens - total_chars // 3) <= 1

    def test_tool_calls_arguments_counted(self):
        """Tool calls with large arguments should increase token count."""
        large_args = json.dumps({"command": "x" * 9000})
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Do something"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "bash",
                        "arguments": large_args,
                    },
                }],
            },
        ]
        tokens = Agent._estimate_tokens(messages)
        # The large args (9000+ chars) must contribute to the estimate
        assert tokens > 2000, f"Tool call args not counted: got {tokens} tokens for ~9000 char args"

    def test_tool_response_content_counted(self):
        """Tool response content should be counted normally (it's in 'content')."""
        messages = [
            {"role": "system", "content": "System"},
            {"role": "tool", "tool_call_id": "call_1", "content": "x" * 3000},
        ]
        tokens = Agent._estimate_tokens(messages)
        assert tokens >= 1000

    def test_multiple_tool_calls(self):
        """Multiple tool calls in one message should all be counted."""
        large_args = json.dumps({"command": "x" * 3000})
        messages = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "bash", "arguments": large_args},
                    },
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path": "/some/file.txt"}'},
                    },
                ],
            },
        ]
        tokens = Agent._estimate_tokens(messages)
        # Both tool call arguments should be counted
        assert tokens > 1000

    def test_none_content_handled(self):
        """Messages with None content and no tool_calls should not crash."""
        messages = [
            {"role": "assistant", "content": None},
        ]
        tokens = Agent._estimate_tokens(messages)
        assert tokens == 0

    def test_empty_messages_list(self):
        """Empty message list returns 0."""
        tokens = Agent._estimate_tokens([])
        assert tokens == 0
