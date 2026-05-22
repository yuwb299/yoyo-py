"""Tests for auto-compact feature — context window management."""

import pytest
from src.agent import Agent, AgentState
from src.provider import Usage


class TestContextCompaction:
    """Test that the agent auto-compacts when context grows too large."""

    def test_estimate_tokens(self):
        """Token estimation is reasonable for typical text."""
        # Rough estimate: ~3 chars per token
        state = AgentState()
        state.messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello world"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        tokens = Agent._estimate_tokens(state.messages)
        assert tokens > 0
        # Should be roughly proportional to content length
        total_chars = sum(len(m.get("content", "")) for m in state.messages)
        assert tokens >= total_chars // 4  # At least a reasonable fraction

    def test_should_compact_under_threshold(self):
        """Under the threshold, compaction is not needed."""
        state = AgentState()
        state.messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        assert not Agent._should_compact(state.messages, max_tokens=100000)

    def test_should_compact_over_threshold(self):
        """Over the threshold, compaction is needed."""
        state = AgentState()
        # Create a very long conversation
        state.messages = [
            {"role": "system", "content": "You are helpful."},
        ]
        # Add many large messages to exceed threshold
        for i in range(100):
            state.messages.append({"role": "user", "content": "X" * 1000})
            state.messages.append({"role": "assistant", "content": "Y" * 1000})
        assert Agent._should_compact(state.messages, max_tokens=10000)

    def test_compact_preserves_system_prompt(self):
        """Compaction should always keep the system prompt."""
        messages = [
            {"role": "system", "content": "You are a coding assistant."},
            {"role": "user", "content": "A" * 1000},
            {"role": "assistant", "content": "B" * 1000},
            {"role": "user", "content": "C" * 1000},
            {"role": "assistant", "content": "D" * 1000},
        ]
        result = Agent._compact_messages(messages, keep_recent=2)
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "You are a coding assistant."

    def test_compact_keeps_recent_messages(self):
        """Compaction should keep the N most recent non-system messages."""
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "old1"},
            {"role": "assistant", "content": "old2"},
            {"role": "user", "content": "recent1"},
            {"role": "assistant", "content": "recent2"},
        ]
        result = Agent._compact_messages(messages, keep_recent=2)
        # Should have: system, summary, recent1, recent2
        assert len(result) < len(messages)
        assert result[-1]["content"] == "recent2"
        assert result[-2]["content"] == "recent1"

    def test_compact_includes_summary(self):
        """Compaction should include a summary of removed messages."""
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "old question"},
            {"role": "assistant", "content": "old answer"},
            {"role": "user", "content": "recent question"},
            {"role": "assistant", "content": "recent answer"},
        ]
        result = Agent._compact_messages(messages, keep_recent=2)
        # There should be a summary message between system and recent
        summary_msgs = [m for m in result if m["role"] == "system" and "summary" in m.get("content", "").lower()]
        # Or a user message with summary
        has_summary = any("summary" in m.get("content", "").lower() or "previous" in m.get("content", "").lower() for m in result)
        assert has_summary, f"No summary found in compacted messages: {result}"

    def test_compact_empty_messages(self):
        """Compacting empty or minimal messages should be safe."""
        messages = [
            {"role": "system", "content": "System"},
        ]
        result = Agent._compact_messages(messages, keep_recent=2)
        assert result[0]["role"] == "system"
        # Should not crash even with nothing to compact

    def test_compact_all_recent(self):
        """If all messages are 'recent', no compaction needed."""
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "msg2"},
        ]
        result = Agent._compact_messages(messages, keep_recent=10)
        # All messages kept, no summary added
        assert len(result) == len(messages)
