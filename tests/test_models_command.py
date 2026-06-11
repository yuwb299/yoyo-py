"""Test /models REPL command."""
from src.repl import CommandRegistry


def _build_registry_with_models():
    """Build a minimal command registry with the /models command wired up."""
    from src.agent import Agent
    from src.provider import GLMProvider
    from src.tools import TOOL_FUNCTIONS, TOOL_SCHEMAS
    from src.repl import _build_command_registry

    provider = GLMProvider(model="glm-5.1", api_key="test-key")
    agent = Agent(
        provider=provider,
        system_prompt="test",
        tools=TOOL_FUNCTIONS,
        tool_schemas=TOOL_SCHEMAS,
    )
    from src.skills import SkillSet
    skills = SkillSet()
    return _build_command_registry(agent, provider, skills)


def test_models_command_lists_models():
    """/models should list known models with context info."""
    registry = _build_registry_with_models()
    result = registry.dispatch("/models", {})
    assert result.output
    assert "glm-5" in result.output
    assert "gpt-4o" in result.output
    assert "ctx" in result.output.lower()


def test_models_command_shows_current_marker():
    """/models should mark the current model."""
    registry = _build_registry_with_models()
    result = registry.dispatch("/models", {})
    # Should show "current" marker next to the active model
    assert "current" in result.output


def test_models_command_not_done():
    """/models should not exit the REPL."""
    registry = _build_registry_with_models()
    result = registry.dispatch("/models", {})
    assert result.done is False


def test_models_command_no_agent_prompt():
    """/models should not trigger an agent turn."""
    registry = _build_registry_with_models()
    result = registry.dispatch("/models", {})
    assert result.agent_prompt is None
