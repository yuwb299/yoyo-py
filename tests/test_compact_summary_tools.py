"""Tests for improved compact summary that includes tool call names."""

import pytest
from src.agent import Agent


class TestCompactSummaryWithToolCalls:
    """Compacted summaries should mention what tools were called."""

    def test_summary_includes_tool_names(self):
        """When assistant messages with tool_calls are compacted, the summary
        should include tool names so the agent remembers what it did."""
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Read the README"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "README.md"}'},
                }],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "# My Project\nA cool project."},
            {"role": "user", "content": "Now edit it"},
            {"role": "assistant", "content": "Done editing!"},
        ]
        result = Agent._compact_messages(messages, keep_recent=2)

        # The summary should mention read_file
        summary_msg = [m for m in result if "Summary" in m.get("content", "")]
        assert summary_msg, f"No summary message found in: {result}"
        assert "read_file" in summary_msg[0]["content"], (
            f"Summary should mention tool names but got: {summary_msg[0]['content']}"
        )

    def test_summary_includes_multiple_tool_names(self):
        """Multiple tool calls in one message should all be named."""
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Read and search"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path": "a.py"}'},
                    },
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {"name": "search", "arguments": '{"pattern": "TODO"}'},
                    },
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "file contents"},
            {"role": "tool", "tool_call_id": "call_2", "content": "no matches"},
            {"role": "user", "content": "Now fix it"},
            {"role": "assistant", "content": "Fixed!"},
        ]
        result = Agent._compact_messages(messages, keep_recent=2)
        summary_msg = [m for m in result if "Summary" in m.get("content", "")]
        assert summary_msg
        assert "read_file" in summary_msg[0]["content"]
        assert "search" in summary_msg[0]["content"]

    def test_summary_preserves_text_content_with_tool_calls(self):
        """When assistant has both text content AND tool calls, both appear."""
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Help me"},
            {
                "role": "assistant",
                "content": "I'll read the file first.",
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "a.py"}'},
                }],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "contents"},
            {"role": "user", "content": "Continue"},
            {"role": "assistant", "content": "Done!"},
        ]
        result = Agent._compact_messages(messages, keep_recent=2)
        summary_msg = [m for m in result if "Summary" in m.get("content", "")]
        assert summary_msg
        assert "read_file" in summary_msg[0]["content"]
        assert "I'll read the file first." in summary_msg[0]["content"]

    def test_summary_text_only_unchanged(self):
        """Messages without tool calls should still work as before."""
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "Bye"},
            {"role": "assistant", "content": "See you!"},
        ]
        result = Agent._compact_messages(messages, keep_recent=2)
        summary_msg = [m for m in result if "Summary" in m.get("content", "")]
        assert summary_msg
        assert "Hi there!" in summary_msg[0]["content"]
        # No "(called: ...)" for plain text messages
        assert "(called:" not in summary_msg[0]["content"]
