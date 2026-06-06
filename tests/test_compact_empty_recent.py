"""Tests for _compact_messages when recent messages are all moved to old.

When orphaned tool handling moves all recent messages into old, the resulting
`recent` list is empty. The summary message must be 'assistant' role (not 'user')
because the next message in the conversation will be a user message, and
consecutive user messages cause API errors.
"""

import pytest
from src.agent import Agent


def test_compact_orphaned_tools_all_recent_empty_assistant_role():
    """When all recent msgs are orphaned tools moved to old, summary is assistant."""
    system = [{"role": "system", "content": "You are helpful."}]
    old_msgs = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "q3"},
        {"role": "assistant", "content": "a3"},
    ]
    # Recent: only tool responses whose matching assistant messages are in old.
    # The orphan handler will move them all to old, leaving recent empty.
    recent = [
        {"role": "tool", "tool_call_id": "tc_1", "content": "result 1"},
        {"role": "tool", "tool_call_id": "tc_2", "content": "result 2"},
    ]

    all_msgs = system + old_msgs + recent
    result = Agent._compact_messages(all_msgs, keep_recent=2)

    # Should be: system + summary(assistant) [+ nothing, recent is empty]
    assert len(result) == 2
    summary_msg = result[1]
    assert summary_msg["role"] == "assistant", (
        f"Summary should be 'assistant' when recent is empty, "
        f"got '{summary_msg['role']}'"
    )
    assert "[Summary of previous conversation]" in summary_msg["content"]


def test_compact_orphaned_tool_plus_user_assistant_role():
    """When orphaned tool is moved but user msg remains, summary is assistant."""
    system = [{"role": "system", "content": "You are helpful."}]
    old_msgs = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "q3"},
        {"role": "assistant", "content": "a3"},
    ]
    recent = [
        {"role": "tool", "tool_call_id": "tc_1", "content": "result 1"},
        {"role": "user", "content": "next question"},
    ]

    all_msgs = system + old_msgs + recent
    result = Agent._compact_messages(all_msgs, keep_recent=2)

    # The orphaned tool gets moved to old; user msg stays in recent
    # Recent starts with user, so summary should be assistant
    summary_msg = result[1]
    assert summary_msg["role"] == "assistant", (
        f"Summary should be 'assistant' when recent starts with user, "
        f"got '{summary_msg['role']}'"
    )


def test_compact_normal_recent_assistant_start_user_role():
    """When recent starts with assistant, summary should be 'user' role."""
    system = [{"role": "system", "content": "You are helpful."}]
    old_msgs = [
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "old question 2"},
        {"role": "assistant", "content": "old answer 2"},
        {"role": "user", "content": "old question 3"},
        {"role": "assistant", "content": "old answer 3"},
    ]
    recent_msgs = [
        {"role": "assistant", "content": "recent answer"},
        {"role": "user", "content": "recent question"},
    ]

    all_msgs = system + old_msgs + recent_msgs
    result = Agent._compact_messages(all_msgs, keep_recent=2)

    summary_msg = result[1]
    assert summary_msg["role"] == "user", (
        f"Summary should be 'user' when recent starts with assistant, "
        f"got '{summary_msg['role']}'"
    )


def test_compact_no_compaction_needed():
    """If messages fit within keep_recent, return as-is."""
    msgs = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
    ]
    result = Agent._compact_messages(msgs, keep_recent=100)
    assert result == msgs


def test_compact_validity_after_orphan_handling():
    """Verify the result passes _validate_messages after orphaned tool compaction."""
    system = [{"role": "system", "content": "You are helpful."}]
    old_msgs = []
    for i in range(10):
        old_msgs.append({"role": "user", "content": f"q{i}"})
        old_msgs.append({"role": "assistant", "content": f"a{i}"})

    # Orphaned tools — all get moved to old, recent empty
    recent = [
        {"role": "tool", "tool_call_id": "tc_1", "content": "r1"},
        {"role": "tool", "tool_call_id": "tc_2", "content": "r2"},
    ]

    all_msgs = system + old_msgs + recent
    result = Agent._compact_messages(all_msgs, keep_recent=2)

    issues = Agent._validate_messages(result)
    assert not issues, f"Validation issues: {issues}"
