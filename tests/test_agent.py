"""Tests for yoyo-py agent core."""

import pytest
from src.agent import Agent, AgentEvent
from src.provider import Usage


class TestUsage:
    def test_default(self):
        u = Usage()
        assert u.input_tokens == 0
        assert u.output_tokens == 0

    def test_add(self):
        u1 = Usage(input_tokens=10, output_tokens=20)
        u2 = Usage(input_tokens=5, output_tokens=15)
        u1.add(u2)
        assert u1.input_tokens == 15
        assert u1.output_tokens == 35

    def test_str(self):
        u = Usage(input_tokens=100, output_tokens=200)
        assert "100" in str(u)
        assert "200" in str(u)


class TestAgent:
    def test_create_agent(self):
        agent = Agent(
            provider=None,  # No provider needed for construction
            system_prompt="You are a test agent.",
        )
        assert len(agent.state.messages) == 1
        assert agent.state.messages[0]["role"] == "system"
        assert agent.state.messages[0]["content"] == "You are a test agent."

    def test_clear(self):
        agent = Agent(
            provider=None,
            system_prompt="Test prompt",
        )
        agent.state.messages.append({"role": "user", "content": "hello"})
        agent.clear()
        assert len(agent.state.messages) == 1
        assert agent.state.messages[0]["role"] == "system"

    def test_register_tool(self):
        agent = Agent(provider=None)
        agent.register_tool(
            "test_tool",
            lambda x: x,
            {"type": "function", "function": {"name": "test_tool", "parameters": {}}},
        )
        assert "test_tool" in agent.tools
        assert len(agent.tool_schemas) == 1

    def test_max_tool_rounds_default(self):
        agent = Agent(provider=None)
        assert agent.state.max_tool_rounds == 20

    def test_max_tool_rounds_custom(self):
        agent = Agent(provider=None, max_tool_rounds=5)
        assert agent.state.max_tool_rounds == 5
