"""Tests for agent stream error preserving partial assistant content.

When a stream errors mid-way (after some text has been streamed), the agent
saves the partial content + an [error: ...] marker into the message history
so the conversation stays valid. This exercises the conditional expression
at the error-handling site.
"""

import asyncio
from unittest.mock import MagicMock

from src.agent import Agent, AgentEvent
from src.provider import APIError, Usage


def _mock_parse_usage(response):
    if hasattr(response, "usage") and response.usage:
        return Usage(
            input_tokens=getattr(response.usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(response.usage, "completion_tokens", 0) or 0,
        )
    return Usage()


class _ErrorAfterTextChunk:
    """Mimics a stream that yields one text delta then raises.

    Used to force the agent down the 'partial assistant content + error' path.
    """


async def _collect_events(agent, user_input):
    events = []
    async for event in agent.prompt(user_input):
        events.append(event)
    return events


class TestStreamErrorPartialContent:
    def test_error_with_partial_content_preserves_text(self):
        """If text streamed before an error, the saved message includes it."""
        mock_provider = MagicMock()
        mock_provider.parse_usage = _mock_parse_usage

        # Simulate a streaming generator that yields text, then raises.
        def fake_chat(*args, **kwargs):
            def _gen():
                chunk = MagicMock()
                chunk.usage = None
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = "partial response"
                chunk.choices[0].delta.tool_calls = None
                chunk.choices[0].finish_reason = None
                yield chunk
                raise RuntimeError("stream broke")
            return _gen()

        mock_provider.chat = fake_chat

        agent = Agent(provider=mock_provider, system_prompt="test")
        events = asyncio.new_event_loop().run_until_complete(
            _collect_events(agent, "hello")
        )

        # An error event must have been emitted
        error_events = [d for e, d in events if e == AgentEvent.ERROR]
        assert len(error_events) == 1
        assert "stream broke" in error_events[0]

        # The saved assistant message must include the partial text + error marker
        # (the last user-facing message before the tool loop is the assistant turn)
        assistant_msgs = [
            m for m in agent.state.messages if m.get("role") == "assistant"
        ]
        assert assistant_msgs, "expected a saved assistant message"
        content = assistant_msgs[-1].get("content", "")
        assert "partial response" in content, (
            f"partial text lost; content was: {content!r}"
        )
        assert "[error:" in content, (
            f"error marker lost; content was: {content!r}"
        )

    def test_error_with_no_content_just_marker(self):
        """If nothing streamed before the error, only the marker is saved."""
        mock_provider = MagicMock()
        mock_provider.parse_usage = _mock_parse_usage

        def fake_chat(*args, **kwargs):
            def _gen():
                # Empty chunk (no content) then raise
                chunk = MagicMock()
                chunk.usage = None
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = None
                chunk.choices[0].delta.tool_calls = None
                chunk.choices[0].finish_reason = None
                yield chunk
                raise APIError("boom", category="server", retryable=True)
            return _gen()

        mock_provider.chat = fake_chat

        agent = Agent(provider=mock_provider, system_prompt="test")
        events = asyncio.new_event_loop().run_until_complete(
            _collect_events(agent, "hello")
        )

        assistant_msgs = [
            m for m in agent.state.messages if m.get("role") == "assistant"
        ]
        assert assistant_msgs
        content = assistant_msgs[-1].get("content", "")
        # Should be JUST the marker, no leading garbage / None concatenation
        assert content.startswith("[error:")
