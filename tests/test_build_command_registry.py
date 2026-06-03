"""Tests for _build_command_registry — integration tests for slash command handlers.

These tests verify that the command registry built by _build_command_registry
correctly dispatches all registered commands and returns the expected
CommandResult values. The handlers are closures that capture mock agent,
provider, and skills objects, so we test the full integration.
"""

import os
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from src.repl import CommandRegistry, CommandResult, _build_command_registry
from src.agent import Agent, AgentState
from src.provider import GLMProvider, Usage
from src.skills import SkillSet


@pytest.fixture
def mock_provider():
    """Create a mock GLMProvider with all necessary attributes."""
    provider = MagicMock(spec=GLMProvider)
    provider.model = "test-model"
    provider.base_url = "https://api.test.com/v1"
    provider.api_key = "sk-test123456789"
    provider.max_tokens = None
    provider.temperature = 0.7
    provider.top_p = None
    provider._provider_name = "test"
    return provider


@pytest.fixture
def mock_agent():
    """Create a mock Agent with state."""
    agent = MagicMock(spec=Agent)
    agent.state = AgentState()
    agent.state.messages = [{"role": "system", "content": "test"}]
    agent.state.usage = Usage(input_tokens=100, output_tokens=50)
    return agent


@pytest.fixture
def mock_skills():
    """Create a mock SkillSet."""
    skills = MagicMock(spec=SkillSet)
    skills.count.return_value = 3
    skills.is_empty.return_value = False
    skills.all.return_value = [
        ("skill1", "Content for skill 1 that is quite long actually"),
        ("skill2", "Content for skill 2 also quite long"),
    ]
    return skills


@pytest.fixture
def registry(mock_agent, mock_provider, mock_skills):
    """Build a command registry with mocked dependencies."""
    return _build_command_registry(mock_agent, mock_provider, mock_skills)


class TestRegistryCompleteness:
    """Verify all expected commands are registered."""

    EXPECTED_COMMANDS = [
        "quit", "exit", "clear", "help", "redo", "last", "copy",
        "compact", "diff", "undo", "log", "commit", "review", "pr",
        "tree", "health", "test", "fix", "init",
        "status", "tokens", "cost", "history", "search", "system", "env",
        "config", "list-providers",
        "save", "load", "export", "resume",
        "remember", "memories", "forget",
        "skills", "commands",
        "model", "cd", "revert",
    ]

    def test_all_commands_registered(self, registry):
        """All expected slash commands should be registered in the registry."""
        registered = set(registry.list_commands())
        for cmd in self.EXPECTED_COMMANDS:
            assert cmd in registered, f"Command '{cmd}' not registered"


class TestQuitCommand:
    """Test /quit and /exit commands."""

    def test_quit_returns_done(self, registry, mock_agent):
        """/quit returns CommandResult with done=True."""
        result = registry.dispatch("/quit", {})
        assert result.done is True

    def test_exit_alias(self, registry):
        """/exit is an alias for /quit."""
        result = registry.dispatch("/exit", {})
        assert result.done is True

    def test_quit_has_output(self, registry):
        """/quit shows a goodbye message."""
        result = registry.dispatch("/quit", {})
        assert "bye" in result.output


class TestClearCommand:
    """Test /clear command."""

    def test_clear_calls_agent_clear(self, registry, mock_agent):
        """/clear calls agent.clear() and shows confirmation."""
        result = registry.dispatch("/clear", {})
        mock_agent.clear.assert_called_once()
        assert "cleared" in result.output

    def test_clear_not_done(self, registry):
        """/clear does not exit the REPL."""
        result = registry.dispatch("/clear", {})
        assert result.done is False


class TestHelpCommand:
    """Test /help command."""

    def test_help_returns_output(self, registry):
        """/help returns non-empty output."""
        result = registry.dispatch("/help", {})
        assert result.output
        assert result.done is False


class TestRedoCommand:
    """Test /redo command."""

    def test_redo_no_previous_message(self, registry):
        """/redo with no previous user message shows error."""
        result = registry.dispatch("/redo", {})
        assert "No previous" in result.output

    def test_redo_with_previous_message(self, registry, mock_agent):
        """/redo returns the last user message as agent_prompt."""
        mock_agent.state.messages = [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "hello world"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = registry.dispatch("/redo", {})
        assert result.agent_prompt == "hello world"


class TestLastCommand:
    """Test /last command."""

    def test_last_no_previous_response(self, registry):
        """/last with no previous assistant response shows error."""
        result = registry.dispatch("/last", {})
        assert "No previous" in result.output

    def test_last_with_previous_response(self, registry, mock_agent):
        """/last returns the last assistant response."""
        mock_agent.state.messages = [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there!"},
        ]
        result = registry.dispatch("/last", {})
        assert "hi there!" in result.output


class TestCopyCommand:
    """Test /copy command."""

    def test_copy_no_previous_response(self, registry):
        """/copy with no previous response shows error."""
        result = registry.dispatch("/copy", {})
        assert "No previous" in result.output

    def test_copy_with_response(self, registry, mock_agent):
        """/copy attempts clipboard copy and returns result."""
        mock_agent.state.messages = [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there!"},
        ]
        with patch("src.repl._copy_to_clipboard", return_value=True):
            result = registry.dispatch("/copy", {})
            assert "Copied" in result.output


class TestCompactCommand:
    """Test /compact command."""

    def test_compact_shows_reduction(self, registry, mock_agent):
        """/compact shows message count before and after."""
        mock_agent.state.messages = [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ] * 10
        result = registry.dispatch("/compact", {})
        assert "compacted" in result.output


class TestTokensCommand:
    """Test /tokens command."""

    def test_tokens_shows_usage(self, registry):
        """/tokens shows current usage."""
        result = registry.dispatch("/tokens", {})
        assert "100" in result.output  # input_tokens from fixture


class TestCostCommand:
    """Test /cost command."""

    def test_cost_returns_output(self, registry):
        """/cost returns non-empty output."""
        result = registry.dispatch("/cost", {})
        assert result.output


class TestStatusCommand:
    """Test /status command."""

    def test_status_shows_model(self, registry):
        """/status includes model info."""
        result = registry.dispatch("/status", {})
        assert "test-model" in result.output

    def test_status_shows_skills(self, registry):
        """/status shows skills count."""
        result = registry.dispatch("/status", {})
        assert "3" in result.output  # skills.count() from fixture


class TestSkillsCommand:
    """Test /skills command."""

    def test_skills_shows_loaded(self, registry):
        """/skills shows loaded skills."""
        result = registry.dispatch("/skills", {})
        assert "skill1" in result.output

    def test_skills_empty(self, registry, mock_skills):
        """/skills with no skills shows message."""
        mock_skills.is_empty.return_value = True
        reg = _build_command_registry(MagicMock(), MagicMock(), mock_skills)
        result = reg.dispatch("/skills", {})
        assert "No skills" in result.output


class TestModelCommand:
    """Test /model command."""

    def test_model_no_args(self, registry):
        """/model without name shows usage."""
        result = registry.dispatch("/model ", {})
        assert "Usage" in result.output

    def test_model_switches(self, registry, mock_provider):
        """/model switches the provider model."""
        result = registry.dispatch("/model gpt-4o", {})
        assert mock_provider.model == "gpt-4o"
        assert "gpt-4o" in result.output

    def test_model_with_keep(self, registry, mock_provider, mock_agent):
        """/model --keep preserves history."""
        result = registry.dispatch("/model gpt-4o --keep", {})
        assert mock_provider.model == "gpt-4o"
        mock_agent.clear.assert_not_called()
        assert "preserved" in result.output

    def test_model_without_keep_clears(self, registry, mock_provider, mock_agent):
        """/model without --keep clears conversation."""
        result = registry.dispatch("/model gpt-4o", {})
        mock_agent.clear.assert_called_once()


class TestEnvCommand:
    """Test /env command."""

    def test_env_shows_info(self, registry):
        """/env shows provider configuration."""
        result = registry.dispatch("/env", {})
        assert "test-model" in result.output


class TestRevertCommand:
    """Test /revert command."""

    def test_revert_default_count(self, registry, mock_agent):
        """/revert with no args removes 1 exchange."""
        mock_agent.state.messages = [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = registry.dispatch("/revert", {})
        assert result.done is False

    def test_revert_invalid_count(self, registry):
        """/revert with non-numeric count shows usage."""
        result = registry.dispatch("/revert abc", {})
        assert "Usage" in result.output

    def test_revert_zero_count(self, registry):
        """/revert 0 shows error."""
        result = registry.dispatch("/revert 0", {})
        assert "at least 1" in result.output


class TestRememberCommand:
    """Test /remember command."""

    def test_remember_no_text(self, registry):
        """/remember without text shows usage."""
        result = registry.dispatch("/remember", {})
        assert "Usage" in result.output

    def test_remember_with_text(self, registry):
        """/remember calls _add_memory."""
        with patch("src.repl._add_memory", return_value="Added!"):
            result = registry.dispatch("/remember use pytest for testing", {})
            assert "Added!" in result.output


class TestMemoriesCommand:
    """Test /memories command."""

    def test_memories_returns_output(self, registry):
        """/memories calls _list_memories."""
        with patch("src.repl._list_memories", return_value="No memories"):
            result = registry.dispatch("/memories", {})
            assert "No memories" in result.output


class TestForgettingCommand:
    """Test /forget command."""

    def test_forget_no_id(self, registry):
        """/forget without ID shows usage."""
        result = registry.dispatch("/forget", {})
        assert "Usage" in result.output

    def test_forget_invalid_id(self, registry):
        """/forget with non-numeric ID shows error."""
        result = registry.dispatch("/forget abc", {})
        assert "number" in result.output

    def test_forget_valid_id(self, registry):
        """/forget with valid ID calls _forget_memory."""
        with patch("src.repl._forget_memory", return_value="Forgotten!"):
            result = registry.dispatch("/forget 3", {})
            assert "Forgotten!" in result.output


class TestDiffCommand:
    """Test /diff command."""

    def test_diff_returns_output(self, registry):
        """/diff calls _git_diff_summary."""
        with patch("src.repl._git_diff_summary", return_value="no changes"):
            result = registry.dispatch("/diff", {})
            assert "no changes" in result.output


class TestUndoCommand:
    """Test /undo command."""

    def test_undo_returns_output(self, registry):
        """/undo calls _git_undo."""
        with patch("src.repl._git_undo", return_value="reverted"):
            result = registry.dispatch("/undo", {})
            assert "reverted" in result.output


class TestLogCommand:
    """Test /log command."""

    def test_log_default(self, registry):
        """/log shows default 10 entries."""
        with patch("src.repl._run_git_log", return_value="log output") as mock_log:
            result = registry.dispatch("/log", {})
            mock_log.assert_called_once_with(count=10, oneline=False)

    def test_log_with_count(self, registry):
        """/log N shows N entries."""
        with patch("src.repl._run_git_log", return_value="log output") as mock_log:
            result = registry.dispatch("/log 5", {})
            mock_log.assert_called_once_with(count=5, oneline=False)

    def test_log_oneline(self, registry):
        """/log --oneline uses oneline format."""
        with patch("src.repl._run_git_log", return_value="log output") as mock_log:
            result = registry.dispatch("/log --oneline", {})
            mock_log.assert_called_once_with(count=10, oneline=True)


class TestCommitCommand:
    """Test /commit command."""

    def test_commit_no_message(self, registry):
        """/commit without message shows usage."""
        result = registry.dispatch("/commit", {})
        assert "Usage" in result.output

    def test_commit_with_message(self, registry):
        """/commit calls _git_commit with the message."""
        with patch("src.repl._git_commit", return_value="committed!") as mock:
            result = registry.dispatch("/commit fix the bug", {})
            mock.assert_called_once_with("fix the bug")


class TestTreeCommand:
    """Test /tree command."""

    def test_tree_returns_output(self, registry):
        """/tree calls _project_tree."""
        with patch("src.repl._project_tree", return_value="project tree"):
            result = registry.dispatch("/tree", {})
            assert "project tree" in result.output


class TestHealthCommand:
    """Test /health command."""

    def test_health_returns_output(self, registry):
        """/health calls _run_health_check."""
        with patch("src.repl._run_health_check", return_value="all good"):
            result = registry.dispatch("/health", {})
            assert "all good" in result.output


class TestTestCommand:
    """Test /test command."""

    def test_test_returns_output(self, registry):
        """/test calls _run_test_command."""
        with patch("src.repl._run_test_command", return_value="tests pass"):
            result = registry.dispatch("/test", {})
            assert "tests pass" in result.output


class TestFixCommand:
    """Test /fix command."""

    def test_fix_returns_output(self, registry):
        """/fix calls _run_fix_command."""
        with patch("src.repl._run_fix_command", return_value="fixed"):
            result = registry.dispatch("/fix", {})
            assert "fixed" in result.output


class TestInitCommand:
    """Test /init command."""

    def test_init_returns_output(self, registry):
        """/init calls _run_init_command."""
        with patch("src.repl._run_init_command", return_value="initialized"):
            result = registry.dispatch("/init", {})
            assert "initialized" in result.output


class TestReviewCommand:
    """Test /review command."""

    def test_review_bare(self, registry):
        """/review calls _run_review without flags."""
        with patch("src.repl._run_review", return_value="review prompt"):
            result = registry.dispatch("/review", {})
            assert result.agent_prompt == "review prompt"

    def test_review_commit_flag(self, registry):
        """/review --commit passes commit=True."""
        with patch("src.repl._run_review", return_value="review prompt") as mock:
            result = registry.dispatch("/review --commit", {})
            mock.assert_called_once_with(commit=True)

    def test_review_staged_flag(self, registry):
        """/review --staged passes staged=True."""
        with patch("src.repl._run_review", return_value="review prompt") as mock:
            result = registry.dispatch("/review --staged", {})
            mock.assert_called_once_with(staged=True)

    def test_review_error_message(self, registry):
        """/review with error message shows it directly."""
        with patch("src.repl._run_review", return_value="[no changes]"):
            result = registry.dispatch("/review", {})
            assert result.agent_prompt is None
            assert "[no changes]" in result.output

    def test_review_unknown_flag(self, registry):
        """/review with unknown flag shows usage."""
        result = registry.dispatch("/review --bad", {})
        assert "Usage" in result.output


class TestPrCommand:
    """Test /pr command."""

    def test_pr_returns_prompt(self, registry):
        """/pr returns a PR description prompt."""
        with patch("src.repl._run_pr_description", return_value="PR description"):
            result = registry.dispatch("/pr", {})
            assert result.agent_prompt == "PR description"

    def test_pr_error_message(self, registry):
        """/pr with error shows it directly."""
        with patch("src.repl._run_pr_description", return_value="[no changes]"):
            result = registry.dispatch("/pr", {})
            assert result.agent_prompt is None


class TestConfigCommand:
    """Test /config command."""

    def test_config_view(self, registry):
        """/config shows current settings."""
        result = registry.dispatch("/config", {})
        assert result.output

    def test_config_set_temperature(self, registry, mock_provider):
        """/config temperature 0.5 updates provider."""
        result = registry.dispatch("/config temperature 0.5", {})
        assert mock_provider.temperature == 0.5


class TestListProvidersCommand:
    """Test /list-providers command."""

    def test_list_providers_returns_output(self, registry):
        """/list-providers shows available providers."""
        result = registry.dispatch("/list-providers", {})
        assert result.output


class TestHistoryCommand:
    """Test /history command."""

    def test_history_returns_output(self, registry):
        """/history shows conversation history."""
        result = registry.dispatch("/history", {})
        assert result.output


class TestSearchCommand:
    """Test /search command."""

    def test_search_no_keyword(self, registry):
        """/search without keyword shows usage."""
        result = registry.dispatch("/search", {})
        assert "Usage" in result.output

    def test_search_with_keyword(self, registry):
        """/search with keyword calls _search_conversation."""
        with patch("src.repl._search_conversation", return_value="found 2"):
            result = registry.dispatch("/search hello", {})
            assert "found 2" in result.output


class TestSystemCommand:
    """Test /system command."""

    def test_system_returns_output(self, registry):
        """/system shows the system prompt."""
        result = registry.dispatch("/system", {})
        assert result.output


class TestSaveCommand:
    """Test /save command."""

    def test_save_default_path(self, registry):
        """/save uses default path."""
        with patch("src.repl._save_session", return_value="saved!") as mock:
            result = registry.dispatch("/save", {})
            assert "saved!" in result.output


class TestExportCommand:
    """Test /export command."""

    def test_export_default_path(self, registry):
        """/export uses default path."""
        with patch("src.repl._export_to_file", return_value="exported!") as mock:
            result = registry.dispatch("/export", {})
            assert "exported!" in result.output


class TestLoadCommand:
    """Test /load command."""

    def test_load_failure(self, registry):
        """/load with nonexistent file shows error."""
        with patch("src.repl._load_session", return_value=None):
            result = registry.dispatch("/load", {})
            assert "Failed" in result.output


class TestResumeCommand:
    """Test /resume command."""

    def test_resume_no_session(self, registry):
        """/resume with no session shows message."""
        with patch("src.repl._handle_resume_command", return_value="No session found"):
            result = registry.dispatch("/resume", {})
            assert "No session found" in result.output


class TestCdCommand:
    """Test /cd command."""

    def test_cd_changes_directory(self, registry):
        """/cd calls _handle_cd_command."""
        with patch("src.repl._handle_cd_command", return_value="[OK] changed to /tmp"):
            result = registry.dispatch("/cd /tmp", {})
            assert "changed" in result.output


class TestCommandsCommand:
    """Test /commands command."""

    def test_commands_no_custom(self, registry):
        """/commands with no custom commands shows message."""
        with patch("src.repl._load_custom_commands", return_value={}):
            result = registry.dispatch("/commands", {})
            assert "No custom" in result.output

    def test_commands_with_custom(self, registry):
        """/commands shows custom command names."""
        with patch("src.repl._load_custom_commands", return_value={
            "deploy": {"description": "Deploy the project"},
        }):
            result = registry.dispatch("/commands", {})
            assert "deploy" in result.output


class TestUnknownCommand:
    """Test dispatching unknown commands."""

    def test_unknown_returns_none(self, registry):
        """Unknown commands return None from dispatch."""
        result = registry.dispatch("/nonexistent", {})
        assert result is None
