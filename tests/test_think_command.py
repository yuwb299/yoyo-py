"""Tests for /think command and reasoning_effort provider support."""

import pytest

from src.provider import GLMProvider, FailoverProvider, Usage
from src.repl import CommandRegistry, CommandResult, _format_status_output
from src.agent import Agent
from src.skills import SkillSet


# ANSI codes for test helpers
RESET = "\x1b[0m"
YELLOW = "\x1b[33m"
DIM = "\x1b[2m"
GREEN = "\x1b[32m"


# ── Helpers ────────────────────────────────────────────────────────

def _make_provider(**kwargs):
    """Create a GLMProvider with test defaults."""
    return GLMProvider(
        api_key="test-key",
        base_url="https://test.example.com/v1",
        model="test-model",
        **kwargs,
    )


def _make_registry_and_provider():
    """Build a command registry with /think command, returning (registry, provider)."""
    provider = _make_provider()
    agent = Agent(provider=provider, system_prompt="test")
    skills = SkillSet()
    registry = CommandRegistry()

    @registry.register("think")
    def _cmd_think(line: str, ctx: dict):
        effort = line[6:].strip().lower() if len(line) > 6 else ""
        valid_efforts = {"low", "medium", "high"}
        if effort == "off":
            provider.reasoning_effort = None
            return CommandResult(output=f"{DIM}  Reasoning effort: off (use API default){RESET}\n")
        if effort == "" or effort == "show":
            current = provider.reasoning_effort or "default"
            return CommandResult(output=f"{DIM}  Reasoning effort: {current}{RESET}\n")
        if effort not in valid_efforts:
            return CommandResult(
                output=f"{YELLOW}Usage: /think [low|medium|high|off]{RESET}\n"
                f"{DIM}  Current: {provider.reasoning_effort or 'default'}{RESET}\n"
            )
        provider.reasoning_effort = effort
        return CommandResult(output=f"{GREEN}  ✓ Reasoning effort set to {effort}{RESET}\n")

    return registry, provider


def _run(registry, line):
    """Dispatch a command through the registry."""
    return registry.dispatch(line, ctx={})


class TestReasoningEffortProvider:
    """Test that GLMProvider supports reasoning_effort attribute."""

    def test_default_reasoning_effort_is_none(self):
        provider = _make_provider()
        assert provider.reasoning_effort is None

    def test_set_reasoning_effort(self):
        provider = _make_provider()
        provider.reasoning_effort = "high"
        assert provider.reasoning_effort == "high"

    def test_reasoning_effort_values(self):
        provider = _make_provider()
        for value in ("low", "medium", "high"):
            provider.reasoning_effort = value
            assert provider.reasoning_effort == value

    def test_reasoning_effort_can_be_cleared(self):
        provider = _make_provider()
        provider.reasoning_effort = "high"
        provider.reasoning_effort = None
        assert provider.reasoning_effort is None


class TestReasoningEffortFailover:
    """Test that FailoverProvider propagates reasoning_effort."""

    def test_failover_exposes_reasoning_effort(self):
        p1 = _make_provider()
        p1.reasoning_effort = "high"
        p2 = _make_provider()
        failover = FailoverProvider([p1, p2])
        assert failover.reasoning_effort == "high"

    def test_failover_default_is_none(self):
        p1 = _make_provider()
        p2 = _make_provider()
        failover = FailoverProvider([p1, p2])
        assert failover.reasoning_effort is None

    def test_failover_settable(self):
        p1 = _make_provider()
        p2 = _make_provider()
        failover = FailoverProvider([p1, p2])
        failover.reasoning_effort = "low"
        assert failover.reasoning_effort == "low"


class TestThinkCommand:
    """Test /think slash command dispatch."""

    def test_think_set_high(self):
        registry, provider = _make_registry_and_provider()
        result = _run(registry, "/think high")
        assert isinstance(result, CommandResult)
        assert "high" in result.output
        assert provider.reasoning_effort == "high"

    def test_think_set_low(self):
        registry, provider = _make_registry_and_provider()
        _run(registry, "/think low")
        assert provider.reasoning_effort == "low"

    def test_think_set_medium(self):
        registry, provider = _make_registry_and_provider()
        _run(registry, "/think medium")
        assert provider.reasoning_effort == "medium"

    def test_think_off(self):
        registry, provider = _make_registry_and_provider()
        provider.reasoning_effort = "high"
        result = _run(registry, "/think off")
        assert provider.reasoning_effort is None
        assert "off" in result.output

    def test_think_show_current(self):
        registry, provider = _make_registry_and_provider()
        provider.reasoning_effort = "medium"
        result = _run(registry, "/think")
        assert "medium" in result.output

    def test_think_invalid(self):
        registry, provider = _make_registry_and_provider()
        result = _run(registry, "/think extreme")
        assert "Usage" in result.output
        assert provider.reasoning_effort is None

    def test_think_show_when_default(self):
        registry, provider = _make_registry_and_provider()
        result = _run(registry, "/think show")
        assert "default" in result.output


class TestReasoningEffortInKwargs:
    """Test that reasoning_effort is included in API call kwargs when set."""

    def test_reasoning_effort_included_when_set(self, monkeypatch):
        provider = _make_provider()
        provider.reasoning_effort = "high"

        captured_kwargs = {}

        def mock_create(**kwargs):
            captured_kwargs.update(kwargs)
            class MockResponse:
                pass
            return MockResponse()

        monkeypatch.setattr(provider.client.chat.completions, "create", mock_create)
        provider.chat(messages=[{"role": "user", "content": "hi"}], stream=False)
        assert captured_kwargs.get("reasoning_effort") == "high"

    def test_reasoning_effort_excluded_when_none(self, monkeypatch):
        provider = _make_provider()
        assert provider.reasoning_effort is None

        captured_kwargs = {}

        def mock_create(**kwargs):
            captured_kwargs.update(kwargs)
            class MockResponse:
                pass
            return MockResponse()

        monkeypatch.setattr(provider.client.chat.completions, "create", mock_create)
        provider.chat(messages=[{"role": "user", "content": "hi"}], stream=False)
        assert "reasoning_effort" not in captured_kwargs

    def test_all_effort_levels_in_kwargs(self, monkeypatch):
        """Each valid level is correctly passed through."""
        for level in ("low", "medium", "high"):
            provider = _make_provider()
            provider.reasoning_effort = level

            captured_kwargs = {}

            def mock_create(**kwargs):
                captured_kwargs.update(kwargs)
                class MockResponse:
                    pass
                return MockResponse()

            monkeypatch.setattr(provider.client.chat.completions, "create", mock_create)
            provider.chat(messages=[{"role": "user", "content": "hi"}], stream=False)
            assert captured_kwargs["reasoning_effort"] == level


class TestStatusShowsThinking:
    """Test that /status shows reasoning effort when set."""

    def test_status_includes_thinking(self):
        output = _format_status_output(
            model="test-model",
            cwd="/tmp",
            messages=[],
            usage=Usage(),
            skills_count=0,
            context_tokens=0,
            reasoning_effort="high",
        )
        assert "thinking" in output
        assert "high" in output

    def test_status_omits_thinking_when_default(self):
        output = _format_status_output(
            model="test-model",
            cwd="/tmp",
            messages=[],
            usage=Usage(),
            skills_count=0,
            context_tokens=0,
            reasoning_effort=None,
        )
        assert "thinking" not in output
