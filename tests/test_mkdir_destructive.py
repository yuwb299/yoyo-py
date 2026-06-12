"""Test that mkdir is classified as a destructive tool (requires confirmation)."""

from src.agent import Agent


def test_mkdir_in_destructive_tools():
    """mkdir creates directories — it should be in DESTRUCTIVE_TOOLS."""
    assert "mkdir" in Agent.DESTRUCTIVE_TOOLS, (
        "mkdir should require user confirmation before creating directories"
    )


def test_mkdir_not_in_read_only_tools():
    """mkdir modifies filesystem — it should NOT be in READ_ONLY_TOOLS."""
    assert "mkdir" not in Agent.READ_ONLY_TOOLS


def test_mkdir_classified():
    """mkdir should be classified in exactly one category (destructive)."""
    all_tools = {"bash", "read_file", "write_file", "edit_file", "search",
                 "list_files", "mkdir", "glob", "copy_file", "rename"}
    classified = Agent.DESTRUCTIVE_TOOLS | Agent.READ_ONLY_TOOLS
    unclassified = all_tools - classified
    # All tools should be classified
    assert not unclassified, (
        f"These tools are neither destructive nor read-only: {unclassified}. "
        f"Every tool should be in at least one category."
    )
