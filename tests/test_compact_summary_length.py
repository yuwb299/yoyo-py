"""Tests for compact summary length capping — summary should not blow up token budget."""

import pytest
from src.agent import Agent


def test_compact_summary_caps_total_length():
    """Summary of many messages should not exceed a reasonable total length."""
    messages = [{"role": "system", "content": "You are helpful"}]
    for i in range(100):
        messages.append({"role": "user", "content": f"Question {i}: " + "x" * 300})
        messages.append({"role": "assistant", "content": f"Answer {i}: " + "y" * 300})

    compacted = Agent._compact_messages(messages, keep_recent=4)
    summary = compacted[1]  # The summary message
    # Summary should be at most ~4000 chars (our _COMPACT_SUMMARY_MAX)
    assert len(summary["content"]) <= 4500, f"Summary too long: {len(summary['content'])} chars"


def test_compact_summary_still_includes_recent_messages():
    """Recent messages should not be affected by summary truncation."""
    messages = [{"role": "system", "content": "You are helpful"}]
    for i in range(50):
        messages.append({"role": "user", "content": f"Q{i}"})
        messages.append({"role": "assistant", "content": f"A{i}"})
    # Add identifiable recent messages
    messages.append({"role": "user", "content": "RECENT_Q"})
    messages.append({"role": "assistant", "content": "RECENT_A"})

    compacted = Agent._compact_messages(messages, keep_recent=4)
    # Last 4 messages should be preserved
    contents = [m.get("content", "") for m in compacted]
    assert any("RECENT_Q" in c for c in contents)
    assert any("RECENT_A" in c for c in contents)


def test_compact_summary_for_short_conversations():
    """Short conversations should not be compacted at all."""
    messages = [
        {"role": "system", "content": "You are helpful"},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]
    compacted = Agent._compact_messages(messages, keep_recent=4)
    # No compaction needed — messages are short
    assert len(compacted) == 3


def test_compact_summary_preserves_system_prompt():
    """System prompt must always be first after compaction."""
    messages = [
        {"role": "system", "content": "You are helpful"},
    ]
    for i in range(20):
        messages.append({"role": "user", "content": f"Q{i}: " + "x" * 200})
        messages.append({"role": "assistant", "content": f"A{i}: " + "y" * 200})

    compacted = Agent._compact_messages(messages, keep_recent=4)
    assert compacted[0]["role"] == "system"
    assert compacted[0]["content"] == "You are helpful"


def test_compact_summary_truncation_indicator():
    """When summary is truncated, it should indicate how many messages were skipped."""
    messages = [{"role": "system", "content": "You are helpful"}]
    for i in range(200):
        messages.append({"role": "user", "content": f"Q{i}: " + "x" * 300})
        messages.append({"role": "assistant", "content": f"A{i}: " + "y" * 300})

    compacted = Agent._compact_messages(messages, keep_recent=4)
    summary = compacted[1]["content"]
    # Should indicate truncation
    assert "... (" in summary or "more messages" in summary


def test_compact_estimate_tokens_with_large_summary():
    """Token estimation of compacted messages should be much smaller than original."""
    messages = [{"role": "system", "content": "You are helpful"}]
    for i in range(200):
        messages.append({"role": "user", "content": f"Q{i}: " + "x" * 500})
        messages.append({"role": "assistant", "content": f"A{i}: " + "y" * 500})

    original_tokens = Agent._estimate_tokens(messages)
    compacted = Agent._compact_messages(messages, keep_recent=4)
    compacted_tokens = Agent._estimate_tokens(compacted)

    # Compacted should be dramatically smaller (at least 10x)
    assert compacted_tokens < original_tokens / 10, \
        f"Compacted tokens {compacted_tokens} not much smaller than original {original_tokens}"
