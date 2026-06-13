"""Tests for token usage accounting.

The agent must count each API response's usage exactly once. A regression
caused usage to be double-counted: usage was added for every chunk that
carried it, AND added again on the finish_reason chunk — so APIs that send
usage only on the final chunk (the common case for OpenAI-compatible
endpoints) had their tokens counted twice.
"""

import asyncio
import json
from unittest.mock import MagicMock

from src.agent import Agent, AgentEvent
from src.provider import GLMProvider, Usage


def _make_provider():
    """Mock GLMProvider that doesn't need a real API key."""
    provider = MagicMock(spec=GLMProvider)
    provider.model = "test-model"
    provider.parse_usage = GLMProvider.parse_usage
    return provider


def _run(agent, prompt):
    async def _collect():
        events = []
        async for ev in agent.prompt(prompt):
            events.append(ev)
        return events
    return asyncio.new_event_loop().run_until_complete(_collect())


def _text_chunks(prompt_tokens, completion_tokens):
    """Build a minimal text-only stream ending in a single usage+finish chunk.

    This mirrors how OpenAI-compatible APIs deliver usage: only on the final
    chunk that also carries finish_reason.
    """
    text_chunk = MagicMock()
    text_chunk.choices = [MagicMock()]
    text_chunk.choices[0].delta = MagicMock(content="Hello", tool_calls=None)
    text_chunk.choices[0].finish_reason = None
    text_chunk.usage = None

    final = MagicMock()
    final.choices = [MagicMock()]
    final.choices[0].delta = MagicMock(content=None, tool_calls=None)
    final.choices[0].finish_reason = "stop"
    final.usage = MagicMock()
    final.usage.prompt_tokens = prompt_tokens
    final.usage.completion_tokens = completion_tokens
    return [text_chunk, final]


def test_usage_counted_once_for_single_response():
    """Usage from the final chunk must be counted exactly once."""
    provider = _make_provider()
    provider.chat.return_value = iter(_text_chunks(1000, 200))

    agent = Agent(provider=provider, system_prompt="test")
    _run(agent, "hi")

    # Should be 1000/200, NOT 2000/400 (which would indicate double counting)
    assert agent.state.usage.input_tokens == 1000, (
        f"Expected 1000 input tokens, got {agent.state.usage.input_tokens} "
        f"(likely double-counted)"
    )
    assert agent.state.usage.output_tokens == 200, (
        f"Expected 200 output tokens, got {agent.state.usage.output_tokens} "
        f"(likely double-counted)"
    )


def test_usage_not_double_counted_across_rounds():
    """Two API responses should accumulate to 2x, not more."""
    provider = _make_provider()
    # Each prompt() call makes one chat() call returning the same chunks.
    # Agent returns a new iterator each time provider.chat is called.
    chunks = _text_chunks(500, 100)
    provider.chat.return_value = iter(chunks)

    agent = Agent(provider=provider, system_prompt="test")
    _run(agent, "first")
    # Reset the mock's return value for the second prompt
    provider.chat.return_value = iter(_text_chunks(500, 100))
    _run(agent, "second")

    assert agent.state.usage.input_tokens == 1000
    assert agent.state.usage.output_tokens == 200


def test_usage_from_usage_on_every_chunk():
    """If usage arrives incrementally (rare), it's counted once per chunk,
    never double-added on the finish chunk."""
    # One chunk carries usage with finish_reason — must be added exactly once.
    provider = _make_provider()
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta = MagicMock(content="Hi", tool_calls=None)
    chunk.choices[0].finish_reason = "stop"
    chunk.usage = MagicMock()
    chunk.usage.prompt_tokens = 333
    chunk.usage.completion_tokens = 111
    provider.chat.return_value = iter([chunk])

    agent = Agent(provider=provider, system_prompt="test")
    _run(agent, "hi")

    assert agent.state.usage.input_tokens == 333
    assert agent.state.usage.output_tokens == 111
