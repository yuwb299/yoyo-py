"""Tests that the rename tool is properly registered and wired up.

Regression test for the bug where tool_rename was implemented and had a schema
but was missing from TOOL_FUNCTIONS — same class of bug as Day 17's mkdir issue.
"""

from src.tools import TOOL_FUNCTIONS, TOOL_SCHEMAS, tool_rename


def test_rename_in_tool_functions():
    """rename must be in TOOL_FUNCTIONS so the agent can call it."""
    assert "rename" in TOOL_FUNCTIONS


def test_rename_function_is_correct():
    """The registered function must be tool_rename."""
    assert TOOL_FUNCTIONS["rename"] is tool_rename


def test_rename_in_tool_schemas():
    """rename must have a schema in TOOL_SCHEMAS."""
    schema_names = [s["function"]["name"] for s in TOOL_SCHEMAS]
    assert "rename" in schema_names


def test_rename_schema_matches_function():
    """The rename schema should have source and destination parameters."""
    schema = next(s for s in TOOL_SCHEMAS if s["function"]["name"] == "rename")
    params = schema["function"]["parameters"]["properties"]
    assert "source" in params
    assert "destination" in params
    required = schema["function"]["parameters"]["required"]
    assert "source" in required
    assert "destination" in required


def test_rename_tool_summary():
    """The rename tool should have a summary in _tool_summary."""
    from src.repl import _tool_summary
    summary = _tool_summary("rename", {"source": "a.txt", "destination": "b.txt"})
    assert "a.txt" in summary
    assert "b.txt" in summary


def test_rename_is_destructive():
    """Rename should be in DESTRUCTIVE_TOOLS since it moves files."""
    from src.agent import Agent
    assert "rename" in Agent.DESTRUCTIVE_TOOLS
