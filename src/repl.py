"""Interactive REPL — the terminal interface for yoyo-py."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .agent import Agent, AgentEvent
from .provider import GLMProvider, Usage
from .tools import TOOL_FUNCTIONS, TOOL_SCHEMAS
from .skills import SkillSet
from . import __version__

# ANSI colors
RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
CYAN = "\x1b[36m"
RED = "\x1b[31m"
MAGENTA = "\x1b[35m"


# ── Command Registry ──────────────────────────────────────────────────
# A lightweight registry that maps slash command names to handler functions.
# Each handler receives the raw input line and a context dict, and returns
# a CommandResult. This replaces the giant if/elif chain in run_repl().

from dataclasses import dataclass, field as dc_field


@dataclass
class CommandResult:
    """Result from a slash command handler.

    Attributes:
        output: Text to display to the user. Printed before returning to the REPL loop.
        agent_prompt: If set, this text is sent to the agent as a prompt after displaying output.
                      Used by commands like /review, /pr that need the LLM to process results.
        done: If True, the REPL should exit after this command (e.g. /quit, /exit).
    """
    output: str = ""
    agent_prompt: str | None = None
    done: bool = False


class CommandRegistry:
    """Registry mapping slash command names to handler functions.

    Usage:
        registry = CommandRegistry()

        @registry.register("hello")
        def handle_hello(line: str, ctx: dict) -> CommandResult:
            return CommandResult(output="Hello!")

        result = registry.dispatch("/hello", ctx)
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[str, dict], CommandResult]] = {}

    def register(
        self,
        name: str,
        aliases: list[str] | None = None,
    ) -> Callable:
        """Decorator to register a command handler.

        Args:
            name: Primary command name (without /).
            aliases: Alternative names that dispatch to the same handler.
        """
        def decorator(fn: Callable[[str, dict], CommandResult]) -> Callable[[str, dict], CommandResult]:
            self._handlers[name] = fn
            if aliases:
                for alias in aliases:
                    self._handlers[alias] = fn
            return fn
        return decorator

    def dispatch(self, line: str, ctx: dict) -> CommandResult | None:
        """Dispatch a slash command line to the registered handler.

        Matches by extracting the command name from the line (first word after /),
        then calling the registered handler with the full line and context.

        Args:
            line: The raw input line (e.g. "/commit fix bug").
            ctx: Context dict with agent state (messages, model, etc.).

        Returns:
            CommandResult if a handler was found, None if no handler matched.
        """
        if not line.startswith("/"):
            return None

        # Extract command name: first word after /
        parts = line[1:].split(None, 1)
        cmd_name = parts[0].lower() if parts else ""

        handler = self._handlers.get(cmd_name)
        if handler is None:
            return None

        return handler(line, ctx)

    def list_commands(self) -> list[str]:
        """Return sorted list of registered command names."""
        return sorted(self._handlers.keys())


def command_handler(
    registry: CommandRegistry,
    name: str,
    aliases: list[str] | None = None,
) -> Callable:
    """Standalone decorator version for module-level registration.

    Same as registry.register() but usable without the @ syntax sugar.
    """
    return registry.register(name, aliases=aliases)


# ── Readline support: history + tab completion ────────────────────────

_HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".yoyo_history")
_HISTORY_MAX = 500

# All slash commands for tab completion
_SLASH_COMMANDS = sorted([
    "/help", "/quit", "/exit", "/clear", "/redo", "/last", "/copy",
    "/resume", "/compact", "/cd", "/model", "/revert",
    "/diff", "/log", "/commit", "/undo", "/review", "/pr",
    "/tree", "/count", "/init", "/health", "/test", "/fix", "/edit", "/cat", "/head", "/tail", "/du", "/find", "/wc",
    "/status", "/tokens", "/cost", "/history", "/search", "/grep", "/system", "/env",
    "/config", "/list-providers", "/provider", "/think", "/version", "/man",
    "/save", "/load", "/sessions", "/rm", "/export", "/remember", "/memories", "/forget",
    "/append",
    "/skills", "/commands", "/selfassess",
])


def _setup_readline() -> None:
    """Configure readline for persistent history and slash command completion.

    Persistent history lets users press Up to recall commands from previous
    sessions. Tab completion speeds up slash command entry.
    """
    try:
        import readline
    except ImportError:
        return  # Not available on Windows or some minimal Python installs

    # Tab completion for slash commands
    readline.set_completer(_slash_completer)
    readline.parse_and_bind("tab: complete")
    # Use our completer as the only completion source (not filename completion)
    readline.set_completer_delims(" \t\n")

    # Load persistent history
    try:
        readline.read_history_file(_HISTORY_FILE)
    except FileNotFoundError:
        pass
    except Exception:
        pass

    # Limit history length
    readline.set_history_length(_HISTORY_MAX)


def _save_readline_history() -> None:
    """Save readline history to disk. Silent on failure."""
    try:
        import readline
        readline.write_history_file(_HISTORY_FILE)
    except Exception:
        pass


# ── Persistent config: save/load generation settings ───────────────────

# Valid config keys and their validation rules
_VALID_CONFIG_KEYS = {"temperature", "max_tokens", "top_p"}


def _get_default_config_path() -> str:
    """Return the default path for persistent config: .yoyo/config.json in cwd."""
    return os.path.join(os.getcwd(), ".yoyo", "config.json")


def _load_persistent_config(config_path: str | None = None) -> dict[str, Any]:
    """Load persistent config from .yoyo/config.json.

    Returns only valid keys (temperature, max_tokens, top_p).
    Returns empty dict if file doesn't exist or is corrupt.
    """
    path = config_path or _get_default_config_path()
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    # Filter to valid keys only
    return {k: v for k, v in data.items() if k in _VALID_CONFIG_KEYS}


def _save_persistent_config(
    settings: dict[str, Any],
    config_path: str | None = None,
) -> None:
    """Save settings to .yoyo/config.json, merging with existing config.

    Validates values before saving:
    - temperature: clamped to [0.0, 2.0]
    - top_p: clamped to [0.0, 1.0]
    - max_tokens: must be positive (skipped if invalid)

    Creates the .yoyo/ directory if needed.
    """
    path = config_path or _get_default_config_path()
    dir_path = os.path.dirname(path)

    # Load existing config to merge with
    existing = _load_persistent_config(config_path=path)

    for key, value in settings.items():
        if key not in _VALID_CONFIG_KEYS:
            continue
        if value is None:
            # Remove key (reset to default)
            existing.pop(key, None)
            continue
        # Validate
        if key == "temperature":
            value = max(0.0, min(2.0, float(value)))
        elif key == "top_p":
            value = max(0.0, min(1.0, float(value)))
        elif key == "max_tokens":
            value = int(value)
            if value < 1:
                continue  # Skip invalid value
        existing[key] = value

    # Create directory if needed
    os.makedirs(dir_path, exist_ok=True)

    with open(path, "w") as f:
        json.dump(existing, f, indent=2)
        f.write("\n")


def _slash_completer(text: str, state: int) -> str | None:
    """Readline completer: suggests slash commands and file paths.

    For commands that take file/directory arguments (cd, edit, load, save,
    export), completes with matching filesystem entries. For other inputs
    starting with /, completes slash command names.
    """
    if not text.startswith("/"):
        return None

    # Commands that take path arguments — each maps to a filter function
    _PATH_COMMANDS = {
        "/cd ": _complete_dirs,
        "/edit ": _complete_files,
        "/load ": _complete_json_paths,
        "/save ": _complete_json_paths,
        "/export ": _complete_md_paths,
        "/rm ": _complete_yoyo_sessions,
        "/cat ": _complete_files,
        "/head ": _complete_files,
        "/tail ": _complete_files,
        "/du ": _complete_files,
        "/find ": _complete_files,
        "/wc ": _complete_files,
    }

    # Commands that complete from a fixed list of options
    _LIST_COMMANDS: dict[str, Callable[[str], list[str]]] = {
        "/model ": _complete_model_names,
        "/provider ": _complete_provider_names,
        "/think ": lambda partial: [x for x in ("low", "medium", "high") if x.startswith(partial)],
    }

    # Check if we should do path completion instead of command completion
    for prefix, completer_fn in _PATH_COMMANDS.items():
        if text.startswith(prefix):
            matches = completer_fn(text[len(prefix):])
            if state < len(matches):
                return prefix + matches[state]
            return None

    # Check list-based completions (model names, provider names)
    for prefix, completer_fn in _LIST_COMMANDS.items():
        if text.startswith(prefix):
            matches = completer_fn(text[len(prefix):])
            if state < len(matches):
                return prefix + matches[state]
            return None

    # Default: slash command name completion
    matches = [cmd for cmd in _SLASH_COMMANDS if cmd.startswith(text)]
    if state < len(matches):
        return matches[state]
    return None


def _complete_dirs(partial: str) -> list[str]:
    """Return directory names matching the partial path."""
    try:
        cwd = os.getcwd()
        if os.path.isabs(partial):
            base_dir = os.path.dirname(partial) or "/"
            prefix = os.path.basename(partial)
        else:
            base_dir = os.path.dirname(os.path.join(cwd, partial)) or cwd
            prefix = os.path.basename(partial)

        entries = []
        for entry in os.listdir(base_dir):
            full = os.path.join(base_dir, entry)
            if os.path.isdir(full) and entry.startswith(prefix):
                entries.append(entry)
        return sorted(entries)
    except Exception:
        return []


def _complete_files(partial: str) -> list[str]:
    """Return file names matching the partial path."""
    try:
        cwd = os.getcwd()
        if os.path.isabs(partial):
            base_dir = os.path.dirname(partial) or "/"
            prefix = os.path.basename(partial)
        else:
            base_dir = os.path.dirname(os.path.join(cwd, partial)) or cwd
            prefix = os.path.basename(partial)

        entries = []
        for entry in os.listdir(base_dir):
            full = os.path.join(base_dir, entry)
            if os.path.isfile(full) and entry.startswith(prefix):
                entries.append(entry)
        return sorted(entries)
    except Exception:
        return []


def _complete_json_paths(partial: str) -> list[str]:
    """Return .json file and directory names matching the partial path."""
    return _complete_by_ext(partial, ".json")


def _complete_md_paths(partial: str) -> list[str]:
    """Return .md file and directory names matching the partial path."""
    return _complete_by_ext(partial, ".md")


def _complete_by_ext(partial: str, ext: str) -> list[str]:
    """Return entries matching the partial path with given extension or directories."""
    try:
        cwd = os.getcwd()
        if os.path.isabs(partial):
            base_dir = os.path.dirname(partial) or "/"
            prefix = os.path.basename(partial)
        else:
            base_dir = os.path.dirname(os.path.join(cwd, partial)) or cwd
            prefix = os.path.basename(partial)

        entries = []
        for entry in os.listdir(base_dir):
            full = os.path.join(base_dir, entry)
            if entry.startswith(prefix) and (
                os.path.isdir(full) or entry.endswith(ext)
            ):
                entries.append(entry)
        return sorted(entries)
    except Exception:
        return []


def _complete_yoyo_sessions(partial: str) -> list[str]:
    """Complete session names from .yoyo/*.json for /rm command."""
    try:
        yoyo_dir = os.path.join(os.getcwd(), ".yoyo")
        if not os.path.isdir(yoyo_dir):
            return []
        entries = []
        for entry in os.listdir(yoyo_dir):
            if entry.endswith(".json") and entry.startswith(partial):
                entries.append(entry)
        return sorted(entries)
    except Exception:
        return []


def _complete_model_names(partial: str) -> list[str]:
    """Complete model names from the known context window table."""
    from .provider import MODEL_CONTEXT_WINDOWS
    return sorted(m for m in MODEL_CONTEXT_WINDOWS if m.startswith(partial))


def _complete_provider_names(partial: str) -> list[str]:
    """Complete provider preset names."""
    from .provider import PROVIDER_PRESETS
    return sorted(p for p in PROVIDER_PRESETS if p.startswith(partial))


def print_banner() -> None:
    print(f"\n{BOLD}{CYAN}  yoyo-py{RESET} {DIM}v{__version__} — a self-evolving coding agent (Python + GLM 5){RESET}")
    print(f"{DIM}  Type /help for commands, /quit to exit{RESET}\n")


def print_usage(usage) -> None:
    if usage.input_tokens > 0 or usage.output_tokens > 0:
        print(f"\n{DIM}  tokens: {usage}{RESET}")


# Context file names in priority order — first match wins.
# Covers the major AI coding agent conventions so yoyo-py can work
# with projects that already have instructions for other tools.
_CONTEXT_FILE_NAMES = (
    "YOYO.md",
    "CLAUDE.md",
    "AGENTS.md",
    "RULES.md",
    ".cursorrules",
    ".windsurfrules",
)

# Maximum parent directory levels to walk up when searching for context files.
_CONTEXT_SEARCH_MAX_DEPTH = 10


def _find_context_file(cwd: str) -> tuple[str, str] | None:
    """Find the best context file for the given working directory.

    Searches for known context file names (YOYO.md, CLAUDE.md, AGENTS.md,
    .cursorrules, RULES.md, .windsurfrules) in priority order. Looks in the
    current directory first, then walks up parent directories up to
    _CONTEXT_SEARCH_MAX_DEPTH levels.

    Returns (file_path, file_name) if found, else None.
    """
    current = Path(cwd).resolve()
    for _ in range(_CONTEXT_SEARCH_MAX_DEPTH + 1):
        for name in _CONTEXT_FILE_NAMES:
            candidate = current / name
            if candidate.is_file():
                return (str(candidate), name)
        parent = current.parent
        if parent == current:
            # Reached filesystem root
            break
        current = parent
    return None


def load_system_prompt(skills: SkillSet | None = None) -> str:
    """Build the system prompt from base + skills + project context."""
    from datetime import datetime

    parts = [
        "You are a coding assistant working in the user's terminal.",
        "You have access to the filesystem and shell. Be direct and concise.",
        "When the user asks you to do something, do it — don't just explain how.",
        "Use tools proactively: read files to understand context, run commands to verify your work.",
        "After making changes, run tests or verify the result when appropriate.",
        "You respond in the same language the user uses.",
        f"Current date: {datetime.now().strftime('%Y-%m-%d')}",
        f"Current working directory: {os.getcwd()}",
    ]

    # Add git context (branch, recently changed files)
    git_ctx = _git_context()
    if git_ctx:
        parts.append(git_ctx)

    # Discover project context files (YOYO.md, CLAUDE.md, AGENTS.md, .cursorrules, etc.)
    # Searches current dir first, then walks up parent dirs (up to 10 levels).
    ctx_result = _find_context_file(os.getcwd())
    if ctx_result:
        ctx_path, ctx_name = ctx_result
        try:
            with open(ctx_path, encoding="utf-8") as fh:
                content = fh.read()
            parts.append(f"\n# Project Context ({ctx_name})\n{content}")
        except Exception:
            pass

    # Add skills
    if skills and not skills.is_empty():
        parts.append(f"\n# Loaded Skills\n{skills.to_prompt()}")

    # Add project memories
    memories_prompt = _load_memories_into_prompt()
    if memories_prompt:
        parts.append(memories_prompt)

    return "\n".join(parts)


def _make_confirm_fn(
    auto_approve: bool = False,
    input_fn: Callable | None = None,
) -> Callable[[str, dict], bool]:
    """Create a confirmation function for destructive tool calls.

    Args:
        auto_approve: If True, always return True (used with --yes flag).
        input_fn: Function to call for user input. Defaults to built-in input().

    Returns:
        A function (tool_name, tool_args) -> bool that decides whether to allow
        a destructive tool call.
    """
    if auto_approve:
        return lambda name, args: True

    _input = input_fn or input

    def _confirm(tool_name: str, tool_args: dict) -> bool:
        # Build a short summary of what the tool will do
        if tool_name == "bash":
            summary = f"$ {tool_args.get('command', '...')}"
        elif tool_name == "write_file":
            summary = f"write → {tool_args.get('path', '?')}"
        elif tool_name == "edit_file":
            path = tool_args.get('path', '?')
            old = tool_args.get('old_string', '')
            new = tool_args.get('new_string', '')
            # Show a compact diff-like preview for edit operations
            if old and new:
                old_preview = old[:60] + ('…' if len(old) > 60 else '')
                new_preview = new[:60] + ('…' if len(new) > 60 else '')
                summary = f"edit → {path}\n    {RED}- {old_preview}{RESET}\n    {GREEN}+ {new_preview}{RESET}"
            elif old:
                summary = f"edit → {path} (replace)"
            else:
                summary = f"edit → {path}"
        elif tool_name == "copy_file":
            summary = f"copy {tool_args.get('source', '?')} → {tool_args.get('destination', '?')}"
        elif tool_name == "rename":
            summary = f"rename {tool_args.get('source', '?')} → {tool_args.get('destination', '?')}"
        else:
            summary = f"{tool_name}({tool_args})"

        try:
            answer = _input(f"{YELLOW}  ⚠ Allow {summary}? [y/N]{RESET} ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            # Default to reject on Ctrl+C/D
            return False

        return answer in ("y", "yes")

    return _confirm


async def run_repl(
    provider: GLMProvider,
    skill_dirs: list[str] | None = None,
    verbose: bool = False,
    initial_prompt: str | None = None,
    pipe_input: str | None = None,
    auto_approve: bool = False,
    resume: bool = False,
    continue_after_prompt: bool = False,
) -> None:
    """Run the interactive REPL loop."""
    # Load skills
    skills = SkillSet()
    if skill_dirs:
        for d in skill_dirs:
            skills.load(d)

    system_prompt = load_system_prompt(skills)

    # Wire up permission system: confirm before destructive tools
    # unless --yes flag is set (which auto-approves everything)
    # Non-interactive mode (pipe/prompt) also auto-approves — no user to confirm
    non_interactive = bool(pipe_input or initial_prompt)
    confirm_fn = _make_confirm_fn(auto_approve=auto_approve or non_interactive)

    agent = Agent(
        provider=provider,
        system_prompt=system_prompt,
        tools=TOOL_FUNCTIONS,
        tool_schemas=TOOL_SCHEMAS,
        verbose=verbose,
        confirm_fn=confirm_fn,
    )

    # Load persistent config from .yoyo/config.json (temperature, max_tokens, top_p)
    # so settings survive across sessions
    saved_config = _load_persistent_config()
    for key, value in saved_config.items():
        setattr(provider, key, value)

    # Handle --resume flag: restore last auto-saved session before starting REPL
    if resume and not pipe_input and not initial_prompt:
        result = _handle_resume_command()
        if isinstance(result, tuple):
            messages, model, usage, warnings = result
            agent.state.messages = messages
            agent.state.usage = usage
            provider.model = model
            real_count = len([m for m in messages if m.get("role") != "system"])
            print(f"{GREEN}  ✓ Resumed session ({real_count} messages, model: {model}){RESET}")
            if warnings:
                print(f"{YELLOW}  ⚠ Session has {len(warnings)} issue(s):{RESET}")
                for w in warnings[:5]:
                    print(f"{YELLOW}    • {w}{RESET}")
            print()
        else:
            # No autosave found or invalid — just start fresh silently
            pass

    # Enable readline history + tab completion
    _setup_readline()

    print_banner()
    print(f"{DIM}  model: {provider.model}{RESET}")
    if not skills.is_empty():
        print(f"{DIM}  skills: {skills.count()} loaded{RESET}")
    print(f"{DIM}  cwd:   {os.getcwd()}{RESET}\n")

    # Handle piped input — always exits after processing
    if pipe_input:
        await _run_agent_turn(agent, pipe_input)
        return

    # Build command registry — all slash commands in one place
    # (needed before initial prompt so the registry is available for the
    # interactive loop even if we start with -p --continue)
    registry = _build_command_registry(agent, provider, skills)

    # Handle initial prompt (-p flag)
    # With --continue, run the prompt and fall through to interactive loop.
    # Without --continue, exit after the prompt (original behavior).
    if initial_prompt:
        await _run_agent_turn(agent, initial_prompt)
        if not continue_after_prompt:
            return

    # Interactive loop
    while True:
        try:
            line = _read_multiline_input()
        except (EOFError, KeyboardInterrupt):
            # Auto-save on exit to prevent data loss
            _auto_save_on_exit(agent.state.messages, provider.model, usage=agent.state.usage)
            _save_readline_history()
            print(f"\n{DIM}  bye 👋{RESET}\n")
            break

        line = line.strip()
        if not line:
            continue

        # Shell escape: !command runs it locally and feeds output to agent
        # This is like IPython's ! syntax — quick way to share command output
        # with the agent without copy-pasting.
        if line.startswith("!") and len(line) > 1:
            shell_cmd = line[1:].strip()
            if shell_cmd:
                print(f"{DIM}  $ {shell_cmd}{RESET}")
                output = tool_bash(shell_cmd)
                prompt = _format_shell_escape(shell_cmd, output)
                # Show preview of output to the user
                preview = _format_tool_output_preview(output, max_len=300, max_lines=5)
                if preview:
                    print(f"{DIM}  {preview}{RESET}\n")
                await _run_agent_turn(agent, prompt)
            continue

        # Handle slash commands via the command registry
        if line.startswith("/"):
            result = registry.dispatch(line, {})
            if result is not None:
                if result.output:
                    print(result.output, end="")
                if result.done:
                    break
                if result.agent_prompt:
                    await _run_agent_turn(agent, result.agent_prompt)
                continue

            # Fallback: check custom commands from .yoyo/commands/
            custom_name = line[1:].split()[0]
            custom_args = line[1 + len(custom_name):].strip()
            resolved = _resolve_custom_command(custom_name, args=custom_args)
            if resolved is not None:
                await _run_agent_turn(agent, resolved)
            else:
                print(f"{DIM}  Unknown command: {line}{RESET}\n")
            continue

        # Run agent turn
        await _run_agent_turn(agent, line)


def _show_context_warning(agent: Agent) -> None:
    """Show a subtle warning if context usage is high (≥60%).

    This helps users understand why the agent might be losing context
    and proactively use /compact before auto-compact kicks in.
    """
    est_tokens = Agent._estimate_tokens(agent.state.messages)
    context_window = _get_model_context_window(agent.provider.model)
    pct = int(est_tokens / context_window * 100) if context_window > 0 else 0

    if pct >= 60:
        budget = _format_context_budget(est_tokens, context_window)
        print(f"{DIM}  context: {budget}{RESET}")


async def _run_agent_turn(agent: Agent, user_input: str) -> None:
    """Execute one agent turn and display results."""
    # Show context warning if usage is high — helps users avoid unexpected auto-compact
    _show_context_warning(agent)

    in_text = False

    # Set up Ctrl+C handler during agent execution
    def _on_interrupt(sig, frame):
        agent.interrupt()

    import signal
    old_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, _on_interrupt)

    try:
        async for event_type, data in agent.prompt(user_input):
            if event_type == AgentEvent.TEXT:
                if not in_text:
                    print()
                    in_text = True
                print(data, end="", flush=True)

            elif event_type == AgentEvent.TOOL_START:
                if in_text:
                    print()
                    in_text = False
                name = data["name"]
                args = data["args"]
                summary = _tool_summary(name, args)
                print(f"{YELLOW}  ▶ {summary}{RESET}", end="", flush=True)

            elif event_type == AgentEvent.TOOL_END:
                if data["is_error"]:
                    print(f" {RED}✗{RESET}")
                    # Show error preview so user can see what went wrong
                    preview = _format_tool_output_preview(data.get("output"), max_len=200, is_error=True)
                    if preview:
                        print(f"    {RED}{preview}{RESET}")
                else:
                    print(f" {GREEN}✓{RESET}")
                    # Show output preview so user gets immediate feedback
                    preview = _format_tool_output_preview(data.get("output"), max_len=150)
                    if preview:
                        print(f"    {DIM}{preview}{RESET}")

            elif event_type == AgentEvent.COMPACT:
                if in_text:
                    print()
                    in_text = False
                info = data
                print(
                    f"{DIM}  ⚡ auto-compacted: {info['old_count']}→{info['new_count']} messages, "
                    f"~{info['old_tokens']}→~{info['new_tokens']} tokens{RESET}\n"
                )

            elif event_type == AgentEvent.DONE:
                if in_text:
                    print()
                print_usage(data)
                print()

            elif event_type == AgentEvent.INTERRUPTED:
                if in_text:
                    print()
                print(f"\n{YELLOW}  ⏸ interrupted — press Enter to continue{RESET}\n")

            elif event_type == AgentEvent.ERROR:
                if in_text:
                    print()
                print(f"\n{RED}  ✗ {data}{RESET}\n")
    finally:
        # Restore previous SIGINT handler
        signal.signal(signal.SIGINT, old_handler)

    if in_text:
        print()


def _tool_summary(name: str, args: dict) -> str:
    """Generate a short summary of a tool call for display."""
    if name == "bash":
        cmd = args.get("command", "...")
        return f"$ {_truncate_str(cmd, 80)}"
    elif name == "read_file":
        path = args.get("path", "?")
        return f"read {path}"
    elif name == "write_file":
        path = args.get("path", "?")
        return f"write {path}"
    elif name == "edit_file":
        path = args.get("path", "?")
        return f"edit {path}"
    elif name == "search":
        pat = args.get("pattern", "?")
        return f"search '{_truncate_str(pat, 60)}'"
    elif name == "list_files":
        path = args.get("path", ".")
        return f"ls {path}"
    elif name == "glob":
        pat = args.get("pattern", "*")
        return f"glob '{_truncate_str(pat, 60)}'"
    elif name == "mkdir":
        path = args.get("path", ".")
        return f"mkdir {path}"
    elif name == "copy_file":
        src = args.get("source", "?")
        dst = args.get("destination", "?")
        return f"copy {src} → {dst}"
    elif name == "rename":
        src = args.get("source", "?")
        dst = args.get("destination", "?")
        return f"rename {src} → {dst}"
    return name


def _read_multiline_input() -> str:
    """Read user input with backslash continuation support.

    Lines ending with '\\' are continued on the next line.
    The backslash and trailing newline are replaced with a single newline.
    """
    PROMPT_FIRST = f"{BOLD}{GREEN}> {RESET}"
    PROMPT_CONT = f"{BOLD}{GREEN}... {RESET}"

    try:
        line = input(PROMPT_FIRST)
    except (EOFError, KeyboardInterrupt):
        raise

    # Strip only the trailing newline that input() includes; preserve leading whitespace
    lines = []
    while True:
        if line.endswith("\\"):
            # Remove the trailing backslash, continue to next line
            lines.append(line[:-1])
            try:
                line = input(PROMPT_CONT)
            except (EOFError, KeyboardInterrupt):
                # If interrupted during continuation, return what we have so far
                break
        else:
            lines.append(line)
            break

    return "\n".join(lines)


def _truncate_str(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len] + "..."


def _format_shell_escape(command: str, output: str, max_output: int = 5000) -> str:
    """Format shell escape output as a user message for the agent.

    When a user types '!command', we execute it locally and feed the
    output to the agent as context. This lets users share command output
    (git log, test results, etc.) with the agent without copy-pasting.

    Args:
        command: The shell command that was run (without the ! prefix).
        output: Combined stdout+stderr from the command.
        max_output: Max chars to include (default 5000 — enough context
            without blowing up the conversation).

    Returns:
        Formatted string suitable as a user message.
    """
    if not output or not output.strip():
        return f"Output of `{command}`:\n(no output)"

    # Truncate very long output — the agent doesn't need 50K of log
    if len(output) > max_output:
        truncated = output[:max_output]
        truncated += f"\n... [truncated from {len(output)} chars]"
        output = truncated

    return f"Output of `{command}`:\n{output}"


def _format_tool_output_preview(
    output: str | None,
    max_len: int = 200,
    max_lines: int = 3,
    is_error: bool = False,
) -> str:
    """Format a short preview of tool output for display in the REPL.

    Shows the first few lines of output, truncated to max_len chars.
    This gives users immediate feedback without waiting for the LLM to
    rephrase the result.

    Args:
        output: The tool output string (may be None).
        max_len: Max characters to show (default 200).
        max_lines: Max lines to show (default 3).
        is_error: Whether this is an error output.

    Returns a formatted preview string, or empty string if no output.
    """
    if not output:
        return ""

    # Split into lines, take first max_lines
    lines = output.strip().splitlines()
    total_chars = len(output)
    total_lines = len(lines)

    if total_lines <= max_lines and total_chars <= max_len:
        return output.strip()

    # Take first max_lines lines
    preview_lines = lines[:max_lines]
    preview = "\n".join(preview_lines)

    # Truncate if still too long
    if len(preview) > max_len:
        preview = preview[:max_len]

    # Add truncation indicator with stats
    indicators = []
    if total_lines > max_lines:
        indicators.append(f"{total_lines - max_lines} more line{'s' if total_lines - max_lines != 1 else ''}")
    if len(preview) < total_chars and total_lines <= max_lines:
        indicators.append(f"{total_chars} chars total")

    if indicators:
        preview += f"… ({', '.join(indicators)})"
    else:
        preview += "…"

    return preview


def _run_git(*args: str, timeout: int = 10, workdir: str | None = None) -> subprocess.CompletedProcess:
    """Run a git command and return the CompletedProcess result.

    This is the shared git helper used by all git-related REPL functions.
    Extracted from 7 duplicated local function definitions to reduce code duplication
    and make future git-related features easier to add.

    Args:
        *args: Git subcommand and arguments (e.g. "branch", "--show-current").
        timeout: Max seconds to wait (default 10).
        workdir: Working directory (default: None = current directory).

    Returns:
        subprocess.CompletedProcess with returncode, stdout, stderr.
    """
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
    }
    if workdir is not None:
        kwargs["cwd"] = workdir
    return subprocess.run(["git"] + list(args), **kwargs)


def _git_context() -> str:
    """Collect git context for the system prompt: branch and recently changed files.

    Returns a formatted string for the system prompt, or empty string if not in a git repo.
    This helps the agent understand what files the user has been working on recently.
    """
    # Use shorter timeout for system prompt context — this runs on every startup
    _git = lambda *args: _run_git(*args, timeout=5)

    # Check we're in a git repo
    check = _git("rev-parse", "--is-inside-work-tree")
    if check.returncode != 0:
        return ""

    # Get current branch name
    branch_result = _git("branch", "--show-current")
    if branch_result.returncode == 0 and branch_result.stdout.strip():
        branch = branch_result.stdout.strip()
    else:
        # Detached HEAD — show short commit hash instead
        head_result = _git("rev-parse", "--short", "HEAD")
        branch = head_result.stdout.strip() if head_result.returncode == 0 else "detached"

    # Get recently changed files (modified + untracked)
    changed_files = []
    diff_result = _git("diff", "--name-only")
    if diff_result.returncode == 0 and diff_result.stdout.strip():
        changed_files.extend(diff_result.stdout.strip().splitlines())

    # Staged changes too
    diff_cached = _git("diff", "--cached", "--name-only")
    if diff_cached.returncode == 0 and diff_cached.stdout.strip():
        for f in diff_cached.stdout.strip().splitlines():
            if f not in changed_files:
                changed_files.append(f)

    # Untracked files
    untracked = _git("ls-files", "--others", "--exclude-standard")
    if untracked.returncode == 0 and untracked.stdout.strip():
        for f in untracked.stdout.strip().splitlines():
            if f not in changed_files:
                changed_files.append(f)

    # Build context string
    lines = [f"\n# Git Context\nBranch: {branch}"]
    if changed_files:
        lines.append("Recently changed files:")
        for f in changed_files[:20]:  # Limit to 20 files to avoid bloating the prompt
            lines.append(f"  {f}")
        if len(changed_files) > 20:
            lines.append(f"  ... and {len(changed_files) - 20} more")

    return "\n".join(lines)


def _git_status_line() -> str | None:
    """Return a one-line git status summary: branch + dirty/clean.

    Returns None if not in a git repo.
    """
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            # Try detached HEAD
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return None
            branch = result.stdout.strip() + " (detached)"
        else:
            branch = result.stdout.strip()

        # Check dirty status
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return branch

        changed = len([l for l in result.stdout.strip().splitlines() if l.strip()])
        if changed == 0:
            return f"{branch} (clean)"
        else:
            return f"{branch} ({changed} changed)"
    except Exception:
        return None


def _git_diff_summary() -> str:
    """Generate a summary of git changes (staged + unstaged).

    Returns a human-readable summary or error message.
    """
    # Status labels for name-status output
    STATUS_LABELS = {
        "M": "modified",
        "A": "added",
        "D": "deleted",
        "R": "renamed",
        "C": "copied",
        "T": "typechange",
    }

    # Check we're in a git repo
    check = _run_git("rev-parse", "--is-inside-work-tree")
    if check.returncode != 0:
        return "[Not a git repo]"

    # Get unstaged changes
    unstaged = _run_git("diff", "--name-status")
    # Get staged changes
    staged = _run_git("diff", "--cached", "--name-status")

    if unstaged.returncode != 0 or staged.returncode != 0:
        return f"[ERROR] git diff failed"

    unstaged_output = unstaged.stdout.strip()
    staged_output = staged.stdout.strip()

    if not unstaged_output and not staged_output:
        return "[No changes — working tree clean]"

    lines = []

    # Parse unstaged
    if unstaged_output:
        lines.append(f"{BOLD}Unstaged changes:{RESET}")
        for entry in unstaged_output.splitlines():
            parts = entry.split("\t", 1)
            if len(parts) == 2:
                status, path = parts
                label = STATUS_LABELS.get(status, status)
                lines.append(f"  {YELLOW}{label}{RESET}  {path}")
            else:
                lines.append(f"  {entry}")

    # Parse staged
    if staged_output:
        lines.append(f"{BOLD}Staged changes:{RESET}")
        for entry in staged_output.splitlines():
            parts = entry.split("\t", 1)
            if len(parts) == 2:
                status, path = parts
                label = STATUS_LABELS.get(status, status)
                lines.append(f"  {GREEN}{label}{RESET}  {path}")
            else:
                lines.append(f"  {entry}")

    # Add diff stat
    stat = _run_git("diff", "--stat")
    if stat.returncode == 0 and stat.stdout.strip():
        lines.append(f"\n{DIM}{stat.stdout.strip()}{RESET}")

    return "\n".join(lines)


def _run_diff_enhanced(args: str) -> str:
    """Enhanced /diff command — summary, per-file, full, or staged.

    Usage:
      /diff              Show change summary (default)
      /diff <file>       Show diff for a specific file
      /diff --full       Show full diff output
      /diff --staged     Show staged changes only
      /diff --stat       Show diffstat summary

    Multiple flags can be combined: /diff --staged --full
    """
    parts = args.strip().split()

    # Check we're in a git repo
    check = _run_git("rev-parse", "--is-inside-work-tree")
    if check.returncode != 0:
        return "[Not a git repo]"

    flags = set(parts)
    has_full = "--full" in flags
    has_staged = "--staged" in flags
    has_stat = "--stat" in flags
    # Extract file argument (non-flag args)
    file_args = [p for p in parts if not p.startswith("--")]

    if file_args:
        # Show diff for specific file(s)
        git_args = ["diff"]
        if has_staged:
            git_args.append("--cached")
        git_args.extend(file_args)
        result = _run_git(*git_args)
        if result.returncode != 0:
            return f"{RED}[ERROR] git diff failed: {result.stderr.strip()}{RESET}"
        output = result.stdout.strip()
        if not output:
            return f"{DIM}No changes in {', '.join(file_args)}{RESET}"
        # Truncate very long diffs to avoid flooding the terminal
        if len(output) > 20000:
            output = output[:20000] + f"\n{DIM}... [truncated, {len(output)} chars total]{RESET}"
        return output

    if has_full:
        # Show full diff
        git_args = ["diff"]
        if has_staged:
            git_args.append("--cached")
        result = _run_git(*git_args)
        if result.returncode != 0:
            return f"{RED}[ERROR] git diff failed{RESET}"
        output = result.stdout.strip()
        if not output:
            return f"{DIM}No changes{RESET}"
        if len(output) > 50000:
            output = output[:50000] + f"\n{DIM}... [truncated, {len(output)} chars total]{RESET}"
        return output

    if has_stat:
        # Show diffstat
        git_args = ["diff", "--stat"]
        if has_staged:
            git_args.append("--cached")
        result = _run_git(*git_args)
        if result.returncode != 0:
            return f"{RED}[ERROR] git diff --stat failed{RESET}"
        output = result.stdout.strip()
        if not output:
            return f"{DIM}No changes{RESET}"
        return output

    # Default: show the summary view (existing behavior)
    return _git_diff_summary()


def _git_commit(message: str) -> str:
    """Stage all changes and commit with the given message.

    Args:
        message: The commit message.

    Returns a human-readable result or error message.
    """

    # Check we're in a git repo
    check = _run_git("rev-parse", "--is-inside-work-tree")
    if check.returncode != 0:
        return "[ERROR] Not a git repo"

    # Check for changes (staged or unstaged)
    diff = _run_git("diff", "--name-status")
    diff_cached = _run_git("diff", "--cached", "--name-status")

    if diff.returncode != 0 or diff_cached.returncode != 0:
        return f"[ERROR] git diff failed: {diff.stderr.strip()}"

    if not diff.stdout.strip() and not diff_cached.stdout.strip():
        return "[No changes to commit]"

    # Stage all changes
    add = _run_git("add", "-A")
    if add.returncode != 0:
        return f"[ERROR] git add failed: {add.stderr.strip()}"

    # Commit
    commit = _run_git("commit", "-m", message)
    if commit.returncode != 0:
        return f"[ERROR] Commit failed: {commit.stderr.strip()}"

    return commit.stdout.strip()


def _save_session(filepath: str, messages: list[dict], model: str, usage: Usage | None = None) -> str:
    """Save conversation session to a JSON file.

    Args:
        filepath: Path to save the session file.
        messages: The conversation messages to save.
        model: The current model name.
        usage: Token usage data to persist (optional, for backward compat).

    Returns a human-readable result message.
    """
    from datetime import datetime
    from .provider import Usage as _Usage

    try:
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {
            "version": 1,
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "messages": messages,
        }
        # Persist usage data so token tracking survives session reload
        if usage is not None:
            data["usage"] = {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            }

        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return f"[OK] Session saved to {filepath} ({len(messages)} messages)"
    except Exception as e:
        return f"[ERROR] Failed to save session: {e}"


def _auto_save_session(
    save_path: str,
    messages: list[dict],
    model: str,
    usage: Usage | None = None,
) -> str:
    """Auto-save session on exit — prevents data loss from unexpected termination.

    Only saves if there are real messages beyond just the system prompt.
    The auto-saved file is marked with an "autosaved" flag so the user
    can distinguish it from manual saves.

    Args:
        save_path: Path to save the auto-save file.
        messages: The conversation messages.
        model: Current model name.
        usage: Token usage data.

    Returns a confirmation or skip message.
    """
    from datetime import datetime
    from .provider import Usage as _Usage

    # Don't save empty conversations or system-only sessions
    real_msgs = [m for m in messages if m.get("role") != "system"]
    if not real_msgs:
        return "[Skipped auto-save — no conversation to save]"

    try:
        p = Path(save_path)
        p.parent.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {
            "version": 1,
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "messages": messages,
            "autosaved": True,
        }
        if usage is not None:
            data["usage"] = {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            }

        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return f"[OK] Auto-saved session ({len(real_msgs)} messages)"
    except Exception as e:
        return f"[ERROR] Auto-save failed: {e}"


def _auto_save_on_exit(
    messages: list[dict],
    model: str,
    usage: Usage | None = None,
) -> None:
    """Auto-save session on REPL exit.

    Silently saves to .yoyo/autosave.json so users don't lose their
    conversation if they forget to /save. Only saves if there are real
    messages (not just a system prompt). Errors are silently ignored
    since this runs during exit.
    """
    try:
        save_path = os.path.join(os.getcwd(), ".yoyo", "autosave.json")
        _auto_save_session(save_path, messages, model, usage=usage)
    except Exception:
        pass  # Silent on exit — don't crash during shutdown


def _list_sessions(workdir: str | None = None) -> list[dict]:
    """List all session files in the .yoyo/ directory with metadata.

    Scans for .json files in <workdir>/.yoyo/ and extracts metadata:
    filename, timestamp, model, message count (excluding system), auto-saved flag,
    and token usage if available.

    Args:
        workdir: Working directory to search for .yoyo/. Defaults to cwd.

    Returns a list of dicts sorted by filename, each with session metadata.
    """
    if workdir is None:
        workdir = os.getcwd()
    yoyo_dir = os.path.join(workdir, ".yoyo")

    if not os.path.isdir(yoyo_dir):
        return []

    sessions = []
    for entry in sorted(os.listdir(yoyo_dir)):
        if not entry.endswith(".json"):
            continue
        filepath = os.path.join(yoyo_dir, entry)
        if not os.path.isfile(filepath):
            continue

        try:
            data = json.loads(Path(filepath).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        # Must have at least messages and model to be a valid session
        if not isinstance(data, dict) or "messages" not in data or "model" not in data:
            continue

        msg_count = len([m for m in data["messages"] if m.get("role") != "system"])
        meta: dict[str, Any] = {
            "filename": entry,
            "filepath": filepath,
            "timestamp": data.get("timestamp", ""),
            "model": data.get("model", "unknown"),
            "message_count": msg_count,
            "autosaved": data.get("autosaved", False),
            "input_tokens": data.get("usage", {}).get("input_tokens", 0),
            "output_tokens": data.get("usage", {}).get("output_tokens", 0),
        }
        sessions.append(meta)

    return sessions


def _format_sessions_output(sessions: list[dict]) -> str:
    """Format a list of session metadata dicts into readable output.

    Args:
        sessions: List of session metadata dicts from _list_sessions.

    Returns a formatted string for display in the REPL.
    """
    if not sessions:
        return f"{DIM}  No saved sessions found in .yoyo/{RESET}\n{DIM}  Use /save to create one{RESET}"

    lines = [f"{BOLD}  Saved Sessions:{RESET}"]
    for s in sessions:
        flag = f" {YELLOW}(auto-saved){RESET}" if s["autosaved"] else ""
        lines.append(f"    {CYAN}{s['filename']}{RESET}{flag}")
        lines.append(f"      {DIM}model: {s['model']}, {s['message_count']} messages{RESET}")
        if s["timestamp"]:
            lines.append(f"      {DIM}saved: {s['timestamp']}{RESET}")
        if s["input_tokens"] or s["output_tokens"]:
            lines.append(f"      {DIM}tokens: {s['input_tokens']} in / {s['output_tokens']} out{RESET}")
    lines.append(f"\n  {DIM}Use /load <filename> to restore, /rm <filename> to delete{RESET}")
    return "\n".join(lines)


def _delete_session(filename: str, workdir: str | None = None) -> bool:
    """Delete a session file from the .yoyo/ directory.

    Only deletes .json files and only from within .yoyo/ — prevents path traversal.

    Args:
        filename: Name of the session file to delete (just the basename).
        workdir: Working directory. Defaults to cwd.

    Returns True if deleted, False if not found or refused.
    """
    if workdir is None:
        workdir = os.getcwd()

    # Security: only allow .json files with no path components
    if not filename.endswith(".json"):
        return False
    # Prevent path traversal: basename must equal filename
    if os.path.basename(filename) != filename:
        return False
    if ".." in filename or "/" in filename or os.sep in filename:
        return False

    yoyo_dir = os.path.join(workdir, ".yoyo")
    filepath = os.path.join(yoyo_dir, filename)

    # Verify the resolved path is still inside .yoyo/
    real_yoyo = os.path.realpath(yoyo_dir)
    real_file = os.path.realpath(filepath)
    if not real_file.startswith(real_yoyo + os.sep) and real_file != real_yoyo:
        return False

    if not os.path.isfile(filepath):
        return False

    try:
        os.remove(filepath)
        return True
    except OSError:
        return False


def _load_session(filepath: str) -> tuple[list[dict], str, Usage, list[str]] | None:
    """Load a conversation session from a JSON file.

    Args:
        filepath: Path to the session file.

    Returns (messages, model, usage, warnings) tuple, or None on failure.
    The warnings list contains human-readable strings about any message
    structure issues found (consecutive same-role messages, orphaned tool
    messages, etc.). The messages are always returned — warnings are
    informational and help the user fix problems before they cause API errors.
    """
    from .provider import Usage as _Usage

    try:
        p = Path(filepath)
        if not p.exists():
            return None

        data = json.loads(p.read_text(encoding="utf-8"))

        # Validate required fields
        if "messages" not in data or "model" not in data:
            return None

        # Restore usage data (default to zero for old session files)
        usage = _Usage()
        if "usage" in data:
            usage = _Usage(
                input_tokens=data["usage"].get("input_tokens", 0),
                output_tokens=data["usage"].get("output_tokens", 0),
            )

        # Validate message structure — issues are informational, not blocking
        warnings: list[str] = []
        messages = data["messages"]
        if messages:
            from .agent import Agent
            issues = Agent._validate_messages(messages)
            warnings = issues

        return (messages, data["model"], usage, warnings)
    except Exception:
        return None


def _handle_resume_command(cwd: str | None = None) -> tuple[list[dict], str, Usage, list[str]] | str:
    """Resume the last auto-saved session.

    Checks for .yoyo/autosave.json in the current (or specified) directory.
    If a valid auto-saved session exists (has real messages beyond system prompt
    and is marked with "autosaved": true), returns (messages, model, usage, warnings)
    and deletes the autosave file. Otherwise returns an error/status message string.

    This gives users a simple /resume command to pick up where they left off
    after an accidental exit, instead of having to know about .yoyo/autosave.json.

    Args:
        cwd: Working directory to look for autosave (defaults to os.getcwd()).

    Returns:
        Tuple of (messages, model, usage, warnings) on success, or a string error message.
    """
    from .provider import Usage as _Usage

    workdir = cwd or os.getcwd()
    autosave_path = Path(workdir) / ".yoyo" / "autosave.json"

    if not autosave_path.exists():
        return "No auto-saved session found — start a new conversation"

    try:
        data = json.loads(autosave_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception):
        return "[ERROR] Auto-save file is corrupted — delete .yoyo/autosave.json to clear"

    # Only resume files that were auto-saved (not manual saves)
    if not data.get("autosaved"):
        return "No auto-saved session found — start a new conversation"

    # Validate required fields
    if "messages" not in data or "model" not in data:
        return "[ERROR] Auto-save file is missing required fields"

    messages = data["messages"]

    # Check for real messages (not just system prompt)
    real_msgs = [m for m in messages if m.get("role") != "system"]
    if not real_msgs:
        return "No auto-saved session found — start a new conversation"

    # Restore usage
    usage = _Usage()
    if "usage" in data:
        usage = _Usage(
            input_tokens=data["usage"].get("input_tokens", 0),
            output_tokens=data["usage"].get("output_tokens", 0),
        )

    model = data["model"]

    # Delete the autosave file after successful resume so it doesn't get
    # loaded again on next startup
    try:
        autosave_path.unlink()
    except OSError:
        pass  # Non-critical — worst case it gets loaded again

    # Validate message structure — warn about issues but don't block
    warnings: list[str] = []
    if messages:
        from .agent import Agent
        warnings = Agent._validate_messages(messages)

    return (messages, model, usage, warnings)


def _handle_cd_command(path: str) -> str:
    """Change the working directory.

    Args:
        path: Target directory path. Empty string or '~' goes to home directory.

    Returns a confirmation or error message. Actually changes os.getcwd().
    """
    # Expand ~ and environment variables
    target = os.path.expanduser(path) if path else os.path.expanduser("~")
    target = os.path.expandvars(target)
    # Resolve relative paths against cwd
    if not os.path.isabs(target):
        target = os.path.join(os.getcwd(), target)
    target = os.path.normpath(target)

    if not os.path.exists(target):
        return f"[ERROR] Directory not found: {target}"
    if not os.path.isdir(target):
        return f"[ERROR] Not a directory: {target}"

    try:
        os.chdir(target)
        return f"[OK] Changed directory to {target}"
    except OSError as e:
        return f"[ERROR] Cannot change directory: {e}"


def _update_system_prompt_cwd(messages: list[dict]) -> None:
    """Update the cwd line in the system prompt after /cd.

    Finds the first system message and updates the 'Current working directory' line
    so the agent's context stays fresh. Also refreshes git context and project
    context file (removing old context and loading the appropriate file for the
    new directory).
    """
    if not messages or messages[0].get("role") != "system":
        return

    content = messages[0].get("content", "")
    if not content:
        return

    lines = content.split("\n")
    updated = False
    for i, line in enumerate(lines):
        if line.startswith("Current working directory:"):
            lines[i] = f"Current working directory: {os.getcwd()}"
            updated = True
            break

    if updated:
        # Remove old project context and git context sections.
        # These are identified by headers starting with "# Git Context" or
        # "# Project Context". A section runs from its header until the next
        # known section header or end of content.
        _REMOVE_SECTIONS = ("# Git Context", "# Project Context")
        # Known section headers that signal the start of a new section
        _KNOWN_SECTIONS = (
            "# Git Context", "# Project Context", "# Loaded Skills",
            "# Project Memories",
        )
        new_lines = []
        skip_section = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(_REMOVE_SECTIONS):
                skip_section = True
                continue
            if skip_section:
                # End the skip when we hit a known section header that
                # isn't one we're removing (e.g. "# Loaded Skills")
                if any(stripped.startswith(h) for h in _KNOWN_SECTIONS
                       if not stripped.startswith(_REMOVE_SECTIONS)):
                    skip_section = False
                    new_lines.append(line)
                    continue
                # Still inside a section we want to remove — skip this line
                continue
            new_lines.append(line)

        # Add fresh git context
        git_ctx = _git_context()
        if git_ctx:
            new_lines.append(git_ctx)

        # Add fresh project context file
        ctx_result = _find_context_file(os.getcwd())
        if ctx_result:
            ctx_path, ctx_name = ctx_result
            try:
                with open(ctx_path, encoding="utf-8") as fh:
                    ctx_content = fh.read()
                new_lines.append(f"\n# Project Context ({ctx_name})\n{ctx_content}")
            except Exception:
                pass

        messages[0]["content"] = "\n".join(new_lines)


def _project_tree(path: str = ".", max_depth: int = 4) -> str:
    """Display project directory tree structure.

    Ignores common noise directories (.git, node_modules, __pycache__, .venv, etc.)
    and shows a visual tree with indentation.

    Args:
        path: Root directory to start from.
        max_depth: Maximum depth to traverse.

    Returns a tree-formatted string.
    """
    root = Path(path)
    if not root.exists():
        return f"[ERROR] Path not found: {path}"
    if not root.is_dir():
        return f"[ERROR] Not a directory: {path}"

    # Directories to skip (common noise)
    IGNORE_DIRS = {
        ".git", "node_modules", "__pycache__", ".venv", "venv",
        ".tox", ".mypy_cache", ".pytest_cache", ".hg", ".svn",
        "dist", "build", ".eggs", ".idea", ".vscode",
        "target", "vendor",  # Rust (target) and Go (vendor) build artifacts
    }

    file_count = 0
    dir_count = 0

    def _walk(directory: Path, prefix: str, depth: int) -> list[str]:
        nonlocal file_count, dir_count
        lines = []

        try:
            entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            lines.append(f"{prefix}[permission denied]")
            return lines

        # Filter out ignored directories
        entries = [e for e in entries if e.name not in IGNORE_DIRS]

        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            child_prefix = "    " if is_last else "│   "

            if entry.is_dir():
                dir_count += 1
                lines.append(f"{prefix}{connector}{entry.name}/")
                if depth < max_depth:
                    lines.extend(_walk(entry, prefix + child_prefix, depth + 1))
            else:
                file_count += 1
                lines.append(f"{prefix}{connector}{entry.name}")

        return lines

    tree_lines = [f"{root.name}/"]
    tree_lines.extend(_walk(root, "", 1))
    tree_lines.append(f"\n{file_count} file(s), {dir_count} director(ies)")

    return "\n".join(tree_lines)


# ── Language detection for /count ────────────────────────────────────

# Extension → (language_name, category)
# category: "code", "markup", "style", "data", "config"
_LANG_MAP: dict[str, tuple[str, str]] = {
    # Code
    ".py": ("Python", "code"),
    ".pyi": ("Python", "code"),
    ".js": ("JavaScript", "code"),
    ".jsx": ("JavaScript", "code"),
    ".ts": ("TypeScript", "code"),
    ".tsx": ("TypeScript", "code"),
    ".rs": ("Rust", "code"),
    ".go": ("Go", "code"),
    ".java": ("Java", "code"),
    ".kt": ("Kotlin", "code"),
    ".c": ("C", "code"),
    ".h": ("C/C++ Header", "code"),
    ".cpp": ("C++", "code"),
    ".cc": ("C++", "code"),
    ".cxx": ("C++", "code"),
    ".hpp": ("C++ Header", "code"),
    ".cs": ("C#", "code"),
    ".rb": ("Ruby", "code"),
    ".php": ("PHP", "code"),
    ".swift": ("Swift", "code"),
    ".scala": ("Scala", "code"),
    ".r": ("R", "code"),
    ".R": ("R", "code"),
    ".lua": ("Lua", "code"),
    ".sh": ("Shell", "code"),
    ".bash": ("Shell", "code"),
    ".zsh": ("Shell", "code"),
    ".sql": ("SQL", "code"),
    # Markup / docs
    ".md": ("Markdown", "markup"),
    ".rst": ("reStructuredText", "markup"),
    ".html": ("HTML", "markup"),
    ".htm": ("HTML", "markup"),
    ".xml": ("XML", "markup"),
    ".yaml": ("YAML", "markup"),
    ".yml": ("YAML", "markup"),
    ".toml": ("TOML", "markup"),
    # Style
    ".css": ("CSS", "style"),
    ".scss": ("SCSS", "style"),
    ".less": ("Less", "style"),
    # Data
    ".json": ("JSON", "data"),
    ".csv": ("CSV", "data"),
    ".tsv": ("TSV", "data"),
    # Config
    ".ini": ("INI", "config"),
    ".cfg": ("INI", "config"),
    ".env": ("Env", "config"),
}

# Dirs to always skip during counting
_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".hg", ".svn",
    "dist", "build", ".eggs", ".idea", ".vscode",
    "target", "vendor", ".next", ".nuxt", ".cache",
    "coverage", ".coverage", "htmlcov", ".ruff_cache",
}


def _run_count_command(workdir: str | None = None) -> str:
    """Count lines of code by language.

    Walks the project tree (skipping noise dirs), identifies file types,
    and reports line counts per language with a summary total.
    """
    cwd = workdir or os.getcwd()
    p = Path(cwd)

    if not p.exists():
        return f"{RED}[ERROR] Directory not found: {cwd}{RESET}"
    if not p.is_dir():
        return f"{RED}[ERROR] Not a directory: {cwd}{RESET}"

    # Collect stats: {lang: (file_count, line_count)}
    lang_stats: dict[str, tuple[int, int]] = {}
    other_files = 0
    other_lines = 0

    for root, dirs, files in os.walk(p):
        # Skip noise directories
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]

        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, encoding="utf-8", errors="ignore") as fh:
                    line_count = sum(1 for _ in fh)
            except (OSError, PermissionError):
                continue

            ext = os.path.splitext(fname)[1]
            if ext in _LANG_MAP:
                lang, _ = _LANG_MAP[ext]
                fc, lc = lang_stats.get(lang, (0, 0))
                lang_stats[lang] = (fc + 1, lc + line_count)
            elif fname.startswith(".") or fname.endswith((".lock", ".map", ".min.js", ".min.css")):
                # Skip lockfiles, source maps, minified files, dotfiles
                continue
            else:
                other_files += 1
                other_lines += line_count

    if not lang_stats and other_files == 0:
        return f"{DIM}No source files found{RESET}"

    # Format output
    lines = [f"{BOLD}Code Statistics{RESET}\n"]

    # Sort by line count descending
    sorted_langs = sorted(lang_stats.items(), key=lambda x: x[1][1], reverse=True)

    total_files = 0
    total_lines = 0

    for lang, (fc, lc) in sorted_langs:
        lines.append(f"  {CYAN}{lang:<20}{RESET} {fc:>4} file(s)  {lc:>6} lines")
        total_files += fc
        total_lines += lc

    if other_files > 0:
        lines.append(f"  {DIM}{'Other':<20} {other_files:>4} file(s)  {other_lines:>6} lines{RESET}")
        total_files += other_files
        total_lines += other_lines

    lines.append(f"\n  {BOLD}Total:{RESET}  {total_files} file(s)  {total_lines} lines")

    return "\n".join(lines)


def _git_undo(workdir: str | None = None) -> str:
    """Undo uncommitted changes: restore modified/deleted files, remove untracked.

    This is the equivalent of `git checkout . && git clean -fd` — a "panic button"
    for reverting working tree changes. Only affects the working tree, not history.

    Args:
        workdir: Working directory (defaults to cwd).

    Returns a human-readable result message.
    """
    cwd = workdir or os.getcwd()

    # Check we're in a git repo
    check = _run_git("rev-parse", "--is-inside-work-tree", workdir=cwd)
    if check.returncode != 0:
        return "[ERROR] Not a git repo"

    # Check for any changes
    status = _run_git("status", "--porcelain", workdir=cwd)
    if status.returncode != 0:
        return f"[ERROR] git status failed: {status.stderr.strip()}"

    if not status.stdout.strip():
        return "[No changes to undo — working tree clean]"

    changes = status.stdout.splitlines()
    reverted = []
    cleaned = []

    for line in changes:
        if not line.strip():
            continue
        # porcelain format: XY PATH — 2 status chars + space + filename
        # XY can include spaces (e.g. " M" for unstaged modification)
        xy = line[:2]
        filename = line[3:]

        if xy[1] == "?" or xy == "??":
            # Untracked file — remove it
            cleaned.append(filename)
        else:
            # Modified, deleted, staged, etc. — restore from HEAD
            reverted.append(filename)

    # Restore tracked files to HEAD state
    if reverted:
        checkout = _run_git("checkout", "HEAD", "--", *reverted, workdir=cwd)
        if checkout.returncode != 0:
            return f"[ERROR] git checkout failed: {checkout.stderr.strip()}"

    # Remove untracked files
    if cleaned:
        clean = _run_git("clean", "-f", "--", *cleaned, workdir=cwd)
        if clean.returncode != 0:
            return f"[ERROR] git clean failed: {clean.stderr.strip()}"

    parts = []
    if reverted:
        parts.append(f"Restored {len(reverted)} file(s) to HEAD state")
    if cleaned:
        parts.append(f"Removed {len(cleaned)} untracked file(s)")
    return "[OK] " + ", ".join(parts)


# ── Project memory system ─────────────────────────────────────────────

def _get_memory_dir() -> Path:
    """Get the .yoyo directory in the current working directory."""
    return Path(os.getcwd()) / ".yoyo"


def _get_memory_file(memory_dir: Path | None = None) -> Path:
    """Get the path to the memories JSON file."""
    return (memory_dir or _get_memory_dir()) / "memories.json"


def _read_memories(memory_dir: Path | None = None) -> list[dict]:
    """Read memories from the JSON file. Returns empty list if no file."""
    mem_file = _get_memory_file(memory_dir)
    if not mem_file.exists():
        return []
    try:
        return json.loads(mem_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception):
        return []


def _write_memories(memories: list[dict], memory_dir: Path | None = None) -> None:
    """Write memories to the JSON file. Removes file if empty."""
    mem_dir = memory_dir or _get_memory_dir()
    mem_file = mem_dir / "memories.json"
    if not memories:
        # Clean up empty file
        if mem_file.exists():
            mem_file.unlink()
        return
    mem_dir.mkdir(parents=True, exist_ok=True)
    mem_file.write_text(json.dumps(memories, indent=2, ensure_ascii=False), encoding="utf-8")


def _add_memory(text: str, memory_dir: Path | None = None) -> str:
    """Add a project memory. Returns a confirmation message."""
    if not text.strip():
        return "[ERROR] Memory text cannot be empty"

    from datetime import datetime
    memories = _read_memories(memory_dir)

    # Auto-increment ID
    next_id = max((m.get("id", 0) for m in memories), default=0) + 1

    memories.append({
        "id": next_id,
        "text": text.strip(),
        "timestamp": datetime.now().isoformat(),
    })
    _write_memories(memories, memory_dir)
    return f"[OK] Remembered #{next_id}: {text.strip()}"


def _list_memories(memory_dir: Path | None = None) -> str:
    """List all project memories. Returns a formatted string."""
    memories = _read_memories(memory_dir)
    if not memories:
        return "No memories saved. Use /remember <text> to add one."

    lines = [f"{BOLD}Project Memories:{RESET}"]
    for m in memories:
        lines.append(f"  {CYAN}#{m['id']}{RESET} {m['text']}")
    return "\n".join(lines)


def _forget_memory(mem_id: int, memory_dir: Path | None = None) -> str:
    """Remove a memory by ID. Returns a confirmation message."""
    memories = _read_memories(memory_dir)
    if not memories:
        return "[ERROR] No memories to forget"

    original_len = len(memories)
    memories = [m for m in memories if m.get("id") != mem_id]

    if len(memories) == original_len:
        return f"[ERROR] Memory #{mem_id} not found"

    _write_memories(memories, memory_dir)
    return f"[OK] Forgot memory #{mem_id}"


def _load_memories_into_prompt(memory_dir: Path | None = None) -> str:
    """Load memories formatted for injection into the system prompt."""
    memories = _read_memories(memory_dir)
    if not memories:
        return ""

    lines = ["# Project Memories"]
    for m in memories:
        lines.append(f"- {m['text']}")
    return "\n".join(lines)


def _run_backups_command(args: str) -> str:
    """Handle /backups command — list, show, or restore file backups.

    Subcommands:
        /backups            List all backups
        /backups show N     Show content of backup #N
        /backups restore N  Restore backup #N to original file path
    """
    from .tools import _BACKUP_SUBDIR, _BACKUP_DIR_NAME, _format_size

    backup_dir = Path(_BACKUP_DIR_NAME) / _BACKUP_SUBDIR
    parts = args.strip().split()

    # ── Subcommand dispatch ────────────────────────────────────────
    if parts and parts[0] == "show":
        return _backups_show(backup_dir, parts[1:] if len(parts) > 1 else [])

    if parts and parts[0] == "restore":
        return _backups_restore(backup_dir, parts[1:] if len(parts) > 1 else [])

    # ── Default: list backups ─────────────────────────────────────
    if not backup_dir.exists() or not backup_dir.is_dir():
        return f"{DIM}No backups found.{RESET}"

    backups = sorted(backup_dir.iterdir(), key=lambda f: f.name)
    if not backups:
        return f"{DIM}No backups found.{RESET}"

    lines = [f"{BOLD}File Backups{RESET} ({len(backups)} total)"]
    lines.append(f"{DIM}  Use /backups show <N> to view, /backups restore <N> to restore{RESET}")
    lines.append("")

    for i, b in enumerate(backups, 1):
        size = b.stat().st_size
        # Parse the backup name to extract the original filename and timestamp
        name = b.stem  # e.g. "test_txt_20260613_143022"
        # Remove timestamp suffix (YYYYMMDD_HHMMSS[_N])
        ts_match = re.match(r"^(.+?)_(\d{8}_\d{6})(?:_\d+)?$", name)
        if ts_match:
            orig_name = ts_match.group(1).replace("_", os.sep)
            ts = ts_match.group(2)
            # Format timestamp nicely
            try:
                from datetime import datetime
                dt = datetime.strptime(ts, "%Y%m%d_%H%M%S")
                ts_display = dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                ts_display = ts
        else:
            orig_name = name
            ts_display = "unknown"
        lines.append(f"  {CYAN}{i:>3}{RESET}  {orig_name}  {DIM}({ts_display}, {_format_size(size)}){RESET}")

    return "\n".join(lines)


def _backups_show(backup_dir: Path, args: list[str]) -> str:
    """Show content of a backup by index number."""
    if not args:
        return f"{YELLOW}Usage: /backups show <N>{RESET}"

    try:
        idx = int(args[0])
    except ValueError:
        return f"{RED}Invalid index: {args[0]}{RESET}"

    if not backup_dir.exists():
        return f"{RED}No backups found{RESET}"

    backups = sorted(backup_dir.iterdir(), key=lambda f: f.name)
    if idx < 1 or idx > len(backups):
        return f"{RED}Backup #{idx} not found ({len(backups)} available){RESET}"

    backup = backups[idx - 1]
    try:
        content = backup.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"{RED}Error reading backup: {e}{RESET}"

    name = backup.stem
    ts_match = re.match(r"^(.+?)_(\d{8}_\d{6})(?:_\d+)?$", name)
    orig_name = ts_match.group(1).replace("_", os.sep) if ts_match else name

    lines = [f"{BOLD}Backup #{idx}{RESET} → {orig_name}"]
    lines.append(f"{DIM}{'─' * 40}{RESET}")
    # Show content (truncated if very large)
    if len(content) > 5000:
        lines.append(content[:5000])
        lines.append(f"\n{DIM}... (truncated, {len(content)} chars total){RESET}")
    else:
        lines.append(content)
    return "\n".join(lines)


def _backups_restore(backup_dir: Path, args: list[str]) -> str:
    """Restore a backup by index number to its original file path."""
    if not args:
        return f"{YELLOW}Usage: /backups restore <N>{RESET}"

    try:
        idx = int(args[0])
    except ValueError:
        return f"{RED}Invalid index: {args[0]}{RESET}"

    if not backup_dir.exists():
        return f"{RED}No backups found{RESET}"

    backups = sorted(backup_dir.iterdir(), key=lambda f: f.name)
    if idx < 1 or idx > len(backups):
        return f"{RED}Backup #{idx} not found ({len(backups)} available){RESET}"

    backup = backups[idx - 1]
    name = backup.stem
    ts_match = re.match(r"^(.+?)_(\d{8}_\d{6})(?:_\d+)?$", name)
    if not ts_match:
        return f"{RED}Cannot determine original file path from backup name{RESET}"

    orig_name = ts_match.group(1).replace("_", os.sep)
    orig_path = Path(orig_name)

    try:
        import shutil
        # Back up the current file before restoring (so we don't lose it either)
        if orig_path.exists():
            from .tools import _backup_file
            _backup_file(orig_path)

        shutil.copy2(str(backup), str(orig_path))
        return f"{GREEN}  ✓ Restored {orig_name} from backup #{idx}{RESET}"
    except Exception as e:
        return f"{RED}Error restoring backup: {e}{RESET}"


def _run_health_check(workdir: str | None = None) -> str:
    """Run build/test/lint diagnostics for the project.

    Detects project type (Python, Node, etc.) and runs appropriate checks.
    Returns a formatted summary of results.
    """
    cwd = workdir or os.getcwd()
    p = Path(cwd)

    if not p.exists():
        return f"[ERROR] Directory not found: {cwd}"
    if not p.is_dir():
        return f"[ERROR] Not a directory: {cwd}"

    results = []
    project_types = []

    def _run(cmd: list[str], label: str) -> tuple[bool, str]:
        """Run a command and return (success, output_summary)."""
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60, cwd=cwd
            )
            ok = result.returncode == 0
            # Summarize output — first few lines
            output = result.stdout.strip() or result.stderr.strip()
            lines = output.splitlines()
            if len(lines) > 10:
                summary = "\n".join(lines[:10]) + f"\n  ... ({len(lines) - 10} more lines)"
            else:
                summary = output
            return ok, summary
        except FileNotFoundError:
            return False, f"{cmd[0]} not found"
        except subprocess.TimeoutExpired:
            return False, "timed out"
        except Exception as e:
            return False, str(e)

    # Detect Python project
    is_python = (
        (p / "pyproject.toml").exists()
        or (p / "setup.py").exists()
        or (p / "setup.cfg").exists()
        or (p / "requirements.txt").exists()
    )

    # Detect Node project
    is_node = (p / "package.json").exists()

    # Detect Rust project
    is_rust = (p / "Cargo.toml").exists()

    # Detect Go project
    is_go = (p / "go.mod").exists()

    # Detect Java/Maven project
    is_java = (p / "pom.xml").exists()

    if is_python:
        project_types.append("Python")
        # Run pytest
        ok, output = _run(["python", "-m", "pytest", "--tb=short", "-q"], "pytest")
        status = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        results.append(f"  {status} pytest: {'pass' if ok else 'fail'}")
        if not ok and output:
            for line in output.splitlines()[:5]:
                results.append(f"      {line}")

        # Check for linting tools
        for linter, cmd in [("ruff", ["ruff", "check", "."]), ("flake8", ["flake8", "."])]:
            ok, output = _run(cmd, linter)
            if "not found" not in output:
                status = f"{GREEN}✓{RESET}" if ok else f"{YELLOW}⚠{RESET}"
                findings = ""
                if not ok and output:
                    count = len(output.splitlines())
                    findings = f" ({count} finding{'s' if count != 1 else ''})"
                results.append(f"  {status} {linter}: {'clean' if ok else 'issues found'}{findings}")
                break  # Only run the first available linter

        # Check for type checking
        ok, output = _run(["mypy", ".", "--no-error-summary"], "mypy")
        if "not found" not in output:
            status = f"{GREEN}✓{RESET}" if ok else f"{YELLOW}⚠{RESET}"
            results.append(f"  {status} mypy: {'clean' if ok else 'type errors found'}")

    if is_node:
        project_types.append("Node.js")
        # Run npm test
        ok, output = _run(["npm", "test"], "npm test")
        status = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        results.append(f"  {status} npm test: {'pass' if ok else 'fail'}")

        # Run npm lint
        ok, output = _run(["npm", "run", "lint"], "npm lint")
        if "not found" not in output and "missing script" not in output.lower():
            status = f"{GREEN}✓{RESET}" if ok else f"{YELLOW}⚠{RESET}"
            results.append(f"  {status} npm lint: {'clean' if ok else 'issues found'}")

    if is_rust:
        project_types.append("Rust")
        # Run cargo test
        ok, output = _run(["cargo", "test", "--quiet"], "cargo test")
        status = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        results.append(f"  {status} cargo test: {'pass' if ok else 'fail'}")
        if not ok and output:
            for line in output.splitlines()[:5]:
                results.append(f"      {line}")

        # Run cargo check (faster than build, catches compile errors)
        ok, output = _run(["cargo", "check", "--quiet"], "cargo check")
        if "not found" not in output:
            status = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
            results.append(f"  {status} cargo check: {'ok' if ok else 'compile errors'}")

        # Run clippy if available
        ok, output = _run(["cargo", "clippy", "--quiet"], "clippy")
        if "not found" not in output:
            status = f"{GREEN}✓{RESET}" if ok else f"{YELLOW}⚠{RESET}"
            results.append(f"  {status} clippy: {'clean' if ok else 'warnings/issues'}")

    if is_go:
        project_types.append("Go")
        # Run go test
        ok, output = _run(["go", "test", "./..."], "go test")
        status = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        results.append(f"  {status} go test: {'pass' if ok else 'fail'}")
        if not ok and output:
            for line in output.splitlines()[:5]:
                results.append(f"      {line}")

        # Run go vet
        ok, output = _run(["go", "vet", "./..."], "go vet")
        if "not found" not in output:
            status = f"{GREEN}✓{RESET}" if ok else f"{YELLOW}⚠{RESET}"
            results.append(f"  {status} go vet: {'clean' if ok else 'issues found'}")

    if is_java:
        project_types.append("Java")
        # Run Maven test
        ok, output = _run(["mvn", "test", "-q"], "mvn test")
        status = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        results.append(f"  {status} mvn test: {'pass' if ok else 'fail'}")
        if not ok and output:
            for line in output.splitlines()[:5]:
                results.append(f"      {line}")

    if not project_types:
        results.append(f"  {DIM}No recognized project type found{RESET}")

    # Git status summary
    git_check = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True, timeout=5, cwd=cwd,
    )
    git_info = ""
    if git_check.returncode == 0:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=5, cwd=cwd,
        )
        if status.returncode == 0:
            changes = len([l for l in status.stdout.strip().splitlines() if l.strip()])
            if changes == 0:
                git_info = f"  {GREEN}✓{RESET} git: clean working tree"
            else:
                git_info = f"  {YELLOW}⚠{RESET} git: {changes} uncommitted change(s)"

    header = f"{BOLD}Health Check{RESET} — {', '.join(project_types) or 'Unknown'} project"
    parts = [header] + results
    if git_info:
        parts.append(git_info)

    return "\n".join(parts)


def _run_test_command(workdir: str | None = None, args: str = "") -> str:
    """Detect project type and run tests.

    Simpler and more focused than /health — just runs the test suite
    and shows results. Returns a formatted summary.

    Args:
        workdir: Working directory to run tests in. Defaults to cwd.
        args: Extra arguments to pass to the test runner (e.g. test file
              paths, pytest flags like '-k pattern', '-x', '-v').
    """
    cwd = workdir or os.getcwd()
    p = Path(cwd)

    if not p.exists():
        return f"[ERROR] Directory not found: {cwd}"
    if not p.is_dir():
        return f"[ERROR] Not a directory: {cwd}"

    # Parse extra args into a list for subprocess
    extra = args.split() if args else []

    # Detect Python project
    is_python = (
        (p / "pyproject.toml").exists()
        or (p / "setup.py").exists()
        or (p / "setup.cfg").exists()
        or (p / "requirements.txt").exists()
    )

    # Detect Node project
    is_node = (p / "package.json").exists()

    # Detect Rust project
    is_rust = (p / "Cargo.toml").exists()

    # Detect Go project
    is_go = (p / "go.mod").exists()

    # Detect Java/Maven project
    is_java = (p / "pom.xml").exists()

    if is_python:
        try:
            cmd = ["python", "-m", "pytest", "--tb=short", "-q"] + extra
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=120, cwd=cwd,
            )
            output = result.stdout.strip() or result.stderr.strip()

            if result.returncode == 0:
                # Show last few lines of summary
                lines = output.splitlines()
                summary = lines[-3:] if len(lines) > 3 else lines
                return f"{GREEN}✓ Tests passed{RESET}\n" + "\n".join(summary)
            else:
                lines = output.splitlines()
                # Show summary line + a few failure details
                summary = lines[-5:] if len(lines) > 5 else lines
                return f"{RED}✗ Tests failed{RESET}\n" + "\n".join(summary)

        except FileNotFoundError:
            return f"{YELLOW}pytest not installed — run: pip install pytest{RESET}"
        except subprocess.TimeoutExpired:
            return f"{RED}✗ Tests timed out (120s){RESET}"

    elif is_node:
        try:
            # For Node, pass extra args after -- to npm test
            cmd = ["npm", "test"]
            if extra:
                cmd += ["--"] + extra
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=120, cwd=cwd,
            )
            output = result.stdout.strip() or result.stderr.strip()
            lines = output.splitlines()
            summary = lines[-5:] if len(lines) > 5 else lines

            if result.returncode == 0:
                return f"{GREEN}✓ Tests passed{RESET}\n" + "\n".join(summary)
            else:
                return f"{RED}✗ Tests failed{RESET}\n" + "\n".join(summary)

        except FileNotFoundError:
            return f"{YELLOW}npm not found — install Node.js{RESET}"
        except subprocess.TimeoutExpired:
            return f"{RED}✗ Tests timed out (120s){RESET}"

    elif is_rust:
        try:
            # For Rust, extra args after -- to cargo test
            cmd = ["cargo", "test", "--quiet"]
            if extra:
                cmd += ["--"] + extra
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=120, cwd=cwd,
            )
            output = result.stdout.strip() or result.stderr.strip()

            if result.returncode == 0:
                lines = output.splitlines()
                summary = lines[-3:] if len(lines) > 3 else lines
                return f"{GREEN}✓ Rust tests passed{RESET}\n" + "\n".join(summary)
            else:
                lines = output.splitlines()
                summary = lines[-5:] if len(lines) > 5 else lines
                return f"{RED}✗ Rust tests failed{RESET}\n" + "\n".join(summary)

        except FileNotFoundError:
            return f"{YELLOW}cargo not found — install Rust (https://rustup.rs){RESET}"
        except subprocess.TimeoutExpired:
            return f"{RED}✗ Tests timed out (120s){RESET}"

    elif is_go:
        try:
            # For Go, extra args can be packages or flags
            cmd = ["go", "test"]
            if extra:
                cmd += extra
            else:
                cmd.append("./...")
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=120, cwd=cwd,
            )
            output = result.stdout.strip() or result.stderr.strip()
            lines = output.splitlines()
            summary = lines[-5:] if len(lines) > 5 else lines

            if result.returncode == 0:
                return f"{GREEN}✓ Go tests passed{RESET}\n" + "\n".join(summary)
            else:
                return f"{RED}✗ Go tests failed{RESET}\n" + "\n".join(summary)

        except FileNotFoundError:
            return f"{YELLOW}go not found — install Go (https://go.dev/dl){RESET}"
        except subprocess.TimeoutExpired:
            return f"{RED}✗ Tests timed out (120s){RESET}"

    elif is_java:
        try:
            # For Maven, extra args as -Dtest=... or other flags
            cmd = ["mvn", "test", "-q"]
            if extra:
                cmd += extra
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=120, cwd=cwd,
            )
            output = result.stdout.strip() or result.stderr.strip()
            lines = output.splitlines()
            summary = lines[-5:] if len(lines) > 5 else lines

            if result.returncode == 0:
                return f"{GREEN}✓ Java tests passed (Maven){RESET}\n" + "\n".join(summary)
            else:
                return f"{RED}✗ Java tests failed (Maven){RESET}\n" + "\n".join(summary)

        except FileNotFoundError:
            return f"{YELLOW}mvn not found — install Maven (https://maven.apache.org){RESET}"
        except subprocess.TimeoutExpired:
            return f"{RED}✗ Tests timed out (120s){RESET}"

    else:
        return f"{DIM}No recognized project type found — can't determine test command{RESET}"


def _run_cat_command(args: str) -> str:
    """Quick file viewer — display file content with line numbers.

    Usage: /cat <file> [offset] [limit]

    Supports optional line range:
      /cat foo.py         Show entire file (up to 500 lines)
      /cat foo.py 10 20   Show lines 10-29 (offset 10, limit 20)
    """
    parts = args.strip().split()

    if not parts:
        return f"{YELLOW}Usage: /cat <file> [offset] [limit]{RESET}"

    filepath = parts[0]
    offset = int(parts[1]) if len(parts) > 1 else 1
    limit = int(parts[2]) if len(parts) > 2 else 500

    p = Path(filepath)
    if not p.exists():
        return f"{RED}  File not found: {filepath}{RESET}"
    if not p.is_file():
        return f"{RED}  Not a file: {filepath}{RESET}"

    # Check for binary file — with-statement avoids leaking file descriptors
    try:
        with p.open("rb") as fh:
            chunk = fh.read(8192)
        if b"\x00" in chunk:
            return f"{RED}  Binary file, cannot display: {filepath}{RESET}"
    except OSError:
        pass

    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return f"{RED}  Error reading file: {e}{RESET}"

    total = len(lines)

    # Clamp offset to valid range
    if offset < 1:
        offset = 1
    if offset > total:
        return f"{YELLOW}  File has {total} lines — offset {offset} is past the end{RESET}"

    # Apply limit
    end = min(offset - 1 + limit, total)
    selected = lines[offset - 1:end]

    # Format with line numbers
    width = len(str(end))
    formatted = []
    for i, line in enumerate(selected, start=offset):
        formatted.append(f"  {DIM}{i:>{width}}│{RESET} {line}")

    output = "\n".join(formatted)

    # Add file info header/footer
    header = f"{BOLD}  {filepath}{RESET} ({total} lines"
    if offset > 1 or end < total:
        header += f", showing {offset}-{end}"
    header += ")"

    return f"{header}\n{output}"


def _run_head_command(args: str) -> str:
    """Show the first N lines of a file (default 10).

    More efficient than /cat for large files — reads only what's needed
    when the file is large, rather than loading the entire file.

    Usage: /head <file> [count]
    """
    parts = args.strip().split()

    if not parts:
        return f"{YELLOW}Usage: /head <file> [count] (default 10){RESET}"

    filepath = parts[0]
    count = int(parts[1]) if len(parts) > 1 else 10

    if count < 1:
        return f"{YELLOW}Count must be at least 1{RESET}"

    p = Path(filepath)
    if not p.exists():
        return f"{RED}  File not found: {filepath}{RESET}"
    if not p.is_file():
        return f"{RED}  Not a file: {filepath}{RESET}"

    # Check for binary file — with-statement avoids leaking file descriptors
    try:
        with p.open("rb") as fh:
            chunk = fh.read(8192)
        if b"\x00" in chunk:
            return f"{RED}  Binary file, cannot display: {filepath}{RESET}"
    except OSError:
        pass

    # For efficiency, read only the needed lines when possible
    try:
        selected = []
        total = 0
        with p.open("r", encoding="utf-8", errors="replace") as f:
            for i, line_text in enumerate(f, 1):
                total = i
                if i <= count:
                    selected.append((i, line_text.rstrip("\n")))
                # Keep counting to get total — but for very large files,
                # stop counting after we have enough (estimate total)
                if i > count and i > 10000:
                    # For very large files, just note the total is ">count"
                    total = None
                    break

        if total is None:
            total_str = f">{count}"
        else:
            total_str = str(total)

        # Format with line numbers
        if selected:
            width = len(str(selected[-1][0]))
            formatted = []
            for lineno, line_text in selected:
                formatted.append(f"  {DIM}{lineno:>{width}}│{RESET} {line_text}")
            output = "\n".join(formatted)
        else:
            output = f"{DIM}  (empty file){RESET}"

        header = f"{BOLD}  {filepath}{RESET} ({total_str} lines, first {min(count, len(selected))})"
        return f"{header}\n{output}"

    except OSError as e:
        return f"{RED}  Error reading file: {e}{RESET}"


def _run_tail_command(args: str) -> str:
    """Show the last N lines of a file (default 10).

    For large files, reads from the end efficiently rather than loading
    the entire file into memory.

    Usage: /tail <file> [count]
    """
    parts = args.strip().split()

    if not parts:
        return f"{YELLOW}Usage: /tail <file> [count] (default 10){RESET}"

    filepath = parts[0]
    count = int(parts[1]) if len(parts) > 1 else 10

    if count < 1:
        return f"{YELLOW}Count must be at least 1{RESET}"

    p = Path(filepath)
    if not p.exists():
        return f"{RED}  File not found: {filepath}{RESET}"
    if not p.is_file():
        return f"{RED}  Not a file: {filepath}{RESET}"

    # Check for binary file — with-statement avoids leaking file descriptors
    try:
        with p.open("rb") as fh:
            chunk = fh.read(8192)
        if b"\x00" in chunk:
            return f"{RED}  Binary file, cannot display: {filepath}{RESET}"
    except OSError:
        pass

    try:
        # Read all lines — for tail, we need to know the total count
        # For very large files this is unavoidable
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(lines)

        if total == 0:
            return f"{DIM}  {filepath} (empty file){RESET}"

        # Select last N lines
        start = max(0, total - count)
        selected = lines[start:]

        # Format with original line numbers
        width = len(str(total))
        formatted = []
        for i, line_text in enumerate(selected, start=start + 1):
            formatted.append(f"  {DIM}{i:>{width}}│{RESET} {line_text}")
        output = "\n".join(formatted)

        header = f"{BOLD}  {filepath}{RESET} ({total} lines, last {len(selected)})"
        return f"{header}\n{output}"
    except OSError as e:
        return f"{RED}  Error reading file: {e}{RESET}"


def _run_du_command(args: str) -> str:
    """Show file and directory sizes in human-readable format.

    Usage: /du [path]
    If no path is given, shows sizes in the current directory.
    Files are sorted by size (largest first).
    """
    import subprocess as _sp

    target = args.strip() or "."

    p = Path(target)
    if not p.exists():
        return f"{RED}  Path not found: {target}{RESET}"

    if p.is_file():
        size = p.stat().st_size
        return f"  {_human_size(size)}  {p.name}"

    # Directory: list files sorted by size
    entries = []
    try:
        for child in sorted(p.iterdir()):
            if child.is_file():
                entries.append((child.stat().st_size, child.name))
            elif child.is_dir():
                # Get directory size via du
                try:
                    result = _sp.run(
                        ["du", "-sk", str(child)],
                        capture_output=True, text=True, timeout=5,
                    )
                    if result.returncode == 0:
                        kb = int(result.stdout.split()[0])
                        entries.append((kb * 1024, child.name + "/"))
                except Exception:
                    entries.append((0, child.name + "/"))
    except PermissionError:
        return f"{RED}  Permission denied: {target}{RESET}"

    if not entries:
        return f"{DIM}  {target} (empty directory){RESET}"

    # Sort by size, largest first
    entries.sort(key=lambda e: e[0], reverse=True)

    lines = []
    for size, name in entries:
        lines.append(f"  {_human_size(size):>8s}  {name}")

    total = sum(e[0] for e in entries)
    header = f"{BOLD}  {target}{RESET} ({len(entries)} items)"
    footer = f"  {'─' * 20}\n  {_human_size(total):>8s}  total"
    return f"{header}\n" + "\n".join(lines) + f"\n{footer}"


def _human_size(n: int) -> str:
    """Format a byte count as a human-readable size string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _run_find_command(args: str) -> str:
    """Find files by name pattern (glob syntax).

    Usage: /find <pattern>
    Supports ** for recursive matching, * for any substring.
    Searches from the current working directory.

    Args:
        args: Glob pattern to search for (e.g. "*.py", "*test*", "src/**/test_*.py").

    Returns:
        List of matching files with relative paths.
    """
    pattern = args.strip()

    if not pattern:
        return f"{YELLOW}Usage: /find <pattern>{RESET}\n{DIM}  Example: /find *.py, /find *test*, /find src/**/*.py{RESET}"

    cwd = Path(os.getcwd())
    matches = sorted(cwd.glob(f"**/{pattern}" if "/" not in pattern and "**" not in pattern else pattern))

    # Filter out directories — only show files
    matches = [m for m in matches if m.is_file()]

    # Filter out hidden files and common noise directories
    noise_dirs = {".git", "__pycache__", "node_modules", ".venv", ".mypy_cache", ".pytest_cache", ".tox"}
    filtered = []
    for m in matches:
        try:
            rel = m.relative_to(cwd)
        except ValueError:
            rel = m
        parts = rel.parts
        # Skip if any parent directory is a noise dir or starts with .
        if any(p in noise_dirs or p.startswith(".") for p in parts):
            continue
        filtered.append(rel)

    if not filtered:
        return f"{DIM}  No files found matching: {pattern}{RESET}"

    lines = [f"{BOLD}  Found {len(filtered)} file(s){RESET} matching {CYAN}{pattern}{RESET}"]
    for rel in filtered:
        lines.append(f"  {rel}")
    return "\n".join(lines)


def _run_wc_command(args: str) -> str:
    """Count lines, words, and characters in files.

    Usage: /wc <file> [file2 ...]

    Args:
        args: One or more file paths separated by spaces.

    Returns:
        Line/word/char counts for each file plus a total.
    """
    parts = args.strip().split()
    if not parts:
        return f"{YELLOW}Usage: /wc <file> [file2 ...]{RESET}"

    results = []
    total_lines = total_words = total_chars = 0
    errors = []

    for filepath in parts:
        p = Path(filepath)
        if not p.exists():
            errors.append(f"  {RED}{filepath}: not found{RESET}")
            continue
        if not p.is_file():
            errors.append(f"  {RED}{filepath}: not a file{RESET}")
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            words = len(content.split())
            chars = len(content)
            total_lines += lines
            total_words += words
            total_chars += chars
            results.append((filepath, lines, words, chars))
        except OSError as e:
            errors.append(f"  {RED}{filepath}: {e}{RESET}")

    if not results and not errors:
        return f"{DIM}  No files to count{RESET}"

    # Format as a table
    header = f"  {BOLD}{'lines':>8} {'words':>8} {'chars':>8}  file{RESET}"
    sep = f"  {'─' * 8} {'─' * 8} {'─' * 8}"
    lines = [header, sep]

    for filepath, l, w, c in results:
        lines.append(f"  {l:>8} {w:>8} {c:>8}  {filepath}")

    if len(results) > 1:
        lines.append(sep)
        lines.append(f"  {total_lines:>8} {total_words:>8} {total_chars:>8}  {BOLD}total{RESET}")

    if errors:
        lines.append("")
        lines.extend(errors)

    return "\n".join(lines)


def _run_edit_command(filepath: str) -> str:
    """Open a file in the user's $EDITOR (defaults to vim).

    Args:
        filepath: Path to the file to edit.

    Returns:
        Status message.
    """
    import subprocess

    if not filepath:
        return f"{YELLOW}Usage: /edit <file>{RESET}"

    p = Path(filepath)
    if not p.exists():
        return f"{RED}  File not found: {filepath}{RESET}"
    if not p.is_file():
        return f"{RED}  Not a file: {filepath}{RESET}"

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vim"

    try:
        subprocess.call([editor, str(p)])
        return f"{GREEN}  ✓ Opened {filepath} in {editor}{RESET}"
    except FileNotFoundError:
        return f"{RED}  Editor '{editor}' not found — set EDITOR env var{RESET}"
    except Exception as e:
        return f"{RED}  Error opening editor: {e}{RESET}"


def _run_init_command(workdir: str | None = None, force: bool = False) -> str:
    """Scan the project and generate a YOYO.md context file.

    Creates a YOYO.md file with project info: name, language, structure,
    test commands, and key files. Refuses to overwrite unless force=True.
    """
    cwd = workdir or os.getcwd()
    p = Path(cwd)

    if not p.exists() or not p.is_dir():
        return f"[ERROR] Directory not found: {cwd}"

    yoyo_path = p / "YOYO.md"

    # Don't overwrite existing YOYO.md unless forced
    if yoyo_path.exists() and not force:
        return f"{YELLOW}YOYO.md already exists — use /init --force to overwrite{RESET}"

    # Detect project type
    is_python = (
        (p / "pyproject.toml").exists()
        or (p / "setup.py").exists()
        or (p / "setup.cfg").exists()
        or (p / "requirements.txt").exists()
    )
    is_node = (p / "package.json").exists()
    is_rust = (p / "Cargo.toml").exists()
    is_go = (p / "go.mod").exists()
    is_java = (p / "pom.xml").exists()

    # Build project info
    project_name = p.name
    language = "unknown"
    test_cmd = "unknown"
    project_details = ""

    if is_python:
        language = "Python"
        test_cmd = "python -m pytest"
        # Try to read project name from pyproject.toml
        pyproject = p / "pyproject.toml"
        if pyproject.exists():
            content = pyproject.read_text()
            for line in content.splitlines():
                if line.strip().startswith("name"):
                    project_name = line.split("=", 1)[1].strip().strip("'\"")
                    break
        project_details = f"- Language: {language}\n- Test: `{test_cmd}`\n"

    elif is_node:
        language = "Node.js"
        try:
            pkg = json.loads((p / "package.json").read_text())
            project_name = pkg.get("name", project_name)
            test_cmd = pkg.get("scripts", {}).get("test", "npm test")
        except (json.JSONDecodeError, OSError):
            test_cmd = "npm test"
        project_details = f"- Language: {language}\n- Test: `npm test` (or `{test_cmd}`)\n"

    elif is_rust:
        language = "Rust"
        test_cmd = "cargo test"
        # Try to read project name from Cargo.toml
        cargo = p / "Cargo.toml"
        if cargo.exists():
            content = cargo.read_text()
            for line in content.splitlines():
                if line.strip().startswith("name"):
                    project_name = line.split("=", 1)[1].strip().strip("'\"")
                    break
        project_details = f"- Language: {language}\n- Test: `{test_cmd}`\n- Build: `cargo build`\n- Lint: `cargo clippy`\n"

    elif is_go:
        language = "Go"
        test_cmd = "go test ./..."
        # Read module name from go.mod
        gomod = p / "go.mod"
        if gomod.exists():
            content = gomod.read_text()
            for line in content.splitlines():
                if line.startswith("module "):
                    project_name = line.split(" ", 1)[1].strip()
                    break
        project_details = f"- Language: {language}\n- Test: `{test_cmd}`\n- Vet: `go vet ./...`\n"

    elif is_java:
        language = "Java (Maven)"
        test_cmd = "mvn test"
        project_details = f"- Language: {language}\n- Test: `{test_cmd}`\n- Build: `mvn package`\n"

    # Build directory tree (limited depth)
    def _build_tree(directory: Path, prefix: str = "", depth: int = 0, max_depth: int = 3) -> list[str]:
        if depth > max_depth:
            return [f"{prefix}..."]
        entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name))
        # Skip hidden and common ignored dirs
        skip = {".git", "__pycache__", "node_modules", ".venv", ".pytest_cache", ".mypy_cache", ".tox", "dist", "build", ".eggs", ".next", "target", "vendor"}
        lines = []
        for entry in entries:
            if entry.name.startswith(".") and entry.name not in {".env", ".github"}:
                continue
            if entry.name in skip:
                continue
            if entry.is_dir():
                lines.append(f"{prefix}{entry.name}/")
                lines.extend(_build_tree(entry, prefix + "  ", depth + 1, max_depth))
            else:
                lines.append(f"{prefix}{entry.name}")
        return lines

    tree_lines = _build_tree(p)
    tree_str = "\n".join(tree_lines[:50])  # Cap at 50 lines
    if len(tree_lines) > 50:
        tree_str += "\n  ... (truncated)"

    # Compose YOYO.md
    yoyo_content = f"""# {project_name}

## Project Overview
{project_details}
## Directory Structure
```
{tree_str}
```

## Notes
<!-- Add project-specific context and conventions here -->
"""

    yoyo_path.write_text(yoyo_content)
    return f"{GREEN}[OK] YOYO.md created — project context ready{RESET}"


def _run_fix_command(workdir: str | None = None) -> str:
    """Auto-fix build/lint errors by running formatters and fixers.

    Detects project type and runs appropriate fix tools:
    - Python: ruff fix, then black (if ruff unavailable)
    - Node.js: eslint --fix

    Returns a formatted summary of what was fixed.
    """
    cwd = workdir or os.getcwd()
    p = Path(cwd)

    if not p.exists():
        return f"[ERROR] Directory not found: {cwd}"
    if not p.is_dir():
        return f"[ERROR] Not a directory: {cwd}"

    # Detect project type
    is_python = (
        (p / "pyproject.toml").exists()
        or (p / "setup.py").exists()
        or (p / "setup.cfg").exists()
        or (p / "requirements.txt").exists()
    )
    is_node = (p / "package.json").exists()

    def _run(cmd: list[str]) -> tuple[bool, str]:
        """Run a command and return (success, output)."""
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60, cwd=cwd,
            )
            output = result.stdout.strip() or result.stderr.strip()
            return result.returncode == 0, output
        except FileNotFoundError:
            return False, f"{cmd[0]} not found"
        except subprocess.TimeoutExpired:
            return False, "timed out"
        except Exception as e:
            return False, str(e)

    results = []

    if is_python:
        # Try ruff first (fix + format in one tool)
        ok, output = _run(["ruff", "check", "--fix", "."])
        if "not found" in output.lower():
            # Fallback: try black for formatting
            ok2, output2 = _run(["black", "."])
            if "not found" in output2.lower():
                results.append(f"  {YELLOW}⚠{RESET} No fixer available — install ruff (`pip install ruff`) or black (`pip install black`)")
            else:
                if ok2:
                    if "reformatted" in output2:
                        results.append(f"  {GREEN}✓{RESET} black: {output2.splitlines()[0] if output2 else 'files reformatted'}")
                    else:
                        results.append(f"  {GREEN}✓{RESET} black: already formatted")
                else:
                    results.append(f"  {RED}✗{RESET} black: {output2[:200]}")
        else:
            if ok:
                if "fixed" in output.lower():
                    results.append(f"  {GREEN}✓{RESET} ruff fix: {output.splitlines()[0] if output else 'issues fixed'}")
                else:
                    results.append(f"  {GREEN}✓{RESET} ruff: no issues found")
            else:
                # ruff found unfixable issues — still report what it could fix
                lines = output.splitlines()
                summary = lines[-3:] if len(lines) > 3 else lines
                results.append(f"  {YELLOW}⚠{RESET} ruff: some issues cannot be auto-fixed")
                for line in summary[:5]:
                    results.append(f"      {line}")

        # Also run ruff format (safe auto-formatting)
        ok_fmt, output_fmt = _run(["ruff", "format", "."])
        if "not found" not in output_fmt.lower():
            if ok_fmt:
                if "reformatted" in output_fmt.lower():
                    results.append(f"  {GREEN}✓{RESET} ruff format: files reformatted")
                else:
                    results.append(f"  {GREEN}✓{RESET} ruff format: already formatted")

    elif is_node:
        # Try eslint --fix
        ok, output = _run(["npx", "eslint", "--fix", "."])
        if "not found" in output.lower() or "command" in output.lower():
            # Try project-local eslint
            ok, output = _run(["./node_modules/.bin/eslint", "--fix", "."])
            if "not found" in output.lower():
                results.append(f"  {YELLOW}⚠{RESET} No eslint found — install with `npm install eslint --save-dev`")
            else:
                if ok:
                    results.append(f"  {GREEN}✓{RESET} eslint: no issues remaining")
                else:
                    results.append(f"  {YELLOW}⚠{RESET} eslint: some issues cannot be auto-fixed")
                    for line in output.splitlines()[:5]:
                        results.append(f"      {line}")
        else:
            if ok:
                results.append(f"  {GREEN}✓{RESET} eslint: no issues remaining")
            else:
                lines = output.splitlines()
                summary = lines[:5]
                results.append(f"  {YELLOW}⚠{RESET} eslint: some issues cannot be auto-fixed")
                for line in summary:
                    results.append(f"      {line}")

    else:
        return f"{DIM}No recognized project type found — can't determine fix command{RESET}"

    header = f"{BOLD}Auto-fix{RESET} — {'Python' if is_python else 'Node.js'} project"
    return header + "\n" + "\n".join(results)


# ── /review command ─────────────────────────────────────────────────────

# Max diff size (chars) before truncation — prevents blowing up the prompt
_REVIEW_DIFF_LIMIT = 30000

# Review focus areas — included in every review prompt so the LLM checks systematically
_REVIEW_FOCUS = """\
- **Bugs**: Logic errors, off-by-one, null/None handling, edge cases
- **Security**: Injection, path traversal, secrets in code, unsafe deserialization
- **Performance**: Unnecessary loops, N+1 queries, memory leaks, redundant work
- **Style**: Naming, dead code, complexity, consistency with surrounding code
- **Testing**: Are changes testable? Missing test coverage for new paths?"""


def _review_prompt_from_diff(diff: str) -> str | None:
    """Build a review prompt from a unified diff string.

    Returns the prompt text, or None if the diff is empty.
    """
    if not diff.strip():
        return None

    # Truncate very large diffs to keep the prompt manageable
    if len(diff) > _REVIEW_DIFF_LIMIT:
        diff = diff[:_REVIEW_DIFF_LIMIT] + "\n... [diff truncated]"

    return f"""Please review the following code changes and provide constructive feedback.

Focus on these areas:
{_REVIEW_FOCUS}

If the changes look good, say so briefly. Don't fabricate issues.

```
{diff}
```"""


def _run_review(workdir: str | None = None, commit: bool = False, staged: bool = False) -> str:
    """Generate a code review prompt from git changes.

    By default, reviews unstaged + staged changes.
    With commit=True, reviews the diff of the last commit (HEAD~1..HEAD).
    With staged=True, reviews only staged changes (git diff --cached).

    Returns the review prompt (to be sent to the LLM), or an error/status message.
    """
    cwd = workdir or os.getcwd()

    # Check we're in a git repo
    check = _run_git("rev-parse", "--is-inside-work-tree", workdir=cwd)
    if check.returncode != 0:
        return "[Not a git repo]"

    if commit:
        # Review the last commit
        diff_result = _run_git("diff", "HEAD~1", "HEAD", workdir=cwd)
        if diff_result.returncode != 0:
            # Might be the first commit with no parent — diff against git's empty tree
            # The empty tree hash is a well-known constant in git
            EMPTY_TREE = "4b825dc642cb6eb9a060e54bf899d15363d7aa72"
            diff_result = _run_git("diff", EMPTY_TREE, "HEAD", workdir=cwd)
            if diff_result.returncode != 0:
                return f"[ERROR] Could not get commit diff: {diff_result.stderr[:200]}"
        prompt = _review_prompt_from_diff(diff_result.stdout)
        if prompt is None:
            return "[No changes in the last commit to review]"
        return prompt

    if staged:
        # Review only staged changes
        diff_cached_result = _run_git("diff", "--cached", workdir=cwd)
        if diff_cached_result.returncode != 0:
            return f"[ERROR] git diff --cached failed: {diff_cached_result.stderr[:200]}"
        prompt = _review_prompt_from_diff(diff_cached_result.stdout)
        if prompt is None:
            return "[No staged changes to review]"
        return prompt

    # Review working tree changes (unstaged + staged)
    diff_result = _run_git("diff", workdir=cwd)
    diff_cached_result = _run_git("diff", "--cached", workdir=cwd)

    if diff_result.returncode != 0 or diff_cached_result.returncode != 0:
        return f"[ERROR] git diff failed: {diff_result.stderr[:200]}"

    combined = ""
    if diff_result.stdout.strip():
        combined += diff_result.stdout.strip()
    if diff_cached_result.stdout.strip():
        if combined:
            combined += "\n\n"
        combined += diff_cached_result.stdout.strip()

    prompt = _review_prompt_from_diff(combined)
    if prompt is None:
        return "[No changes to review — working tree clean]"

    return prompt


# ── /log command ────────────────────────────────────────────────────────

def _format_history(
    messages: list[dict],
    show_tokens: bool = False,
    last: int | None = None,
    exchange: bool = False,
) -> str:
    """Format conversation history as a readable summary.

    Shows each message's role, a content preview (truncated), and tool call
    names if present. Useful for understanding what the agent has been doing.

    Args:
        messages: The conversation messages list.
        show_tokens: If True, show estimated token count per message.
        last: If set, only show the last N non-system messages (plus system
              prompt always). Useful for long conversations.
        exchange: If True, hide tool role messages — shows only system, user,
              and assistant messages for a cleaner conversation flow.

    Returns a formatted string.
    """
    if not messages:
        return "No messages in conversation."

    # Separate system from rest for filtering
    system_msgs = []
    rest = list(messages)
    if rest and rest[0].get("role") == "system":
        system_msgs = [rest.pop(0)]

    # Filter: hide tool messages if exchange=True
    if exchange:
        rest = [m for m in rest if m.get("role") != "tool"]

    # Filter: keep only last N non-system messages
    total_non_system = len(rest)
    if last is not None and last < total_non_system:
        if last <= 0:
            rest = []
        else:
            rest = rest[-last:]

    # Reassemble
    display = system_msgs + rest

    lines = [f"{BOLD}Conversation History{RESET} ({len(display)} messages" +
             (f", showing last {last}" if last is not None and last < total_non_system else "") +
             (", exchanges only" if exchange else "") +
             ")"]

    for i, msg in enumerate(display):
        role = msg.get("role", "unknown")
        content = msg.get("content")
        tool_calls = msg.get("tool_calls")

        # Token estimation for this message
        token_str = ""
        if show_tokens:
            from .agent import Agent
            tok = Agent._estimate_tokens([msg])
            token_str = f" {DIM}~{tok}t{RESET}"

        # Role icon
        role_icons = {
            "system": "⚙",
            "user": "👤",
            "assistant": "🤖",
            "tool": "🔧",
        }
        icon = role_icons.get(role, "•")

        if role == "system":
            # System messages are long — just show a label
            preview = "system prompt"
        elif role == "tool":
            tool_call_id = msg.get("tool_call_id", "?")
            preview = (content or "")[:80]
            if len((content or "")) > 80:
                preview += "..."
            lines.append(f"  {icon} {DIM}tool [{tool_call_id}]{RESET}{token_str} {preview}")
            continue
        elif tool_calls:
            # Assistant with tool calls — show which tools
            tool_names = [tc["function"].get("name", "?") for tc in tool_calls if isinstance(tc.get("function"), dict)]
            tools_str = ", ".join(tool_names)
            text_preview = ""
            if content:
                text_preview = f": {(content)[:60]}"
            lines.append(f"  {icon} {CYAN}assistant{RESET} → {YELLOW}{tools_str}{RESET}{token_str}{text_preview}")
            continue
        else:
            # Regular user or assistant message
            preview = (content or "")[:100]
            if len((content or "")) > 100:
                preview += "..."

        role_color = CYAN if role == "user" else (GREEN if role == "assistant" else DIM)
        lines.append(f"  {icon} {role_color}{role}{RESET}{token_str} {preview}")

    # Show total token estimate if requested
    if show_tokens:
        from .agent import Agent
        total_tokens = Agent._estimate_tokens(messages)
        lines.append(f"\n  {DIM}Total estimated tokens: ~{total_tokens}{RESET}")

    return "\n".join(lines)


def _run_git_log(workdir: str | None = None, count: int = 10, oneline: bool = False) -> str:
    """Show recent git commit log.

    Args:
        workdir: Working directory (defaults to cwd).
        count: Number of commits to show (default 10).
        oneline: If True, show compact one-line-per-commit format.

    Returns a formatted commit log or error message.
    """
    cwd = workdir or os.getcwd()

    # Check we're in a git repo
    check = _run_git("rev-parse", "--is-inside-work-tree", workdir=cwd)
    if check.returncode != 0:
        return "[Not a git repo]"

    if oneline:
        # Compact format: short hash + subject only
        log_format = "%h %s"
        log_result = _run_git("log", f"-{count}", f"--format={log_format}", workdir=cwd)
    else:
        # Default format: short hash | subject | author name | relative date
        log_format = "%h|%s|%an|%cr"
        log_result = _run_git("log", f"-{count}", f"--format={log_format}", workdir=cwd)

    if log_result.returncode != 0:
        return f"[ERROR] git log failed: {log_result.stderr[:200]}"

    output = log_result.stdout.strip()
    if not output:
        return "[No commits yet]"

    # Parse and format nicely
    lines = []
    if oneline:
        for entry in output.splitlines():
            lines.append(f"  {YELLOW}{entry}{RESET}")
    else:
        for entry in output.splitlines():
            parts = entry.split("|", 3)
            if len(parts) == 4:
                short_hash, subject, author, date = parts
                lines.append(f"  {YELLOW}{short_hash}{RESET} {subject} {DIM}({author}, {date}){RESET}")
            else:
                lines.append(f"  {entry}")

    header = f"{BOLD}Recent Commits{RESET} (last {count})"
    return header + "\n" + "\n".join(lines)


# ── /cost command + context budget ──────────────────────────────────────

# Pricing per million tokens (approximate, as of 2025-2026).
# These are estimates and may not reflect current pricing.
_MODEL_PRICING: dict[str, dict[str, float]] = {
    # GLM models (Zhipu AI) — pricing in USD per million tokens
    "glm-5": {"input": 0.50, "output": 2.00},
    "glm-5.1": {"input": 0.50, "output": 2.00},
    "glm-4-plus": {"input": 0.70, "output": 3.00},
    "glm-4": {"input": 0.40, "output": 1.50},
    "glm-4-flash": {"input": 0.05, "output": 0.20},
    # OpenAI models (GPT-4.x, 2025)
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    # OpenAI models (o-series reasoning, 2025)
    "o1": {"input": 15.00, "output": 60.00},
    "o1-mini": {"input": 3.00, "output": 12.00},
    "o3": {"input": 10.00, "output": 40.00},
    "o3-mini": {"input": 1.10, "output": 4.40},
    "o4-mini": {"input": 1.10, "output": 4.40},
    # Anthropic models (Claude, 2025)
    "claude-opus-4": {"input": 15.00, "output": 75.00},
    "claude-sonnet-4": {"input": 3.00, "output": 15.00},
    "claude-3-7-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-opus": {"input": 15.00, "output": 75.00},
    "claude-3-haiku": {"input": 0.25, "output": 1.25},
    # Google models (Gemini, 2025)
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    # DeepSeek models
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    "deepseek-v3": {"input": 0.14, "output": 0.28},
    "deepseek-r1": {"input": 0.55, "output": 2.19},
    # Moonshot models
    "moonshot-v1-8k": {"input": 0.50, "output": 0.50},
    "moonshot-v1-32k": {"input": 1.00, "output": 1.00},
    "moonshot-v1-128k": {"input": 3.00, "output": 3.00},
}


def _find_model_pricing(model: str) -> dict[str, float] | None:
    """Find pricing for a model, handling version suffixes.

    E.g. 'glm-5.1-plus' should match 'glm-5.1' if no exact match.
    """
    # Exact match first
    if model in _MODEL_PRICING:
        return _MODEL_PRICING[model]

    # Try prefix matching: 'gpt-4o-2024-05-13' → 'gpt-4o'
    for prefix in sorted(_MODEL_PRICING.keys(), key=len, reverse=True):
        if model.startswith(prefix):
            return _MODEL_PRICING[prefix]

    return None


def _estimate_cost(usage: Usage, model: str) -> str:
    """Estimate API cost from token usage data.

    Args:
        usage: Token usage data.
        model: The model name.

    Returns a formatted string with cost breakdown.
    """
    pricing = _find_model_pricing(model)

    if pricing is None:
        return (
            f"{BOLD}Cost Estimate{RESET}\n"
            f"  Model: {model} (unknown pricing)\n"
            f"  Input:  {usage.input_tokens:,} tokens\n"
            f"  Output: {usage.output_tokens:,} tokens\n"
            f"  {DIM}Set pricing in _MODEL_PRICING to get cost estimates.{RESET}"
        )

    input_cost = (usage.input_tokens / 1_000_000) * pricing["input"]
    output_cost = (usage.output_tokens / 1_000_000) * pricing["output"]
    total_cost = input_cost + output_cost

    return (
        f"{BOLD}Cost Estimate{RESET} — {model}\n"
        f"  Input:  {usage.input_tokens:>10,} tokens  (${input_cost:.4f})\n"
        f"  Output: {usage.output_tokens:>10,} tokens  (${output_cost:.4f})\n"
        f"  {BOLD}Total:  ${(total_cost):.4f}{RESET}"
    )


# ── Context window budget ──────────────────────────────────────────────

from .provider import get_model_context_window, MODEL_CONTEXT_WINDOWS, DEFAULT_CONTEXT_WINDOW

# Backward-compatible aliases for internal repl.py code that used the old private names
_MODEL_CONTEXT_WINDOWS = MODEL_CONTEXT_WINDOWS
_DEFAULT_CONTEXT_WINDOW = DEFAULT_CONTEXT_WINDOW
_get_model_context_window = get_model_context_window


def _format_context_budget(used_tokens: int, context_window: int) -> str:
    """Format a context budget display showing usage percentage.

    Shows a warning when usage exceeds 80% of the context window.
    This helps users know when to /compact or start a new session.

    Args:
        used_tokens: Estimated tokens in the current context.
        context_window: Model's total context window size.

    Returns a formatted string like "50,000 / 128,000 (39%)".
    """
    pct = int(used_tokens / context_window * 100) if context_window > 0 else 0
    used_str = f"{used_tokens:,}"
    window_str = f"{context_window:,}"

    if pct >= 80:
        return f"{RED}{used_str} / {window_str} ({pct}%) ⚠ high{RESET}"
    elif pct >= 60:
        return f"{YELLOW}{used_str} / {window_str} ({pct}%){RESET}"
    else:
        return f"{used_str} / {window_str} ({pct}%)"


# ── /env command ──────────────────────────────────────────────────────

def _mask_api_key(key: str) -> str:
    """Mask an API key, showing only the first 4 characters.

    Returns '***' for very short keys and '(not set)' for empty keys.
    This prevents accidental exposure of secrets in terminal output.
    """
    if not key:
        return "(not set)"
    if len(key) <= 4:
        return "***"
    return key[:4] + "*" * (len(key) - 4)


def _show_env_info(
    model: str,
    base_url: str,
    provider: str | None,
    api_key: str = "",
    max_tokens: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> str:
    """Show current provider configuration for debugging.

    Masks the API key to prevent accidental exposure while still
    letting the user verify they're using the right key.

    Args:
        model: Current model name.
        base_url: API base URL.
        provider: Provider preset name (None for custom).
        api_key: API key (will be masked in output).
        max_tokens: Max output tokens (None = API default).
        temperature: Sampling temperature (None = API default).
        top_p: Nucleus sampling threshold (None = API default).

    Returns a formatted string with config details.
    """
    provider_label = provider if provider else "custom"
    if provider_label == "failover":
        provider_label = "failover (multi-provider)"
    masked_key = _mask_api_key(api_key)

    lines = [
        f"{BOLD}Provider Config{RESET}",
        f"  Provider: {provider_label}",
        f"  Model:    {model}",
        f"  Base URL: {base_url}",
        f"  API Key:  {masked_key}",
    ]

    # Show generation params if explicitly set
    if max_tokens is not None:
        lines.append(f"  Max Tokens: {max_tokens}")
    if temperature is not None:
        lines.append(f"  Temperature: {temperature}")
    if top_p is not None:
        lines.append(f"  Top P: {top_p}")

    return "\n".join(lines)


# ── Custom slash commands from .yoyo/commands/ ─────────────────────────

def _load_custom_commands(workdir: str | None = None) -> dict[str, dict[str, str]]:
    """Load custom command definitions from .yoyo/commands/*.md files.

    Each .md file defines a command. The filename (minus .md) is the command name.
    Files can have YAML frontmatter with 'name' and 'description' fields.
    The remaining content is the prompt template, optionally with {{args}} placeholder.

    Returns:
        Dict mapping command_name -> {"prompt": str, "description": str}
    """
    cwd = workdir or os.getcwd()
    cmd_dir = Path(cwd) / ".yoyo" / "commands"

    if not cmd_dir.is_dir():
        return {}

    commands: dict[str, dict[str, str]] = {}
    for md_file in sorted(cmd_dir.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        name = md_file.stem
        description = ""
        content = text.strip()

        # Parse YAML frontmatter
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
        if fm_match:
            frontmatter = fm_match.group(1)
            content = fm_match.group(2).strip()

            for line in frontmatter.splitlines():
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("description:"):
                    description = line.split(":", 1)[1].strip()

        commands[name] = {
            "prompt": content,
            "description": description,
        }

    return commands


def _resolve_custom_command(
    command_name: str,
    workdir: str | None = None,
    args: str = "",
) -> str | None:
    """Resolve a custom command to its prompt text.

    If the command has a {{args}} placeholder, substitute it.
    If no placeholder but args are provided, append them to the prompt.

    Args:
        command_name: The slash command name (without /).
        workdir: Working directory to search for .yoyo/commands/.
        args: Additional arguments from the user input.

    Returns:
        The resolved prompt text, or None if command not found.
    """
    commands = _load_custom_commands(workdir)

    if command_name not in commands:
        return None

    prompt = commands[command_name]["prompt"]

    if "{{args}}" in prompt:
        prompt = prompt.replace("{{args}}", args)
    elif args:
        # When no placeholder, just append args — this is more useful
        # than silently dropping them, as the user explicitly typed something
        prompt = f"{prompt}\n\n{args}"

    return prompt




# ── /pr command ────────────────────────────────────────────────────────

# Max diff size for PR description — prevents blowing up the prompt
_PR_DIFF_LIMIT = 30000


def _run_pr_description(workdir: str | None = None) -> str:
    """Generate a PR description from git changes.

    Collects diff (staged + unstaged), branch name, recent commit log,
    and builds a structured PR description prompt for the agent to refine.

    Returns the PR description prompt, or an error/status message.
    """
    cwd = workdir or os.getcwd()

    # Check we're in a git repo
    check = _run_git("rev-parse", "--is-inside-work-tree", workdir=cwd)
    if check.returncode != 0:
        return "[Not a git repo]"

    # Get unstaged + staged diffs
    diff_result = _run_git("diff", workdir=cwd)
    diff_cached_result = _run_git("diff", "--cached", workdir=cwd)

    if diff_result.returncode != 0 or diff_cached_result.returncode != 0:
        return f"[ERROR] git diff failed"

    combined = ""
    if diff_result.stdout.strip():
        combined += diff_result.stdout.strip()
    if diff_cached_result.stdout.strip():
        if combined:
            combined += "\n\n"
        combined += diff_cached_result.stdout.strip()

    if not combined:
        return "[No changes to describe — working tree clean]"

    # Truncate large diffs
    if len(combined) > _PR_DIFF_LIMIT:
        combined = combined[:_PR_DIFF_LIMIT] + "\n... [diff truncated]"

    # Get current branch name
    branch_result = _run_git("branch", "--show-current", workdir=cwd)
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"

    # Get number of commits ahead of main/master
    for base_branch in ("main", "master"):
        count_result = _run_git("rev-list", "--count", f"{base_branch}..HEAD", workdir=cwd)
        if count_result.returncode == 0:
            commit_count = int(count_result.stdout.strip())
            break
    else:
        commit_count = 0

    # Get recent commit messages (for PR summary)
    log_count = max(commit_count, 10)
    log_result = _run_git("log", f"-{log_count}", "--format=%s", workdir=cwd)
    commit_messages = log_result.stdout.strip() if log_result.returncode == 0 else ""

    # Build diff stat for quick overview
    stat_result = _run_git("diff", "--stat", workdir=cwd)
    stat = stat_result.stdout.strip() if stat_result.returncode == 0 else ""

    # Build the PR description prompt
    parts = [
        "Generate a clear, concise PR description for the following changes.",
        "",
        f"**Branch:** `{branch}`",
    ]

    if commit_count:
        parts.append(f"**Commits in this branch:** {commit_count}")

    if commit_messages:
        parts.append(f"\n**Recent commit messages:**")
        for line in commit_messages.splitlines()[:10]:
            parts.append(f"  - {line}")

    if stat:
        parts.append(f"\n**Files changed:**")
        parts.append(f"```\n{stat}\n```")

    parts.append(f"\n**Full diff:**")
    parts.append(f"```\n{combined}\n```")

    parts.append("\nPlease generate a PR description with:")
    parts.append("1. A clear **title** (under 72 chars)")
    parts.append("2. A **summary** of what this PR does and why")
    parts.append("3. **Changes** — bullet list of key changes")
    parts.append("4. **Testing** — how the changes were tested (or should be)")

    return "\n".join(parts)


def _handle_config_command(
    args_str: str,
    temperature: float | None,
    max_tokens: int | None,
    top_p: float | None,
    model: str,
) -> tuple[str, dict[str, Any]]:
    """Handle the /config command — view or set generation parameters.

    Args:
        args_str: The arguments after /config (empty = show all, "key value" = set).
        temperature: Current temperature setting.
        max_tokens: Current max_tokens setting.
        top_p: Current top_p setting.
        model: Current model name.

    Returns:
        Tuple of (output_string, updates_dict).
        updates_dict contains only the params that were changed.
    """
    updates: dict[str, Any] = {}

    if not args_str.strip():
        # Show current config
        def _fmt_val(val, default_label="API default"):
            return str(val) if val is not None else f"{DIM}{default_label}{RESET}"

        lines = [
            f"{BOLD}Generation Config{RESET} — {model}",
            f"  temperature: {_fmt_val(temperature)}",
            f"  max_tokens:  {_fmt_val(max_tokens)}",
            f"  top_p:       {_fmt_val(top_p)}",
            "",
            f"  {DIM}Set with: /config <param> <value>{RESET}",
            f"  {DIM}Params: temperature (0.0-2.0), max_tokens (int), top_p (0.0-1.0){RESET}",
        ]
        return "\n".join(lines), updates

    # Handle /config reset — restore all params to API defaults
    if args_str.strip() == "reset":
        updates = {"temperature": None, "max_tokens": None, "top_p": None}
        return f"{GREEN}[OK] Generation params reset to API defaults{RESET}", updates

    # Parse "key value" format
    parts = args_str.strip().split(maxsplit=1)
    if len(parts) != 2:
        return f"{YELLOW}Usage: /config <param> <value> — or /config to view current settings{RESET}", updates

    key, val_str = parts
    valid_params = {"temperature", "max_tokens", "top_p"}
    if key not in valid_params:
        return (
            f"{YELLOW}Unknown parameter: {key}{RESET}\n"
            f"  Valid parameters: {', '.join(sorted(valid_params))}"
        ), updates

    try:
        if key == "max_tokens":
            value = int(val_str)
            if value < 1:
                return f"{RED}max_tokens must be a positive integer{RESET}", updates
        else:
            value = float(val_str)
            if key == "temperature" and not (0.0 <= value <= 2.0):
                return f"{RED}temperature must be between 0.0 and 2.0{RESET}", updates
            if key == "top_p" and not (0.0 <= value <= 1.0):
                return f"{RED}top_p must be between 0.0 and 1.0{RESET}", updates
    except ValueError:
        return f"{RED}Invalid value: {val_str!r} — expected a number{RESET}", updates

    updates[key] = value
    return f"{GREEN}[OK] {key} set to {value}{RESET}", updates


def _export_to_file(
    filepath: str,
    messages: list[dict],
    model: str,
    include_system: bool = False,
) -> str:
    """Export conversation as markdown to a file.

    Args:
        filepath: Path to write the markdown file.
        messages: Conversation messages.
        model: Current model name.
        include_system: Whether to include system prompt.

    Returns a confirmation or error message.
    """
    try:
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        content = _export_conversation_markdown(
            messages, model=model, include_system=include_system,
        )
        p.write_text(content, encoding="utf-8")
        return f"{GREEN}[OK] Conversation exported to {filepath}{RESET}"
    except Exception as e:
        return f"{RED}[ERROR] Failed to export: {e}{RESET}"


def _export_conversation_markdown(
    messages: list[dict],
    model: str = "unknown",
    include_system: bool = False,
) -> str:
    """Export conversation as markdown.

    Generates a human-readable markdown document from the conversation history.
    System prompts are excluded by default (they're internal, not user content).
    Tool outputs are truncated to 500 chars to keep the export readable.

    Args:
        messages: The conversation messages list.
        model: Current model name for the header.
        include_system: Whether to include the system prompt.

    Returns a markdown string.
    """
    from datetime import datetime

    lines = [
        f"# Conversation Export",
        f"",
        f"**Model:** {model}",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Messages:** {len(messages)}",
        f"",
        "---",
        "",
    ]

    # Max chars for tool output in export — keeps the file readable
    MAX_TOOL_OUTPUT = 500

    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls")

        # Skip system messages unless explicitly requested
        if role == "system" and not include_system:
            continue

        if role == "system":
            lines.append(f"## System Prompt\n\n{content}\n")
        elif role == "user":
            # Skip compact summaries — they're synthetic
            if content.startswith("[Summary of previous conversation]"):
                lines.append(f"## Context Summary\n\n*(compacted conversation summary)*\n")
                continue
            lines.append(f"## User\n\n{content}\n")
        elif role == "assistant":
            # Skip compact summaries — they're synthetic, not real assistant output
            if content and content.startswith("[Summary of previous conversation]"):
                lines.append(f"## Context Summary\n\n*(compacted conversation summary)*\n")
                continue
            if tool_calls:
                tool_names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
                args = []
                for tc in tool_calls:
                    func = tc.get("function", {})
                    name = func.get("name", "?")
                    arg_str = func.get("arguments", "{}")
                    # Try to pretty-print JSON args
                    try:
                        import json as _json
                        parsed = _json.loads(arg_str)
                        # Truncate long values
                        short = {}
                        for k, v in parsed.items():
                            s = str(v)
                            short[k] = s[:100] + "..." if len(s) > 100 else s
                        args.append(f"{name}({_json.dumps(short)})")
                    except (json.JSONDecodeError, Exception):
                        args.append(f"{name}(...)")
                lines.append(f"## Assistant → {', '.join(tool_names)}\n")
                for arg in args:
                    lines.append(f"- `{arg}`")
                if content:
                    lines.append(f"\n{content}")
                lines.append("")
            else:
                lines.append(f"## Assistant\n\n{content}\n")
        elif role == "tool":
            # Truncate long tool output
            display = content
            if len(display) > MAX_TOOL_OUTPUT:
                display = display[:MAX_TOOL_OUTPUT] + f"\n... [truncated, {len(content)} chars total]"
            lines.append(f"### Tool Output\n\n```\n{display}\n```\n")
        else:
            lines.append(f"## {role.title()}\n\n{content}\n")

    return "\n".join(lines)


def _format_status_output(
    model: str,
    cwd: str,
    messages: list[dict],
    usage: Any,
    skills_count: int,
    context_tokens: int = 0,
    reasoning_effort: str | None = None,
) -> str:
    """Format session status information.

    Shows model, working directory, message count, token usage, estimated
    context size, and loaded skills count. Context tokens help users
    understand how close they are to the model's context window limit.

    Args:
        model: Current model name.
        cwd: Current working directory.
        messages: Conversation messages list.
        usage: Token usage data.
        skills_count: Number of loaded skills.
        context_tokens: Estimated context token count.

    Returns a formatted string.
    """
    msg_count = len(messages)
    msg_label = "message" if msg_count == 1 else "messages"

    # Show context budget with model's window limit
    context_window = _get_model_context_window(model)
    budget_str = _format_context_budget(context_tokens, context_window)

    lines = [
        f"{BOLD}Session Status{RESET}",
        f"  model:    {model}",
        f"  cwd:      {cwd}",
        f"  messages: {msg_count} {msg_label}",
        f"  tokens:   {usage} (API)",
        f"  context:  {budget_str}",
        f"  skills:   {skills_count}",
    ]
    if reasoning_effort:
        lines.append(f"  thinking: {reasoning_effort}")

    # Add git branch + dirty status if in a git repo
    git_info = _git_status_line()
    if git_info:
        lines.append(f"  git:      {git_info}")

    return "\n".join(lines)


def _format_providers_list(
    active_model: str | None = None,
    active_provider: str | None = None,
) -> str:
    """Format available provider presets for display.

    Args:
        active_model: Currently active model name, shown as highlight if matching.
        active_provider: Currently active provider preset name (takes priority).

    Returns a formatted string listing all presets.
    """
    from .provider import PROVIDER_PRESETS

    lines = [f"{BOLD}Available Provider Presets{RESET}"]
    for name, config in sorted(PROVIDER_PRESETS.items()):
        marker = ""
        # Match by provider name first (exact), then by model (fuzzy)
        if active_provider and name == active_provider:
            marker = f" {GREEN}(active){RESET}"
        elif not active_provider and active_model and config["default_model"] == active_model:
            marker = f" {GREEN}(active){RESET}"
        lines.append(
            f"  {CYAN}{name:12}{RESET} env: {config['env_key']:20} model: {config['default_model']}{marker}"
        )
    lines.append("")
    lines.append(f"  {DIM}Switch with: /provider <name> or /model <model-name>{RESET}")
    return "\n".join(lines)


def _copy_to_clipboard(text: str) -> bool:
    """Copy text to the system clipboard. Returns True on success.

    Uses platform-native clipboard tools:
    - macOS: pbcopy
    - Linux: xclip or xsel
    - Windows: clip
    """
    try:
        if sys.platform == "darwin":
            proc = subprocess.run(["pbcopy"], input=text, text=True, timeout=5)
            return proc.returncode == 0
        elif sys.platform == "linux":
            for cmd in [
                ["xclip", "-selection", "clipboard"],
                ["xclip"],
                ["xsel", "--clipboard"],
            ]:
                try:
                    proc = subprocess.run(cmd, input=text, text=True, timeout=5)
                    if proc.returncode == 0:
                        return True
                except FileNotFoundError:
                    continue
            return False
        elif sys.platform == "win32":
            proc = subprocess.run(["clip"], input=text, text=True, timeout=5)
            return proc.returncode == 0
        return False
    except (subprocess.TimeoutExpired, OSError):
        return False


def _strip_interrupted_marker(content: str) -> str:
    """Remove the trailing [interrupted] marker from a partial assistant response.

    When the user copies or views an interrupted response, the [interrupted] marker
    is noise — it was added by the agent to tag the message, not part of the actual
    LLM output.
    """
    if content.endswith("\n[interrupted]"):
        return content[:-len("\n[interrupted]")].rstrip()
    if content.strip() == "[interrupted]":
        return ""
    return content


def _search_conversation(
    messages: list[dict],
    keyword: str,
    case_sensitive: bool = False,
) -> str:
    """Search conversation history for a keyword and return matching messages.

    Shows each matching message with its role, position index, and a content
    preview with the keyword highlighted.

    Args:
        messages: The conversation messages list.
        keyword: The search term to look for.
        case_sensitive: If True, match case exactly.

    Returns a formatted string with search results.
    """
    if not messages:
        return "No messages in conversation."

    if not keyword.strip():
        return f"{YELLOW}Usage: /search <keyword> [--case]{RESET}"

    flags = 0 if case_sensitive else re.IGNORECASE

    # Role icons
    role_icons = {
        "system": "⚙",
        "user": "👤",
        "assistant": "🤖",
        "tool": "🔧",
    }

    # Validate regex first — fall back to literal search if invalid
    try:
        re.compile(keyword)
        use_regex = True
    except re.error:
        # Treat keyword as literal string, escape special chars
        keyword_safe = re.escape(keyword)
        use_regex = False

    matches = []
    for i, msg in enumerate(messages):
        role = msg.get("role", "unknown")
        content = msg.get("content") or ""

        pattern = keyword_safe if not use_regex else keyword
        if not re.search(pattern, content, flags):
            continue

        icon = role_icons.get(role, "•")
        # Find the match position and show context around it
        match = re.search(pattern, content, flags)
        if match:
            start = max(0, match.start() - 30)
            end = min(len(content), match.end() + 50)
            preview = content[start:end]
            if start > 0:
                preview = "..." + preview
            if end < len(content):
                preview = preview + "..."

            role_color = CYAN if role == "user" else (GREEN if role == "assistant" else DIM)
            matches.append(f"  {icon} {role_color}{role}#{i}{RESET} {DIM}{preview}{RESET}")

    if not matches:
        return f"{DIM}No matches found for '{keyword}'{RESET}"

    header = f"{BOLD}Search Results{RESET} ({len(matches)} match{'es' if len(matches) != 1 else ''} for '{keyword}')"
    return header + "\n" + "\n".join(matches)


def _run_grep(args: str) -> str:
    """Quick file content search — like grep but as a slash command.

    Usage: /grep <pattern> [--case] [--glob <pattern>] [-C N | --context N]

    Searches file contents recursively from the current working directory.
    Supports regex patterns (falls back to literal if invalid regex).
    Skips common ignored directories (.git, __pycache__, node_modules, etc.).

    Args:
        args: The search arguments — pattern and optional flags.

    Returns:
        Formatted search results with file paths and line numbers.
    """
    if not args.strip():
        return f"{YELLOW}Usage: /grep <pattern> [--case] [--glob <pattern>] [-C N]{RESET}"

    # Parse flags
    parts = args.split()
    case_sensitive = "--case" in parts
    context_lines = 0
    glob_filter = None

    # Parse -C N / --context N
    for flag in ("-C", "--context"):
        if flag in parts:
            idx = parts.index(flag)
            if idx + 1 < len(parts):
                try:
                    context_lines = int(parts[idx + 1])
                    parts = parts[:idx] + parts[idx + 2:]
                    break
                except ValueError:
                    pass

    if "--glob" in parts:
        glob_idx = parts.index("--glob")
        if glob_idx + 1 < len(parts):
            glob_filter = parts[glob_idx + 1]
            # Remove --glob and its value from parts
            parts = parts[:glob_idx] + parts[glob_idx + 2:]

    # Remove flags from parts to get the pattern
    keywords = [p for p in parts if p not in ("--case", "--glob")]
    if not keywords:
        return f"{YELLOW}Usage: /grep <pattern> [--case] [--glob <pattern>] [-C N]{RESET}"

    pattern = " ".join(keywords)

    # Validate regex — fall back to literal search if invalid
    try:
        re.compile(pattern)
        use_regex = True
    except re.error:
        pattern = re.escape(pattern)
        use_regex = False

    flags = 0 if case_sensitive else re.IGNORECASE

    # Directories to skip
    skip_dirs = {
        ".git", "__pycache__", "node_modules", ".venv", ".pytest_cache",
        ".mypy_cache", ".tox", "dist", "build", ".eggs", ".next", "target",
        "vendor", ".hg", ".svn",
    }

    # Binary check — files with null bytes
    def _is_binary_file(path: Path) -> bool:
        try:
            chunk = path.read_bytes()[:8192]
            return b"\x00" in chunk
        except Exception:
            return True

    results = []
    cwd = Path(os.getcwd())
    max_results = 50

    for root, dirs, files in os.walk(cwd):
        # Skip ignored directories
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]

        for fname in sorted(files):
            if len(results) >= max_results:
                break

            fpath = Path(root) / fname

            # Apply glob filter
            if glob_filter:
                import fnmatch
                if not fnmatch.fnmatch(fname, glob_filter):
                    continue

            # Skip binary files
            if _is_binary_file(fpath):
                continue

            try:
                lines = fpath.read_text(errors="replace").splitlines()
            except Exception:
                continue

            rel_path = fpath.relative_to(cwd)
            for line_num, line in enumerate(lines, 1):
                if len(results) >= max_results:
                    break
                if re.search(pattern, line, flags):
                    # Truncate long lines
                    display_line = line.strip()
                    if len(display_line) > 120:
                        display_line = display_line[:117] + "..."
                    results.append(f"{DIM}{rel_path}{RESET}:{GREEN}{line_num}{RESET}:{display_line}")

                    # Show context lines around the match
                    if context_lines > 0:
                        for offset in range(-context_lines, context_lines + 1):
                            if offset == 0:
                                continue  # Already added the match line
                            ctx_num = line_num + offset
                            if 1 <= ctx_num <= len(lines):
                                ctx_line = lines[ctx_num - 1].strip()
                                if len(ctx_line) > 120:
                                    ctx_line = ctx_line[:117] + "..."
                                results.append(f"{DIM}  {rel_path}:{ctx_num}:  {ctx_line}{RESET}")

    if not results:
        return f"{DIM}No matches found for '{pattern}'{RESET}"

    truncated = ""
    if len(results) >= max_results:
        truncated = f"\n{DIM}  ... (truncated at {max_results} results){RESET}"

    header = f"{BOLD}Grep Results{RESET} ({len(results)} match{'es' if len(results) != 1 else ''} for '{pattern}')"
    return header + "\n" + "\n".join(results) + truncated


def _find_last_user_message(messages: list[dict]) -> str | None:
    """Find the last real user message (not a compact summary) in the conversation.

    Used by /redo to re-send the last prompt. Skips compact summary messages
    (identified by starting with '[Summary of previous conversation]') because
    those are synthetic and not something the user typed.

    Args:
        messages: The conversation message list.

    Returns:
        The content of the last user message, or None if no real user message exists.
    """
    # Walk backwards through messages to find the last real user message
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if not content:
            continue
        # Skip compact summary messages — they're synthetic, not user input
        if content.startswith("[Summary of previous conversation]"):
            continue
        return content
    return None


def _handle_append_command(text: str, messages: list[dict]) -> str:
    """Inject a user message into the conversation without triggering agent response.

    Useful for adding context (error messages, notes, file contents) to the
    conversation before asking a question. The agent will see this message
    in its context on the next turn but won't respond immediately.

    Args:
        text: The text to append as a user message.
        messages: The conversation message list (modified in place).

    Returns:
        Confirmation or usage message.
    """
    if not text.strip():
        return f"{YELLOW}Usage: /append <text>{RESET}\n{DIM}  Adds context to conversation without triggering a response.{RESET}"

    messages.append({
        "role": "user",
        "content": text.strip(),
    })
    return f"{GREEN}  ✓ Appended to conversation ({len(text)} chars){RESET}"


def _handle_revert_command(messages: list[dict], count: int = 1) -> tuple[list[dict], int] | str:
    """Remove the last N conversation exchanges from message history.

    An "exchange" is a user message followed by the assistant's response(s),
    including any tool call chains (assistant → tool → assistant → ...).

    Always preserves the system prompt (index 0). If count exceeds available
    exchanges, removes all non-system messages.

    Args:
        messages: The conversation message list.
        count: Number of exchanges to revert (default 1).

    Returns:
        Tuple of (new_messages, removed_count) on success,
        or a string message if nothing to revert.
    """
    if count < 1:
        return "Reverted 0 exchanges"

    # Only consider non-system messages
    real_msgs = [m for m in messages if m.get("role") != "system"]
    if not real_msgs:
        return "No conversation to revert"

    # Walk backwards to identify exchange boundaries.
    # An exchange starts with a user message and includes everything after it
    # until the next user message (or end of conversation).
    # We identify exchanges by finding user messages from the end.
    exchanges_found = 0
    cut_index = len(messages)  # Where to cut (keep messages[:cut_index])

    for i in range(len(messages) - 1, -1, -1):
        role = messages[i].get("role")
        if role == "system":
            break
        if role == "user":
            exchanges_found += 1
            cut_index = i
            if exchanges_found >= count:
                break

    if exchanges_found == 0:
        return "No conversation to revert"

    removed = len(messages) - cut_index
    new_messages = messages[:cut_index]
    return (new_messages, removed)


def _find_last_assistant_response(messages: list[dict]) -> str | None:
    """Find the last meaningful assistant text response in the conversation.

    Skips:
    - Error markers ([error: ...])
    - Interrupted messages ([interrupted])
    - Compact summaries
    - Tool-call-only messages with no text content

    Args:
        messages: The conversation message list.

    Returns:
        The content of the last real assistant response, or None.
    """
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if not content:
            continue
        # Skip error messages
        if content.startswith("[error:"):
            continue
        # Skip interrupted messages that have no real content before the marker
        if content.strip() == "[interrupted]":
            continue
        # Skip compact summaries
        if content.startswith("[Summary of previous conversation]"):
            continue
        return content
    return None


# Max chars to show in /system display — prevents flooding the terminal
_SYSTEM_DISPLAY_LIMIT = 3000


def _format_system_prompt_display(messages: list[dict]) -> str:
    """Format the current system prompt for display.

    Shows the full system prompt with line count. Truncates very long
    prompts to avoid flooding the terminal. Returns a message if no
    system prompt is set.

    Args:
        messages: The conversation message list.

    Returns a formatted string showing the system prompt.
    """
    # Find the system message
    system_content = None
    for msg in messages:
        if msg.get("role") == "system":
            system_content = msg.get("content", "")
            break

    if system_content is None:
        return f"{DIM}No system prompt set{RESET}"

    line_count = system_content.count("\n") + 1
    char_count = len(system_content)

    lines = [
        f"{BOLD}System Prompt{RESET} ({line_count} lines, {char_count:,} chars)",
        "",
    ]

    if char_count > _SYSTEM_DISPLAY_LIMIT:
        truncated = system_content[:_SYSTEM_DISPLAY_LIMIT]
        lines.append(truncated)
        lines.append("")
        remaining = char_count - _SYSTEM_DISPLAY_LIMIT
        lines.append(f"{DIM}... ({remaining:,} more chars truncated){RESET}")
    else:
        lines.append(system_content)

    return "\n".join(lines)


def _run_selfassess(workdir: str | None = None) -> str:
    """Run a self-diagnostic for the yoyo-py agent.

    Collects code stats, test results, known issues (TODOs/FIXMEs/HACKs),
    git info, and model info into a single summary. Helps the agent or
    user quickly understand the current state of the project.
    """
    import re
    cwd = workdir or os.getcwd()
    lines: list[str] = []
    lines.append("═══════════════════════════════════════════")
    lines.append("  yoyo-py Self-Assessment Report")
    lines.append("═══════════════════════════════════════════")

    def _run(cmd: list[str], timeout: int = 60) -> tuple[bool, str]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
            return r.returncode == 0, r.stdout.strip() or r.stderr.strip()
        except FileNotFoundError:
            return False, f"{cmd[0]} not found"
        except subprocess.TimeoutExpired:
            return False, "timed out"
        except Exception as e:
            return False, str(e)

    # ── Code Statistics ────────────────────────────────────────────
    src_dir = os.path.join(cwd, "src")
    test_dir = os.path.join(cwd, "tests")
    total_src_lines = 0
    total_src_files = 0
    total_test_lines = 0
    total_test_files = 0

    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".py"):
                total_src_files += 1
                try:
                    with open(os.path.join(root, f)) as fh:
                        total_src_lines += sum(1 for _ in fh)
                except Exception:
                    pass

    if os.path.isdir(test_dir):
        for root, dirs, files in os.walk(test_dir):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                if f.endswith(".py"):
                    total_test_files += 1
                    try:
                        with open(os.path.join(root, f)) as fh:
                            total_test_lines += sum(1 for _ in fh)
                    except Exception:
                        pass

    lines.append("")
    lines.append("── Code Stats ──")
    lines.append(f"  Source:   {total_src_files} files, {total_src_lines:,} lines")
    lines.append(f"  Tests:    {total_test_files} files, {total_test_lines:,} lines")

    # ── Test Results ───────────────────────────────────────────────
    lines.append("")
    lines.append("── Test Results ──")
    ok, test_output = _run(["python", "-m", "pytest", "--tb=no", "-q"], timeout=120)
    if ok:
        # Extract summary line like "1088 passed in 10.62s"
        summary_lines = test_output.strip().splitlines()
        summary = summary_lines[-1] if summary_lines else test_output
        lines.append(f"  ✓ {summary}")
    else:
        # Show last few lines on failure
        fail_lines = test_output.strip().splitlines()[-5:]
        lines.append(f"  ✗ Tests failed:")
        for fl in fail_lines:
            lines.append(f"    {fl}")

    # ── Known Issues (TODOs/FIXMEs/HACKs) ──────────────────────────
    lines.append("")
    lines.append("── Known Issues (TODO/FIXME/HACK) ──")
    issue_count = 0
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if not f.endswith(".py"):
                continue
            filepath = os.path.join(root, f)
            try:
                with open(filepath) as fh:
                    for i, line_text in enumerate(fh, 1):
                        if re.search(r'#\s*(TODO|FIXME|HACK)', line_text, re.IGNORECASE):
                            rel = os.path.relpath(filepath, cwd)
                            # Truncate long lines
                            stripped = line_text.strip()
                            if len(stripped) > 80:
                                stripped = stripped[:77] + "..."
                            lines.append(f"  {rel}:{i}: {stripped}")
                            issue_count += 1
                            if issue_count >= 20:
                                lines.append("  ... (showing first 20)")
                                break
            except Exception:
                pass
            if issue_count >= 20:
                break
        if issue_count >= 20:
            break
    if issue_count == 0:
        lines.append("  ✨ No TODOs/FIXMEs/HACKs found — code is clean!")

    # ── Git Info ───────────────────────────────────────────────────
    lines.append("")
    lines.append("── Git ──")
    ok_branch, branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if ok_branch:
        lines.append(f"  Branch: {branch}")
        ok_log, log_output = _run(
            ["git", "log", "--oneline", "-5"]
        )
        if ok_log:
            for log_line in log_output.splitlines():
                lines.append(f"  {log_line}")
    else:
        lines.append("  (git not available)")

    # ── Model & Context ───────────────────────────────────────────
    lines.append("")
    lines.append("── Model ──")
    lines.append(f"  Context window table: {len(_MODEL_CONTEXT_WINDOWS)} models")
    lines.append(f"  Default context: {_DEFAULT_CONTEXT_WINDOW:,} tokens")

    lines.append("")
    lines.append("═══════════════════════════════════════════")
    return "\n".join(lines)


def _build_command_registry(
    agent: Agent,
    provider: GLMProvider,
    skills: SkillSet,
) -> CommandRegistry:
    """Build a CommandRegistry with all slash command handlers.

    Each handler receives the raw input line and a ctx dict (currently empty,
    reserved for future use). Handlers are closures that capture agent,
    provider, and skills from the REPL scope.

    Commands that need to trigger an agent turn return CommandResult with
    agent_prompt set — the REPL loop handles the async call.
    """
    registry = CommandRegistry()

    # ── Session commands ──────────────────────────────────────────

    @registry.register("quit", aliases=["exit"])
    def _cmd_quit(line: str, ctx: dict) -> CommandResult:
        _auto_save_on_exit(agent.state.messages, provider.model, usage=agent.state.usage)
        _save_readline_history()
        return CommandResult(output=f"\n{DIM}  bye 👋{RESET}\n", done=True)

    @registry.register("clear")
    def _cmd_clear(line: str, ctx: dict) -> CommandResult:
        agent.clear()
        return CommandResult(output=f"{DIM}  (conversation cleared){RESET}\n")

    @registry.register("help")
    def _cmd_help(line: str, ctx: dict) -> CommandResult:
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_help()
        return CommandResult(output=buf.getvalue())

    @registry.register("man")
    def _cmd_man(line: str, ctx: dict) -> CommandResult:
        command = line[4:].strip().lstrip("/") if len(line) > 4 else ""
        return CommandResult(output=_format_man_page(command) + "\n")

    @registry.register("redo")
    def _cmd_redo(line: str, ctx: dict) -> CommandResult:
        last_msg = _find_last_user_message(agent.state.messages)
        if last_msg is None:
            return CommandResult(output=f"{DIM}  No previous message to redo{RESET}\n")
        preview = last_msg[:100] + ("..." if len(last_msg) > 100 else "")
        print(f"{DIM}  Redoing: {preview}{RESET}")
        return CommandResult(output="", agent_prompt=last_msg)

    @registry.register("last")
    def _cmd_last(line: str, ctx: dict) -> CommandResult:
        last_response = _find_last_assistant_response(agent.state.messages)
        if last_response is None:
            return CommandResult(output=f"{DIM}  No previous response to show{RESET}\n")
        return CommandResult(output=_strip_interrupted_marker(last_response) + "\n")

    @registry.register("copy")
    def _cmd_copy(line: str, ctx: dict) -> CommandResult:
        last_response = _find_last_assistant_response(agent.state.messages)
        if last_response is None:
            return CommandResult(output=f"{DIM}  No previous response to copy{RESET}\n")
        clean = _strip_interrupted_marker(last_response)
        if _copy_to_clipboard(clean):
            return CommandResult(output=f"{GREEN}  ✓ Copied last response to clipboard{RESET}\n")
        return CommandResult(output=f"{YELLOW}  ⚠ Could not copy to clipboard — no clipboard tool available{RESET}\n")

    @registry.register("compact")
    def _cmd_compact(line: str, ctx: dict) -> CommandResult:
        old_count = len(agent.state.messages)
        old_tokens = Agent._estimate_tokens(agent.state.messages)
        agent.state.messages = Agent._compact_messages(agent.state.messages)
        new_count = len(agent.state.messages)
        new_tokens = Agent._estimate_tokens(agent.state.messages)
        # Validate after compact — same reason as in agent loop:
        # _compact_messages has had 3 bugs. Always check.
        issues = Agent._validate_messages(agent.state.messages)
        warn = ""
        if issues:
            warn = f"\n{DIM}  ⚠ compact validation issues: {issues}{RESET}"
        return CommandResult(
            output=f"{DIM}  (compacted: {old_count}→{new_count} messages, ~{old_tokens}→~{new_tokens} tokens){warn}{RESET}\n"
        )

    @registry.register("trim")
    def _cmd_trim(line: str, ctx: dict) -> CommandResult:
        """Trim old tool outputs to reduce context without losing conversation.

        Unlike /compact which summarizes and removes messages, /trim keeps
        all messages but truncates large tool outputs to their first 3000 chars.
        This is a safe way to shrink context while preserving conversation flow.
        """
        old_tokens = Agent._estimate_tokens(agent.state.messages)

        # Count tool outputs that are large before trimming
        tool_msgs = [m for m in agent.state.messages if m.get("role") == "tool"]
        large_before = sum(1 for m in tool_msgs if len(m.get("content", "")) > 3000)

        agent.state.messages = Agent._trim_tool_outputs(agent.state.messages)

        new_tokens = Agent._estimate_tokens(agent.state.messages)
        tool_msgs_after = [m for m in agent.state.messages if m.get("role") == "tool"]
        large_after = sum(1 for m in tool_msgs_after if len(m.get("content", "")) > 3000)

        saved = old_tokens - new_tokens
        if saved <= 0:
            return CommandResult(
                output=f"{DIM}  (nothing to trim — all tool outputs already compact){RESET}\n"
            )
        return CommandResult(
            output=f"{GREEN}  ✓ trimmed: {large_before}→{large_after} large tool outputs, ~{old_tokens}→~{new_tokens} tokens (saved ~{saved}){RESET}\n"
        )

    # ── Git commands ──────────────────────────────────────────────

    @registry.register("diff")
    def _cmd_diff(line: str, ctx: dict) -> CommandResult:
        diff_args = line[5:].strip() if len(line) > 5 else ""
        return CommandResult(output=_run_diff_enhanced(diff_args) + "\n")

    @registry.register("undo")
    def _cmd_undo(line: str, ctx: dict) -> CommandResult:
        return CommandResult(output=_git_undo() + "\n")

    @registry.register("log")
    def _cmd_log(line: str, ctx: dict) -> CommandResult:
        log_args = line[4:].strip() if len(line) > 4 else ""
        count = 10
        oneline = False
        if log_args:
            parts = log_args.split()
            for part in parts:
                if part == "--oneline":
                    oneline = True
                else:
                    try:
                        count = max(1, min(int(part), 100))
                    except ValueError:
                        return CommandResult(output=f"{YELLOW}Usage: /log [N] [--oneline]{RESET}\n")
        return CommandResult(output=_run_git_log(count=count, oneline=oneline) + "\n")

    @registry.register("commit")
    def _cmd_commit(line: str, ctx: dict) -> CommandResult:
        msg = line[7:].strip() if len(line) > 7 else ""
        if not msg:
            return CommandResult(output=f"{YELLOW}Usage: /commit <message>{RESET}\n")
        return CommandResult(output=_git_commit(msg) + "\n")

    @registry.register("review")
    def _cmd_review(line: str, ctx: dict) -> CommandResult:
        args_str = line[7:].strip() if len(line) > 7 else ""
        if "--commit" in args_str:
            review_result = _run_review(commit=True)
        elif "--staged" in args_str:
            review_result = _run_review(staged=True)
        elif args_str:
            return CommandResult(output=f"{YELLOW}Usage: /review [--commit | --staged]{RESET}\n")
        else:
            review_result = _run_review()
        if review_result.startswith("["):
            return CommandResult(output=review_result + "\n")
        return CommandResult(output="", agent_prompt=review_result)

    @registry.register("pr")
    def _cmd_pr(line: str, ctx: dict) -> CommandResult:
        pr_result = _run_pr_description()
        if pr_result.startswith("["):
            return CommandResult(output=pr_result + "\n")
        return CommandResult(output="", agent_prompt=pr_result)

    # ── Project commands ──────────────────────────────────────────

    @registry.register("tree")
    def _cmd_tree(line: str, ctx: dict) -> CommandResult:
        return CommandResult(output=_project_tree() + "\n")

    @registry.register("count")
    def _cmd_count(line: str, ctx: dict) -> CommandResult:
        return CommandResult(output=_run_count_command() + "\n")

    @registry.register("health")
    def _cmd_health(line: str, ctx: dict) -> CommandResult:
        return CommandResult(output=_run_health_check() + "\n")

    @registry.register("selfassess")
    def _cmd_selfassess(line: str, ctx: dict) -> CommandResult:
        return CommandResult(output=_run_selfassess() + "\n")

    @registry.register("test")
    def _cmd_test(line: str, ctx: dict) -> CommandResult:
        test_args = line[5:].strip() if len(line) > 5 else ""
        return CommandResult(output=_run_test_command(args=test_args) + "\n")

    @registry.register("fix")
    def _cmd_fix(line: str, ctx: dict) -> CommandResult:
        return CommandResult(output=_run_fix_command() + "\n")

    @registry.register("init")
    def _cmd_init(line: str, ctx: dict) -> CommandResult:
        force = "--force" in line.lower()
        return CommandResult(output=_run_init_command(force=force) + "\n")

    @registry.register("edit")
    def _cmd_edit(line: str, ctx: dict) -> CommandResult:
        filepath = line[5:].strip() if len(line) > 5 else ""
        return CommandResult(output=_run_edit_command(filepath) + "\n")

    @registry.register("cat")
    def _cmd_cat(line: str, ctx: dict) -> CommandResult:
        cat_args = line[4:].strip() if len(line) > 4 else ""
        return CommandResult(output=_run_cat_command(cat_args) + "\n")

    @registry.register("head")
    def _cmd_head(line: str, ctx: dict) -> CommandResult:
        head_args = line[5:].strip() if len(line) > 5 else ""
        return CommandResult(output=_run_head_command(head_args) + "\n")

    @registry.register("tail")
    def _cmd_tail(line: str, ctx: dict) -> CommandResult:
        tail_args = line[5:].strip() if len(line) > 5 else ""
        return CommandResult(output=_run_tail_command(tail_args) + "\n")

    @registry.register("du")
    def _cmd_du(line: str, ctx: dict) -> CommandResult:
        du_args = line[3:].strip() if len(line) > 3 else ""
        return CommandResult(output=_run_du_command(du_args) + "\n")

    @registry.register("find")
    def _cmd_find(line: str, ctx: dict) -> CommandResult:
        find_args = line[5:].strip() if len(line) > 5 else ""
        return CommandResult(output=_run_find_command(find_args) + "\n")

    @registry.register("wc")
    def _cmd_wc(line: str, ctx: dict) -> CommandResult:
        wc_args = line[3:].strip() if len(line) > 3 else ""
        return CommandResult(output=_run_wc_command(wc_args) + "\n")

    # ── Session info commands ─────────────────────────────────────

    @registry.register("status")
    def _cmd_status(line: str, ctx: dict) -> CommandResult:
        context_tokens = Agent._estimate_tokens(agent.state.messages)
        return CommandResult(
            output=_format_status_output(
                model=provider.model,
                cwd=os.getcwd(),
                messages=agent.state.messages,
                usage=agent.state.usage,
                skills_count=skills.count(),
                context_tokens=context_tokens,
                reasoning_effort=provider.reasoning_effort,
            ) + "\n"
        )

    @registry.register("tokens")
    def _cmd_tokens(line: str, ctx: dict) -> CommandResult:
        return CommandResult(output=f"{DIM}  {agent.state.usage}{RESET}\n")

    @registry.register("cost")
    def _cmd_cost(line: str, ctx: dict) -> CommandResult:
        return CommandResult(output=_estimate_cost(agent.state.usage, model=provider.model) + "\n")

    @registry.register("history")
    def _cmd_history(line: str, ctx: dict) -> CommandResult:
        show_tokens = "--tokens" in line
        exchange = "--exchange" in line
        # Parse --last N
        last_n = None
        import re as _re
        last_match = _re.search(r"--last\s+(\d+)", line)
        if last_match:
            last_n = int(last_match.group(1))
        return CommandResult(output=_format_history(
            agent.state.messages,
            show_tokens=show_tokens,
            last=last_n,
            exchange=exchange,
        ) + "\n")

    @registry.register("search")
    def _cmd_search(line: str, ctx: dict) -> CommandResult:
        search_args = line[7:].strip() if len(line) > 7 else ""
        if not search_args:
            return CommandResult(output=f"{YELLOW}Usage: /search <keyword> [--case]{RESET}\n")
        case_sensitive = "--case" in search_args
        keyword = search_args.replace("--case", "").strip()
        if not keyword:
            return CommandResult(output=f"{YELLOW}Usage: /search <keyword> [--case]{RESET}\n")
        return CommandResult(
            output=_search_conversation(agent.state.messages, keyword, case_sensitive=case_sensitive) + "\n"
        )

    @registry.register("grep")
    def _cmd_grep(line: str, ctx: dict) -> CommandResult:
        grep_args = line[5:].strip() if len(line) > 5 else ""
        return CommandResult(output=_run_grep(grep_args) + "\n")

    @registry.register("system")
    def _cmd_system(line: str, ctx: dict) -> CommandResult:
        return CommandResult(output=_format_system_prompt_display(agent.state.messages) + "\n")

    @registry.register("env")
    def _cmd_env(line: str, ctx: dict) -> CommandResult:
        return CommandResult(
            output=_show_env_info(
                model=provider.model,
                base_url=provider.base_url,
                provider=getattr(provider, '_provider_name', None),
                api_key=provider.api_key,
                max_tokens=provider.max_tokens,
                temperature=provider.temperature,
                top_p=provider.top_p,
            ) + "\n"
        )

    # ── Config commands ───────────────────────────────────────────

    @registry.register("config")
    def _cmd_config(line: str, ctx: dict) -> CommandResult:
        config_args = line[7:].strip() if len(line) > 7 else ""
        output, updates = _handle_config_command(
            args_str=config_args,
            temperature=provider.temperature,
            max_tokens=provider.max_tokens,
            top_p=provider.top_p,
            model=provider.model,
        )
        for key, value in updates.items():
            setattr(provider, key, value)
        # Persist config changes to .yoyo/config.json so they survive restarts
        if updates:
            _save_persistent_config(updates)
        return CommandResult(output=output + "\n")

    @registry.register("think")
    def _cmd_think(line: str, ctx: dict) -> CommandResult:
        # /think — control reasoning depth for models that support extended thinking
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

    @registry.register("version")
    def _cmd_version(line: str, ctx: dict) -> CommandResult:
        import sys
        output = (
            f"  yoyo-py v{__version__}\n"
            f"  Model: {provider.model}\n"
            f"  Python: {sys.version.split()[0]}"
        )
        return CommandResult(output=output + "\n")

    @registry.register("provider")
    def _cmd_provider(line: str, ctx: dict) -> CommandResult:
        # /provider — switch provider preset at runtime
        args_str = line[9:].strip() if len(line) > 9 else ""
        if not args_str:
            current = getattr(provider, '_provider_name', None) or "custom"
            return CommandResult(
                output=f"{DIM}  Current provider: {current} (model: {provider.model}){RESET}\n"
                f"{DIM}  Usage: /provider <name> [model] [--clear]{RESET}\n"
            )

        from .provider import PROVIDER_PRESETS, resolve_provider_config

        parts = args_str.split()
        provider_name = parts[0].lower()
        clear_history = "--clear" in parts

        # Validate the provider name
        if provider_name not in PROVIDER_PRESETS:
            available = ", ".join(sorted(PROVIDER_PRESETS.keys()))
            return CommandResult(
                output=f"{YELLOW}  Unknown provider: {provider_name}{RESET}\n"
                f"{DIM}  Available: {available}{RESET}\n"
            )

        preset = resolve_provider_config(provider_name)
        api_key = os.getenv(preset["env_key"], "")

        if not api_key:
            return CommandResult(
                output=f"{RED}  Error: {preset['env_key']} not set — "
                f"export it or set it in .env{RESET}\n"
            )

        # Parse optional model override (any arg that isn't --clear or the provider name)
        model_parts = [p for p in parts[1:] if p != "--clear" and not p.startswith("-")]
        new_model = model_parts[0] if model_parts else preset["default_model"]

        # Reconfigure the provider in-place
        old_name = getattr(provider, '_provider_name', None) or "custom"
        provider._provider_name = provider_name
        provider.api_key = api_key
        provider.base_url = preset["base_url"]
        provider.model = new_model
        # Recreate the OpenAI client with new credentials
        from openai import OpenAI
        provider.client = OpenAI(api_key=api_key, base_url=preset["base_url"])

        if clear_history:
            agent.clear()

        status = f"switched to {provider_name} (model: {new_model})"
        if clear_history:
            status += ", history cleared"
        return CommandResult(output=f"{GREEN}  ✓ {status}{RESET}\n")

    @registry.register("list-providers")
    def _cmd_list_providers(line: str, ctx: dict) -> CommandResult:
        return CommandResult(output=_format_providers_list(
            active_model=provider.model,
            active_provider=getattr(provider, '_provider_name', None),
        ) + "\n")

    # ── Persistence commands ──────────────────────────────────────

    @registry.register("save")
    def _cmd_save(line: str, ctx: dict) -> CommandResult:
        save_path = line[5:].strip() if len(line) > 5 else ""
        if not save_path:
            save_path = os.path.join(os.getcwd(), ".yoyo", "session.json")
        return CommandResult(output=_save_session(save_path, agent.state.messages, provider.model, usage=agent.state.usage) + "\n")

    @registry.register("export")
    def _cmd_export(line: str, ctx: dict) -> CommandResult:
        export_path = line[7:].strip() if len(line) > 7 else ""
        include_system = "--system" in export_path
        export_path = export_path.replace("--system", "").strip()
        if not export_path:
            export_path = os.path.join(os.getcwd(), "conversation.md")
        return CommandResult(
            output=_export_to_file(export_path, agent.state.messages, provider.model, include_system=include_system) + "\n"
        )

    @registry.register("load")
    def _cmd_load(line: str, ctx: dict) -> CommandResult:
        load_path = line[5:].strip() if len(line) > 5 else ""
        if not load_path:
            load_path = os.path.join(os.getcwd(), ".yoyo", "session.json")
        result = _load_session(load_path)
        if result is None:
            return CommandResult(output=f"{RED}  Failed to load session from {load_path}{RESET}\n{DIM}  File may not exist or be invalid{RESET}\n")
        messages, model, usage, warnings = result
        agent.state.messages = messages
        agent.state.usage = usage
        provider.model = model
        msg_count = len([m for m in messages if m.get("role") != "system"])
        output = f"{GREEN}  Session loaded from {load_path}{RESET}\n{DIM}  {msg_count} messages, model: {model}{RESET}"
        if warnings:
            output += f"\n{YELLOW}  ⚠ Session has {len(warnings)} issue(s):{RESET}"
            for w in warnings[:5]:
                output += f"\n{YELLOW}    • {w}{RESET}"
        return CommandResult(output=output + "\n")

    @registry.register("sessions")
    def _cmd_sessions(line: str, ctx: dict) -> CommandResult:
        """List all saved sessions in .yoyo/ with metadata."""
        sessions = _list_sessions()
        return CommandResult(output=_format_sessions_output(sessions) + "\n")

    @registry.register("rm")
    def _cmd_rm(line: str, ctx: dict) -> CommandResult:
        """Delete a saved session file from .yoyo/."""
        filename = line[3:].strip()
        if not filename:
            return CommandResult(output=f"{YELLOW}Usage: /rm <session-file>{RESET}\n{DIM}  Use /sessions to list available files{RESET}\n")
        if _delete_session(filename):
            return CommandResult(output=f"{GREEN}  ✓ Deleted {filename}{RESET}\n")
        return CommandResult(output=f"{RED}  Failed to delete {filename}{RESET}\n{DIM}  File may not exist or is not a .json session file{RESET}\n")

    @registry.register("resume")
    def _cmd_resume(line: str, ctx: dict) -> CommandResult:
        result = _handle_resume_command()
        if isinstance(result, str):
            return CommandResult(output=f"{DIM}  {result}{RESET}\n")
        messages, model, usage, warnings = result
        agent.state.messages = messages
        agent.state.usage = usage
        provider.model = model
        real_count = len([m for m in messages if m.get("role") != "system"])
        output = f"{GREEN}  ✓ Resumed session ({real_count} messages, model: {model}){RESET}"
        if warnings:
            output += f"\n{YELLOW}  ⚠ Session has {len(warnings)} issue(s):{RESET}"
            for w in warnings[:5]:
                output += f"\n{YELLOW}    • {w}{RESET}"
        return CommandResult(output=output + "\n")

    @registry.register("remember")
    def _cmd_remember(line: str, ctx: dict) -> CommandResult:
        text = line[9:].strip() if len(line) > 9 else ""
        if not text:
            return CommandResult(output=f"{YELLOW}Usage: /remember <text>{RESET}\n")
        return CommandResult(output=_add_memory(text) + "\n")

    @registry.register("memories")
    def _cmd_memories(line: str, ctx: dict) -> CommandResult:
        return CommandResult(output=_list_memories() + "\n")

    @registry.register("forget")
    def _cmd_forget(line: str, ctx: dict) -> CommandResult:
        mem_id_str = line[7:].strip() if len(line) > 7 else ""
        if not mem_id_str:
            return CommandResult(output=f"{YELLOW}Usage: /forget <id>{RESET}\n")
        try:
            mem_id = int(mem_id_str)
        except ValueError:
            return CommandResult(output=f"{RED}  ID must be a number{RESET}\n")
        return CommandResult(output=_forget_memory(mem_id) + "\n")

    @registry.register("backups")
    def _cmd_backups(line: str, ctx: dict) -> CommandResult:
        args = line[8:].strip() if len(line) > 8 else ""
        return CommandResult(output=_run_backups_command(args) + "\n")

    @registry.register("skills")
    def _cmd_skills(line: str, ctx: dict) -> CommandResult:
        if skills.is_empty():
            return CommandResult(output=f"{DIM}  No skills loaded{RESET}\n")
        lines = []
        for name, content in skills.all():
            lines.append(f"  {CYAN}{name}{RESET}: {content[:80]}...")
        return CommandResult(output="\n".join(lines) + "\n")

    @registry.register("commands")
    def _cmd_commands(line: str, ctx: dict) -> CommandResult:
        custom_cmds = _load_custom_commands()
        if not custom_cmds:
            return CommandResult(output=f"{DIM}  No custom commands found — create .yoyo/commands/*.md{RESET}\n")
        lines = [f"{BOLD}  Custom Commands:{RESET}"]
        for name, info in custom_cmds.items():
            desc = info.get("description", "")
            if desc:
                lines.append(f"    {CYAN}/{name}{RESET} — {desc}")
            else:
                lines.append(f"    {CYAN}/{name}{RESET}")
        return CommandResult(output="\n".join(lines) + "\n")

    # ── Model/cd/revert — commands that mutate REPL state ─────────

    @registry.register("model")
    def _cmd_model(line: str, ctx: dict) -> CommandResult:
        model_args = line[6:].strip()
        keep_history = "--keep" in model_args
        new_model = model_args.replace("--keep", "").strip()
        if not new_model:
            # Show current model info and context window
            from .provider import get_model_context_window
            ctx_window = get_model_context_window(provider.model)
            threshold = Agent._compute_compact_threshold(provider.model)
            return CommandResult(
                output=f"{DIM}  Current model: {provider.model}{RESET}\n"
                f"{DIM}  Context window: {ctx_window:,} tokens{RESET}\n"
                f"{DIM}  Compact threshold: {threshold:,} tokens (60%){RESET}\n"
                f"{DIM}  Usage: /model <name> [--keep]{RESET}\n"
            )
        provider.model = new_model
        if keep_history:
            return CommandResult(output=f"{DIM}  (switched to {new_model}, history preserved){RESET}\n")
        else:
            agent.clear()
            return CommandResult(output=f"{DIM}  (switched to {new_model}, conversation cleared){RESET}\n")

    @registry.register("models")
    def _cmd_models(line: str, ctx: dict) -> CommandResult:
        """List all known models with context window sizes."""
        from .provider import MODEL_CONTEXT_WINDOWS, format_context_size

        lines_out = [f"{BOLD}Known models:{RESET}\n"]
        current = provider.model
        groups: dict[str, list[tuple[str, int]]] = {}
        for model, ctx in sorted(MODEL_CONTEXT_WINDOWS.items()):
            prefix = model.split("-")[0].lower()
            groups.setdefault(prefix, []).append((model, ctx))

        for prefix in sorted(groups):
            for model, ctx in groups[prefix]:
                marker = f" {GREEN}← current{RESET}" if model == current else ""
                lines_out.append(f"  {model:30} {format_context_size(ctx):>8} ctx{marker}")
            lines_out.append("")

        lines_out.append(f"{DIM}  Usage: /model <name> [--keep]{RESET}")
        return CommandResult(output="\n".join(lines_out) + "\n")

    @registry.register("cd")
    def _cmd_cd(line: str, ctx: dict) -> CommandResult:
        target = line[3:].strip() if len(line) > 3 else ""
        result = _handle_cd_command(target)
        if result.startswith("[OK]"):
            _update_system_prompt_cwd(agent.state.messages)
        return CommandResult(output=result + "\n")

    @registry.register("append")
    def _cmd_append(line: str, ctx: dict) -> CommandResult:
        text = line[8:].strip() if len(line) > 8 else ""
        result = _handle_append_command(text, agent.state.messages)
        return CommandResult(output=f"{result}\n")

    @registry.register("revert")
    def _cmd_revert(line: str, ctx: dict) -> CommandResult:
        revert_args = line[7:].strip() if len(line) > 7 else ""
        try:
            count = int(revert_args) if revert_args else 1
        except ValueError:
            return CommandResult(output=f"{YELLOW}Usage: /revert [N] — remove last N exchanges (default 1){RESET}\n")
        if count < 1:
            return CommandResult(output=f"{YELLOW}Count must be at least 1{RESET}\n")
        result = _handle_revert_command(agent.state.messages, count=count)
        if isinstance(result, str):
            return CommandResult(output=f"{DIM}  {result}{RESET}\n")
        new_messages, removed = result
        agent.state.messages = new_messages
        return CommandResult(
            output=f"{GREEN}  ✓ Reverted {removed} message(s) (/{count} exchange{'s' if count > 1 else ''}){RESET}\n"
        )

    return registry


_MAN_PAGES: dict[str, str] = {
    "shell": f"""\
{BOLD}!command{RESET} — Shell escape (run command, feed output to agent)
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  !<command>           Run command and send output to agent as context

{BOLD}Examples:{RESET}
  !git log --oneline -5    Share recent commits with the agent
  !pytest tests/ -x        Share test results with the agent
  !cat README.md           Share file contents with the agent
  !docker ps               Share running containers with the agent

{DIM}Like IPython's ! syntax. The command runs in your shell, and the
output is sent to the agent as context. Useful for sharing command
output without copy-pasting. Output is truncated to 5000 chars.{RESET}""",

    "test": f"""\
{BOLD}/test{RESET} — Run project tests
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /test                Run the full test suite
  /test <file>         Run a specific test file
  /test -k <pattern>   Run tests matching a keyword pattern
  /test -x             Stop on first failure
  /test --lf           Re-run last failed tests
  /test -v             Verbose output

{BOLD}Examples:{RESET}
  /test tests/test_agent.py
  /test -k test_compact
  /test tests/test_foo.py -x -v

{DIM}Detects project type (Python/Node/Rust/Go/Java) and runs the
appropriate test runner. Extra args are passed through to pytest,
cargo test, go test, npm test, or mvn test.{RESET}""",

    "health": f"""\
{BOLD}/health{RESET} — Run build/test/lint diagnostics
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /health              Run all diagnostics for the project

{DIM}Detects project type and runs appropriate checks:
  Python: pytest + ruff/flake8 + mypy
  Node:   npm test + npm lint
  Rust:   cargo test + cargo clippy
  Go:     go test + go vet
  Java:   mvn test{RESET}""",

    "selfassess": f"""\
{BOLD}/selfassess{RESET} — Run a self-diagnostic report
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /selfassess          Show a self-assessment report

{DIM}Shows:
  • Code statistics (source/test files and lines)
  • Test results (pytest summary)
  • Known issues (TODOs/FIXMEs/HACKs in src/)
  • Git info (branch, recent commits)
  • Model info (context window table){RESET}""",

    "fix": f"""\
{BOLD}/fix{RESET} — Auto-fix lint/format errors
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /fix                 Auto-fix lint and format errors

{DIM}Runs appropriate fixers for the project type:
  Python: ruff check --fix / black / isort
  Node:   npm run fix (if configured)
  Rust:   cargo fix{RESET}""",

    "commit": f"""\
{BOLD}/commit{RESET} — Stage all and commit
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /commit <message>    Stage all changes and commit with message

{BOLD}Example:{RESET}
  /commit fix: handle empty input in search

{DIM}Runs git add -A followed by git commit -m <message>.
To review changes first, use /diff or /review.{RESET}""",

    "review": f"""\
{BOLD}/review{RESET} — AI code review of changes
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /review              Review current unstaged changes
  /review --staged     Review staged changes
  /review --commit     Review the last commit

{DIM}Sends the diff to the LLM for review and returns feedback
on code quality, potential bugs, and suggestions.{RESET}""",

    "diff": f"""\
{BOLD}/diff{RESET} — Show git changes
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /diff                Show summary of uncommitted changes
  /diff <file>         Show diff for a specific file
  /diff --full         Show full diff output
  /diff --staged       Show staged changes only
  /diff --stat         Show diffstat summary

{BOLD}Examples:{RESET}
  /diff src/agent.py         Diff a specific file
  /diff --staged --full      Full staged diff
  /diff --stat               Quick stat summary

{DIM}Use /review for AI-powered review of the changes.{RESET}""",

    "status": f"""\
{BOLD}/status{RESET} — Show session info
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /status              Show model, tokens, git branch, context size

{DIM}Displays: active model, token usage (input/output), git branch,
dirty/clean state, context token estimate, loaded skills count.{RESET}""",

    "config": f"""\
{BOLD}/config{RESET} — View/set generation parameters
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /config                          Show current settings
  /config temperature <value>      Set temperature (0.0-2.0)
  /config max_tokens <value>       Set max output tokens
  /config top_p <value>            Set top_p (0.0-1.0)
  /config reset                    Reset all to defaults

{BOLD}Example:{RESET}
  /config temperature 0.7{RESET}""",

    "model": f"""\
{BOLD}/model{RESET} — Switch model mid-session
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /model <name>        Switch model (clears history)
  /model <name> --keep Switch model (preserve history)

{BOLD}Examples:{RESET}
  /model gpt-4o
  /model deepseek-chat --keep

{DIM}The model name is passed directly to the API provider.
Use /list-providers to see available provider presets.{RESET}""",

    "compact": f"""\
{BOLD}/compact{RESET} — Compact conversation history
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /compact             Summarize old messages to reduce context size

{DIM}Compacts the conversation by replacing old messages with a summary.
Auto-compaction happens when context exceeds the threshold (~80k tokens),
but you can manually trigger it anytime.
Use /status to see current context size.{RESET}""",

    "export": f"""\
{BOLD}/export{RESET} — Export conversation as markdown
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /export [path]              Export as markdown (default: conversation.md)
  /export [path] --system     Include system prompt in export

{BOLD}Example:{RESET}
  /export notes.md{RESET}""",

    "search": f"""\
{BOLD}/search{RESET} — Search conversation history
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /search <keyword>     Search conversation (case-insensitive)
  /search <keyword> --case   Case-sensitive search

{BOLD}Example:{RESET}
  /search authentication{RESET}""",

    "grep": f"""\
{BOLD}/grep{RESET} — Search file contents
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /grep <pattern>              Search files (case-insensitive)
  /grep <pattern> --case      Case-sensitive search
  /grep <pattern> --glob *.py Filter by file pattern
  /grep <pattern> -C 3        Show 3 lines of context around matches

{BOLD}Examples:{RESET}
  /grep TODO
  /grep "class Agent" --glob *.py
  /grep "def test_" --case
  /grep "import os" -C 2{RESET}""",

    "think": f"""\
{BOLD}/think{RESET} — Control reasoning depth
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /think               Show current reasoning effort
  /think low|medium|high   Set reasoning effort
  /think off           Disable extended thinking (use API default)

{DIM}Controls extended thinking depth for models that support it.
Higher effort = deeper reasoning but slower and more tokens.{RESET}""",

    "save": f"""\
{BOLD}/save{RESET} — Save session
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /save [path]         Save session (default: .yoyo/session.json)

{BOLD}Example:{RESET}
  /save .yoyo/backup.json

{DIM}Sessions auto-save on exit. Use /save for explicit checkpoints.{RESET}""",

    "load": f"""\
{BOLD}/load{RESET} — Load session
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /load [path]         Load session (default: .yoyo/session.json)

{DIM}Restores messages, model, and token usage from a saved session.{RESET}""",

    "redo": f"""\
{BOLD}/redo{RESET} — Re-send last user prompt
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /redo                Re-send the last user message to the LLM

{DIM}Useful when the response wasn't good enough and you want to try
again with the same prompt.{RESET}""",

    "append": f"""\
{BOLD}/append{RESET} — Inject context into conversation without agent response
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /append <text>       Add text as a user message (no agent response)

{BOLD}Example:{RESET}
  /append Here's the error I'm seeing: ValueError: invalid input

{DIM}Useful for building up context (errors, notes, file contents) before
asking a question. The agent sees the message on the next turn.{RESET}""",

    "revert": f"""\
{BOLD}/revert{RESET} — Remove messages from history
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /revert [N]          Remove last N exchanges (default: 1)

{BOLD}Example:{RESET}
  /revert 3            Remove last 3 user-assistant exchanges

{DIM}Removes complete exchanges (user + assistant + tool messages).
Does NOT undo file changes — use /undo for that.{RESET}""",

    "undo": f"""\
{BOLD}/undo{RESET} — Undo uncommitted changes
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /undo                Restore all files to HEAD state

{DIM}Runs git checkout -- . to discard uncommitted changes.
This is destructive — make sure you want to lose those changes.{RESET}""",

    "log": f"""\
{BOLD}/log{RESET} — Show recent git commits
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /log [N] [--oneline]   Show last N commits (default: 10)

{BOLD}Examples:{RESET}
  /log 20
  /log --oneline
  /log 5 --oneline{RESET}""",

    "pr": f"""\
{BOLD}/pr{RESET} — Generate PR description
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /pr                  Generate a PR description from current changes

{DIM}Analyzes git diff and commit history to suggest a PR title,
description, and type (feature/fix/refactor).{RESET}""",

    "tree": f"""\
{BOLD}/tree{RESET} — Show project structure
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /tree                Show directory tree of the project

{DIM}Displays a visual tree of files and directories, skipping
common ignore patterns (.git, __pycache__, node_modules, etc.).{RESET}""",

    "count": f"""\
{BOLD}/count{RESET} — Count lines of code by language
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /count               Show line counts and file counts by language

{DIM}Scans the project directory and categorizes files by language,
showing total lines, file count, and percentage per language.{RESET}""",

    "env": f"""\
{BOLD}/env{RESET} — Show provider configuration
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /env                 Show model, base URL, API key (masked), params

{DIM}Displays the current provider configuration with the API key
partially masked for security.{RESET}""",

    "edit": f"""\
{BOLD}/edit{RESET} — Open file in editor
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /edit <filepath>     Open file in $EDITOR (default: vim)
  /edit                Open the last file written by the agent

{DIM}After closing the editor, detects if the file was modified
and offers to commit the changes.{RESET}""",

    "init": f"""\
{BOLD}/init{RESET} — Generate YOYO.md context file
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /init                Scan project and generate YOYO.md
  /init --force        Overwrite existing YOYO.md

{DIM}Scans the project structure, dependencies, and key files to
create a YOYO.md that helps the agent understand the project.{RESET}""",

    "remember": f"""\
{BOLD}/remember{RESET} — Save a project fact
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /remember <text>     Save a fact for future sessions

{BOLD}Examples:{RESET}
  /remember Use pytest for tests, test files in tests/
  /remember The main API endpoint is /api/v2/

{DIM}Facts are stored in .yoyo/memories.json and loaded in future
sessions automatically. Use /memories to list, /forget <id> to remove.{RESET}""",

    "memories": f"""\
{BOLD}/memories{RESET} — List remembered facts
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /memories            List all remembered project facts

{DIM}Shows all facts saved with /remember, with their IDs.
Use /forget <id> to remove a specific fact.{RESET}""",

    "forget": f"""\
{BOLD}/forget{RESET} — Remove a remembered fact
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /forget <id>         Remove a fact by its ID number

{BOLD}Example:{RESET}
  /forget 3

{DIM}Use /memories to see all facts and their IDs.{RESET}""",

    "clear": f"""\
{BOLD}/clear{RESET} — Clear conversation history
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /clear               Clear all messages (keeps system prompt)

{DIM}Removes all conversation messages but preserves the system prompt,
model, and configuration. Useful for starting a fresh topic.{RESET}""",

    "last": f"""\
{BOLD}/last{RESET} — Redisplay last response
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /last                Show the last assistant response again

{DIM}Useful when the response scrolled off screen or you want
to re-read it.{RESET}""",

    "backups": f"""\
{BOLD}/backups{RESET} — List, view, and restore file backups
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /backups              List all file backups
  /backups show <N>     Show content of backup #N
  /backups restore <N>  Restore backup #N to original file path

{BOLD}Examples:{RESET}
  /backups              See all available backups
  /backups show 1       View the first backup's content
  /backups restore 1    Restore the first backup

{DIM}Backups are created automatically when write_file or edit_file
overwrites an existing file. Stored in .yoyo/backups/ with a max
of 10 backups per file.{RESET}""",

    "copy": f"""\
{BOLD}/copy{RESET} — Copy last response to clipboard
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /copy                Copy the last assistant response to clipboard

{DIM}Uses pbcopy (macOS) or xclip (Linux).{RESET}""",

    "resume": f"""\
{BOLD}/resume{RESET} — Resume last auto-saved session
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /resume              Load the most recent auto-saved session

{DIM}Sessions are auto-saved to .yoyo/ on exit. This command loads
the most recent one.{RESET}""",

    "cd": f"""\
{BOLD}/cd{RESET} — Change working directory
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /cd [path]           Change working directory (default: home)

{BOLD}Examples:{RESET}
  /cd ~/projects/myapp
  /cd ../other-repo
  /cd                  Go to home directory

{DIM}Changes the directory where tools (bash, read_file, etc.) operate.{RESET}""",

    "tokens": f"""\
{BOLD}/tokens{RESET} — Show token usage
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /tokens              Show input/output token counts and totals

{DIM}Displays cumulative token usage for the current session.{RESET}""",

    "cost": f"""\
{BOLD}/cost{RESET} — Estimate API cost
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /cost                Estimate API cost from token usage

{DIM}Shows estimated cost based on token counts and known pricing
for common models.{RESET}""",

    "history": f"""\
{BOLD}/history{RESET} — Show conversation history
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /history             Show conversation history summary
  /history --tokens    Include token estimates per message
  /history --last N    Show only the last N messages
  /history --exchange  Hide tool messages (cleaner conversation view)
  /history --last 10 --exchange

{DIM}Shows a compact summary of messages in the conversation.
--last N is useful for long conversations. --exchange filters out
tool output messages for a cleaner user↔assistant flow.{RESET}""",

    "system": f"""\
{BOLD}/system{RESET} — View current system prompt
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /system              Display the current system prompt

{DIM}Shows the full system prompt being sent to the model, including
any loaded skills and project context.{RESET}""",

    "list-providers": f"""\
{BOLD}/list-providers{RESET} — List available provider presets
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /list-providers      Show available provider presets

{DIM}Lists all built-in provider configurations (model, base URL,
and description) that can be used with --provider flag.{RESET}""",

    "provider": f"""\
{BOLD}/provider{RESET} — Switch provider preset at runtime
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /provider                  Show current provider info
  /provider <name>           Switch to a provider preset
  /provider <name> <model>   Switch with a custom model
  /provider <name> --clear   Switch and clear history

{BOLD}Examples:{RESET}
  /provider openai
  /provider deepseek deepseek-reasoner
  /provider glm glm-4-plus --clear

{DIM}Switches the API endpoint and credentials to a different provider.
History is preserved by default (use --clear to reset).
Use /list-providers to see available presets.{RESET}""",

    "sessions": f"""\
{BOLD}/sessions{RESET} — List saved sessions
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /sessions            List saved sessions in .yoyo/

{DIM}Shows all session files with metadata (date, message count,
model, token usage).{RESET}""",

    "rm": f"""\
{BOLD}/rm{RESET} — Delete a session file
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /rm <file>           Delete a session file from .yoyo/

{BOLD}Example:{RESET}
  /rm old-session.json

{DIM}Removes a session file from the .yoyo/ directory.
Use /sessions to see available files.{RESET}""",

    "skills": f"""\
{BOLD}/skills{RESET} — List loaded skills
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /skills              List all loaded skills

{DIM}Shows skills loaded from .yoyo/skills/ or via --skills flag.
Each skill provides the agent with additional capabilities.{RESET}""",

    "commands": f"""\
{BOLD}/commands{RESET} — List custom slash commands
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /commands            List custom commands from .yoyo/commands/

{DIM}Custom commands are markdown files in .yoyo/commands/ that
become available as /<name> commands in the session.{RESET}""",

    "help": f"""\
{BOLD}/help{RESET} — Show help
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /help                Show all available commands

{DIM}Displays the full command reference. Use /man <command>
for detailed help on a specific command.{RESET}""",

    "man": f"""\
{BOLD}/man{RESET} — Show command manual
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /man <command>       Show detailed help for a command
  /man                 List available commands with help

{BOLD}Example:{RESET}
  /man test
  /man commit

{DIM}Shows usage, examples, and description for a command.{RESET}""",

    "quit": f"""\
{BOLD}/quit, /exit{RESET} — Exit the agent
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /quit                Exit the session (auto-saves)
  /exit                Same as /quit

{DIM}Session is auto-saved to .yoyo/ before exiting.{RESET}""",

    "exit": f"""\
{BOLD}/exit{RESET} — Exit the agent
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /exit                Exit the session (auto-saves)
  /quit                Same as /exit

{DIM}Session is auto-saved to .yoyo/ before exiting.{RESET}""",

    "version": f"""\
{BOLD}/version{RESET} — Show version info
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /version             Show yoyo-py version, model, and Python version

{DIM}Displays the current yoyo-py version, active model name,
and Python runtime version.{RESET}""",

    "head": f"""\
{BOLD}/head{RESET} — Show first lines of a file
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /head <file>          Show first 10 lines (default)
  /head <file> <N>      Show first N lines

{BOLD}Examples:{RESET}
  /head src/agent.py        First 10 lines
  /head src/agent.py 30     First 30 lines

{DIM}More efficient than /cat for large files — reads only what's needed.
Use /tail to see the end of a file.{RESET}""",

    "tail": f"""\
{BOLD}/tail{RESET} — Show last lines of a file
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /tail <file>          Show last 10 lines (default)
  /tail <file> <N>      Show last N lines

{BOLD}Examples:{RESET}
  /tail src/agent.py        Last 10 lines
  /tail src/agent.py 30     Last 30 lines

{DIM}Shows the end of a file with original line numbers preserved.
Use /head to see the beginning.{RESET}""",

    "du": f"""\
{BOLD}/du{RESET} — Show file and directory sizes
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /du                  Show sizes in current directory
  /du <path>           Show sizes for given path (file or dir)

{BOLD}Examples:{RESET}
  /du src/                List files in src/ sorted by size
  /du README.md           Show size of a single file

{DIM}Files and directories are sorted by size (largest first).
Sizes are shown in human-readable format (B, KB, MB, GB).{RESET}""",

    "find": f"""\
{BOLD}/find{RESET} — Find files by name pattern
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /find <pattern>         Find files matching glob pattern

{BOLD}Examples:{RESET}
  /find *.py              Find all Python files
  /find *test*            Find files with "test" in the name
  /find README.md         Find a specific file

{DIM}Supports standard glob patterns: * (any substring), ** (recursive).
Searches from the current working directory.
Filters out .git, __pycache__, node_modules, and other noise.{RESET}""",

    "wc": f"""\
{BOLD}/wc{RESET} — Count lines, words, and characters in files
{DIM}───────────────────────────────────{RESET}

{BOLD}Usage:{RESET}
  /wc <file> [file2 ...]  Count lines, words, and chars

{BOLD}Examples:{RESET}
  /wc README.md           Count a single file
  /wc src/agent.py src/tools.py   Count multiple files

{DIM}Shows a table with line, word, and character counts.
For multiple files, shows a total row.{RESET}""",
}


def _format_man_page(command: str) -> str:
    """Format and return the man page for a command.

    Args:
        command: Command name (without /), or empty for usage hint.

    Returns:
        Formatted man page text.
    """
    if not command:
        available = ", ".join(sorted(_MAN_PAGES.keys()))
        return (
            f"{YELLOW}Usage: /man <command>{RESET}\n"
            f"{DIM}  Available commands: {available}{RESET}"
        )

    if command not in _MAN_PAGES:
        available = ", ".join(sorted(_MAN_PAGES.keys()))
        return (
            f"{RED}  No help for /{command}{RESET}\n"
            f"{DIM}  Available: {available}{RESET}"
        )

    return _MAN_PAGES[command]


def _print_help() -> None:
    print(f"""
{BOLD}  Session:{RESET}
    {CYAN}/quit, /exit{RESET}    Exit the agent
    {CYAN}/help{RESET}           Show this help
    {CYAN}/man <cmd>{RESET}       Show detailed help for a command
    {CYAN}!<command>{RESET}       Run shell command and feed output to agent
    {CYAN}/clear{RESET}          Clear conversation history
    {CYAN}/redo{RESET}           Re-send the last user prompt
    {CYAN}/revert [N]{RESET}      Remove last N exchanges from history (default 1)
    {CYAN}/last{RESET}           Redisplay the last assistant response
    {CYAN}/copy{RESET}           Copy last response to clipboard
    {CYAN}/resume{RESET}         Resume last auto-saved session
    {CYAN}/compact{RESET}        Compact conversation history
    {CYAN}/trim{RESET}          Trim large tool outputs (lighter than compact)
    {CYAN}/cd [path]{RESET}      Change working directory (default: home)
    {CYAN}/model <name>{RESET}   Switch model (clears history, use --keep to preserve)
    {CYAN}/models{RESET}         List known models with context window sizes

  {BOLD}Git:{RESET}
    {CYAN}/diff{RESET}           Show git changes (--full, --staged, <file>)
    {CYAN}/log [N] [--oneline]{RESET}  Show recent git commits (default 10)
    {CYAN}/commit <msg>{RESET}   Stage all and commit
    {CYAN}/undo{RESET}           Undo uncommitted changes (restore files to HEAD)
    {CYAN}/review{RESET}             AI code review of current changes
    {CYAN}/review --commit{RESET}    Review the last commit
    {CYAN}/review --staged{RESET}    Review staged changes
    {CYAN}/pr{RESET}             Generate PR description from current changes

  {BOLD}Project:{RESET}
    {CYAN}/tree{RESET}           Show project directory structure
    {CYAN}/count{RESET}          Count lines of code by language
    {CYAN}/init{RESET}           Generate YOYO.md context file (--force to overwrite)
    {CYAN}/edit <file>{RESET}    Open file in $EDITOR (default: vim)
    {CYAN}/cat <file> [off] [n]{RESET}  View file content with line numbers
    {CYAN}/head <file> [n]{RESET}  Show first N lines (default 10)
    {CYAN}/tail <file> [n]{RESET}  Show last N lines (default 10)
    {CYAN}/du [path]{RESET}       Show file and directory sizes
    {CYAN}/find <pattern>{RESET}  Find files by name pattern (glob)
    {CYAN}/wc <file> [files]{RESET}  Count lines, words, chars in files
    {CYAN}/health{RESET}         Run build/test/lint diagnostics
    {CYAN}/selfassess{RESET}     Self-diagnostic report (code stats, tests, TODOs, git)
    {CYAN}/test{RESET}           Run project tests (optional: /test <file> or /test -k pattern)
    {CYAN}/fix{RESET}            Auto-fix lint/format errors

  {BOLD}Session Info:{RESET}
    {CYAN}/status{RESET}         Show session info (model, tokens, context)
    {CYAN}/tokens{RESET}         Show token usage
    {CYAN}/cost{RESET}           Estimate API cost from token usage
    {CYAN}/history{RESET}        Show conversation history (--tokens for estimates)
    {CYAN}/search <keyword>{RESET} Search conversation history (--case for case-sensitive)
    {CYAN}/grep <pattern>{RESET}  Search file contents (--case, --glob <pattern>)
    {CYAN}/system{RESET}         View current system prompt
    {CYAN}/env{RESET}            Show provider config (model, base URL, API key)

  {BOLD}Config:{RESET}
    {CYAN}/config{RESET}         View/set generation parameters (temperature, max_tokens, top_p)
    {CYAN}/think [level]{RESET}  Set reasoning effort (low/medium/high/off)
    {CYAN}/list-providers{RESET}  List available provider presets
    {CYAN}/provider <name>{RESET} Switch provider preset at runtime

  {BOLD}Persistence:{RESET}
    {CYAN}/save [path]{RESET}    Save session (default: .yoyo/session.json)
    {CYAN}/load [path]{RESET}    Load session (default: .yoyo/session.json)
    {CYAN}/sessions{RESET}       List saved sessions in .yoyo/ with metadata
    {CYAN}/rm <file>{RESET}      Delete a session file from .yoyo/
    {CYAN}/export [path]{RESET}  Export conversation as markdown (--system to include system prompt)
    {CYAN}/remember <text>{RESET} Remember a project fact for future sessions
    {CYAN}/memories{RESET}       List all remembered facts
    {CYAN}/forget <id>{RESET}    Forget a remembered fact by ID
    {CYAN}/backups{RESET}        List, show, and restore file backups
    {CYAN}/skills{RESET}         List loaded skills
    {CYAN}/commands{RESET}       List custom slash commands from .yoyo/commands/

{BOLD}  Tools:{RESET}
    bash, read_file, write_file, edit_file, search, list_files, mkdir, glob, rename
""")
