"""Tests for improved error handling in the agent — APIError classification reaches the user."""

import asyncio
import pytest
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


async def _collect_events(agent, user_input):
    events = []
    async for event in agent.prompt(user_input):
        events.append(event)
    return events


class TestAgentAPIErrorHandling:
    def test_rate_limit_error_gives_helpful_message(self):
        """Rate limit errors should tell the user it's temporary."""
        mock_provider = MagicMock()
        mock_provider.chat.side_effect = APIError(
            "Rate limited: too many requests",
            category="rate_limit",
            retryable=True,
        )
        mock_provider.parse_usage = _mock_parse_usage

        agent = Agent(provider=mock_provider, system_prompt="test")
        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent, "hello"))

        error_events = [(e, d) for e, d in events if e == AgentEvent.ERROR]
        assert len(error_events) == 1
        # Error message should contain the category for helpfulness
        assert "rate_limit" in error_events[0][1]

    def test_auth_error_gives_clear_message(self):
        """Auth errors should tell the user to check their API key."""
        mock_provider = MagicMock()
        mock_provider.chat.side_effect = APIError(
            "Authentication failed: invalid API key",
            category="auth",
            retryable=False,
        )
        mock_provider.parse_usage = _mock_parse_usage

        agent = Agent(provider=mock_provider, system_prompt="test")
        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent, "hello"))

        error_events = [(e, d) for e, d in events if e == AgentEvent.ERROR]
        assert len(error_events) == 1
        assert "auth" in error_events[0][1]

    def test_generic_exception_still_caught(self):
        """Non-APIError exceptions should still be caught gracefully."""
        mock_provider = MagicMock()
        mock_provider.chat.side_effect = RuntimeError("Something unexpected")
        mock_provider.parse_usage = _mock_parse_usage

        agent = Agent(provider=mock_provider, system_prompt="test")
        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent, "hello"))

        error_events = [(e, d) for e, d in events if e == AgentEvent.ERROR]
        assert len(error_events) == 1
        assert "unexpected" in error_events[0][1].lower() or "Something unexpected" in error_events[0][1]

    def test_api_error_preserves_category(self):
        """APIError.category should be accessible in the error event data."""
        mock_provider = MagicMock()
        mock_provider.chat.side_effect = APIError(
            "Connection error",
            category="connection",
            retryable=True,
        )
        mock_provider.parse_usage = _mock_parse_usage

        agent = Agent(provider=mock_provider, system_prompt="test")
        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent, "hello"))

        error_events = [(e, d) for e, d in events if e == AgentEvent.ERROR]
        assert len(error_events) == 1
        # The error message should include the category for user awareness
        assert "connection" in error_events[0][1]
