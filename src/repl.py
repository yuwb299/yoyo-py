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


def print_banner() -> None:
    print(f"\n{BOLD}{CYAN}  yoyo-py{RESET} {DIM}v{__version__} — a self-evolving coding agent (Python + GLM 5){RESET}")
    print(f"{DIM}  Type /help for commands, /quit to exit{RESET}\n")


def print_usage(usage) -> None:
    if usage.input_tokens > 0 or usage.output_tokens > 0:
        print(f"\n{DIM}  tokens: {usage}{RESET}")


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

    # Load YOYO.md or CLAUDE.md if present
    for ctx_file in ("YOYO.md", "CLAUDE.md"):
        ctx_path = os.path.join(os.getcwd(), ctx_file)
        if os.path.exists(ctx_path):
            try:
                content = open(ctx_path, encoding="utf-8").read()
                parts.append(f"\n# Project Context ({ctx_file})\n{content}")
                break
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
            summary = f"edit → {tool_args.get('path', '?')}"
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

    print_banner()
    print(f"{DIM}  model: {provider.model}{RESET}")
    if not skills.is_empty():
        print(f"{DIM}  skills: {skills.count()} loaded{RESET}")
    print(f"{DIM}  cwd:   {os.getcwd()}{RESET}\n")

    # Handle piped input
    if pipe_input:
        await _run_agent_turn(agent, pipe_input)
        return

    # Handle initial prompt (-p flag)
    if initial_prompt:
        await _run_agent_turn(agent, initial_prompt)
        return

    # Interactive loop
    while True:
        try:
            line = _read_multiline_input()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}  bye 👋{RESET}\n")
            break

        line = line.strip()
        if not line:
            continue

        # Handle slash commands
        if line.startswith("/"):
            cmd = line.lower()
            if cmd in ("/quit", "/exit"):
                print(f"\n{DIM}  bye 👋{RESET}\n")
                break
            elif cmd == "/clear":
                agent.clear()
                print(f"{DIM}  (conversation cleared){RESET}\n")
                continue
            elif cmd == "/redo":
                last_msg = _find_last_user_message(agent.state.messages)
                if last_msg is None:
                    print(f"{DIM}  No previous message to redo{RESET}\n")
                    continue
                print(f"{DIM}  Redoing: {last_msg[:100]}{'...' if len(last_msg) > 100 else ''}{RESET}")
                await _run_agent_turn(agent, last_msg)
                continue
            elif cmd == "/help":
                _print_help()
                continue
            elif cmd.startswith("/model "):
                new_model = line[7:].strip()
                provider.model = new_model
                agent.clear()
                print(f"{DIM}  (switched to {new_model}, conversation cleared){RESET}\n")
                continue
            elif cmd == "/skills":
                if skills.is_empty():
                    print(f"{DIM}  No skills loaded{RESET}")
                else:
                    for name, content in skills.all():
                        print(f"  {CYAN}{name}{RESET}: {content[:80]}...")
                print()
                continue
            elif cmd == "/compact":
                old_count = len(agent.state.messages)
                old_tokens = Agent._estimate_tokens(agent.state.messages)
                agent.state.messages = Agent._compact_messages(agent.state.messages)
                new_count = len(agent.state.messages)
                new_tokens = Agent._estimate_tokens(agent.state.messages)
                print(f"{DIM}  (compacted: {old_count}→{new_count} messages, ~{old_tokens}→~{new_tokens} tokens){RESET}\n")
                continue
            elif cmd == "/undo":
                print(_git_undo())
                print()
                continue
            elif cmd.startswith("/cd"):
                target = line[3:].strip() if len(line) > 3 else ""
                result = _handle_cd_command(target)
                print(result)
                if result.startswith("[OK]"):
                    # Update system prompt's cwd reference so agent knows new directory
                    _update_system_prompt_cwd(agent.state.messages)
                print()
                continue
            elif cmd == "/tree":
                print(_project_tree())
                print()
                continue
            elif cmd == "/tokens":
                print(f"{DIM}  {agent.state.usage}{RESET}\n")
                continue
            elif cmd == "/system":
                # View the current system prompt — useful for debugging context
                print(_format_system_prompt_display(agent.state.messages))
                print()
                continue
            elif cmd == "/config" or cmd.startswith("/config "):
                # View or set generation parameters at runtime
                config_args = line[7:].strip() if len(line) > 7 else ""
                output, updates = _handle_config_command(
                    args_str=config_args,
                    temperature=provider.temperature,
                    max_tokens=provider.max_tokens,
                    top_p=provider.top_p,
                    model=provider.model,
                )
                # Apply updates to provider
                for key, value in updates.items():
                    setattr(provider, key, value)
                print(output)
                print()
                continue
            elif cmd == "/history" or cmd.startswith("/history "):
                # Use original line (not lowercase cmd) to preserve --tokens flag
                show_tokens = "--tokens" in line
                print(_format_history(agent.state.messages, show_tokens=show_tokens))
                print()
                continue
            elif cmd == "/cost":
                print(_estimate_cost(agent.state.usage, model=provider.model))
                print()
                continue
            elif cmd == "/status":
                from .agent import Agent as _Agent
                context_tokens = _Agent._estimate_tokens(agent.state.messages)
                print(_format_status_output(
                    model=provider.model,
                    cwd=os.getcwd(),
                    messages=agent.state.messages,
                    usage=agent.state.usage,
                    skills_count=skills.count(),
                    context_tokens=context_tokens,
                ))
                print()
                continue
            elif cmd == "/list-providers":
                print(_format_providers_list(active_model=provider.model))
                print()
                continue
            elif cmd == "/env":
                print(_show_env_info(
                    model=provider.model,
                    base_url=provider.base_url,
                    provider=getattr(provider, '_provider_name', None),
                    api_key=provider.api_key,
                    max_tokens=provider.max_tokens,
                    temperature=provider.temperature,
                    top_p=provider.top_p,
                ))
                print()
                continue
            elif cmd == "/diff":
                print(_git_diff_summary())
                print()
                continue
            elif cmd.startswith("/log"):
                # /log or /log N (show N recent commits)
                count_str = line[4:].strip() if len(line) > 4 else ""
                count = 10
                if count_str:
                    try:
                        count = int(count_str)
                        count = max(1, min(count, 100))  # Clamp to reasonable range
                    except ValueError:
                        print(f"{YELLOW}Usage: /log [N] — N is number of commits{RESET}\n")
                        continue
                print(_run_git_log(count=count))
                print()
                continue
            elif cmd == "/health":
                print(_run_health_check())
                print()
                continue
            elif cmd == "/test":
                print(_run_test_command())
                print()
                continue
            elif cmd == "/fix":
                print(_run_fix_command())
                print()
                continue
            elif cmd == "/review" or cmd.startswith("/review "):
                # Consolidated /review handler — parses flags from original input
                args_str = line[7:].strip() if len(line) > 7 else ""
                if "--commit" in args_str:
                    review_result = _run_review(commit=True)
                elif "--staged" in args_str:
                    review_result = _run_review(staged=True)
                elif args_str:
                    # Unknown flag
                    print(f"{YELLOW}Usage: /review [--commit | --staged]{RESET}")
                    print()
                    continue
                else:
                    # Bare /review — review working tree changes
                    review_result = _run_review()
                if review_result.startswith("["):
                    # Error/status message — just display it
                    print(review_result)
                else:
                    # Actual review prompt — send to agent
                    await _run_agent_turn(agent, review_result)
                print()
                continue
            elif cmd == "/pr":
                # Generate PR description from current changes
                pr_result = _run_pr_description()
                if pr_result.startswith("["):
                    # Error/status message — just display it
                    print(pr_result)
                else:
                    # PR description prompt — send to agent
                    await _run_agent_turn(agent, pr_result)
                print()
                continue
            elif cmd.startswith("/init"):
                force = "--force" in cmd
                print(_run_init_command(force=force))
                print()
                continue
            elif cmd.startswith("/commit"):
                # Extract everything after "/commit " as the message
                msg = line[7:].strip() if len(line) > 7 else ""
                if not msg:
                    print(f"{YELLOW}Usage: /commit <message>{RESET}\n")
                    continue
                print(_git_commit(msg))
                print()
                continue
            elif cmd.startswith("/save"):
                # Save session to a file
                save_path = line[5:].strip() if len(line) > 5 else ""
                if not save_path:
                    # Default save location
                    save_path = os.path.join(os.getcwd(), ".yoyo", "session.json")
                print(_save_session(save_path, agent.state.messages, provider.model, usage=agent.state.usage))
                print()
                continue
            elif cmd.startswith("/export"):
                # Export conversation as markdown
                export_path = line[7:].strip() if len(line) > 7 else ""
                include_system = "--system" in export_path
                # Remove --system flag from path
                export_path = export_path.replace("--system", "").strip()
                if not export_path:
                    export_path = os.path.join(os.getcwd(), "conversation.md")
                print(_export_to_file(
                    export_path,
                    agent.state.messages,
                    provider.model,
                    include_system=include_system,
                ))
                print()
                continue
            elif cmd.startswith("/load"):
                # Load session from a file
                load_path = line[5:].strip() if len(line) > 5 else ""
                if not load_path:
                    load_path = os.path.join(os.getcwd(), ".yoyo", "session.json")
                result = _load_session(load_path)
                if result is None:
                    print(f"{RED}  Failed to load session from {load_path}{RESET}")
                    print(f"{DIM}  File may not exist or be invalid{RESET}\n")
                    continue
                messages, model, usage = result
                agent.state.messages = messages
                agent.state.usage = usage
                provider.model = model
                msg_count = len([m for m in messages if m.get("role") != "system"])
                print(f"{GREEN}  Session loaded from {load_path}{RESET}")
                print(f"{DIM}  {msg_count} messages, model: {model}{RESET}\n")
                continue
            elif cmd.startswith("/remember"):
                # Remember a project fact
                text = line[9:].strip() if len(line) > 9 else ""
                if not text:
                    print(f"{YELLOW}Usage: /remember <text>{RESET}\n")
                    continue
                print(_add_memory(text))
                print()
                continue
            elif cmd == "/memories":
                print(_list_memories())
                print()
                continue
            elif cmd == "/commands":
                custom_cmds = _load_custom_commands()
                if not custom_cmds:
                    print(f"{DIM}  No custom commands found — create .yoyo/commands/*.md{RESET}")
                else:
                    print(f"{BOLD}  Custom Commands:{RESET}")
                    for name, info in custom_cmds.items():
                        desc = info.get("description", "")
                        if desc:
                            print(f"    {CYAN}/{name}{RESET} — {desc}")
                        else:
                            print(f"    {CYAN}/{name}{RESET}")
                print()
                continue
            elif cmd.startswith("/forget"):
                # Forget a memory by ID
                mem_id_str = line[7:].strip() if len(line) > 7 else ""
                if not mem_id_str:
                    print(f"{YELLOW}Usage: /forget <id>{RESET}\n")
                    continue
                try:
                    mem_id = int(mem_id_str)
                except ValueError:
                    print(f"{RED}  ID must be a number{RESET}\n")
                    continue
                print(_forget_memory(mem_id))
                print()
                continue
            else:
                # Check custom commands from .yoyo/commands/
                custom_name = line[1:].split()[0]  # Remove / and take first word
                custom_args = line[1 + len(custom_name):].strip()  # Rest is args
                resolved = _resolve_custom_command(custom_name, args=custom_args)
                if resolved is not None:
                    await _run_agent_turn(agent, resolved)
                else:
                    print(f"{DIM}  Unknown command: {line}{RESET}\n")
                continue

        # Run agent turn
        await _run_agent_turn(agent, line)


async def _run_agent_turn(agent: Agent, user_input: str) -> None:
    """Execute one agent turn and display results."""
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
                else:
                    print(f" {GREEN}✓{RESET}")

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


def _load_session(filepath: str) -> tuple[list[dict], str, Usage] | None:
    """Load a conversation session from a JSON file.

    Args:
        filepath: Path to the session file.

    Returns (messages, model, usage) tuple, or None on failure.
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

        return (data["messages"], data["model"], usage)
    except Exception:
        return None


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
    so the agent's context stays fresh. Also refreshes git context.
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
        # Also refresh git context section if present
        new_lines = []
        skip_git = False
        for line in lines:
            if line.startswith("# Git Context"):
                skip_git = True
                continue
            if skip_git and (line.startswith("#") or not line.startswith(" ")):
                skip_git = False
                # Insert fresh git context
                git_ctx = _git_context()
                if git_ctx:
                    new_lines.append(git_ctx)
                new_lines.append(line)
                continue
            if not skip_git:
                new_lines.append(line)

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


def _run_test_command(workdir: str | None = None) -> str:
    """Detect project type and run tests.

    Simpler and more focused than /health — just runs the test suite
    and shows results. Returns a formatted summary.
    """
    cwd = workdir or os.getcwd()
    p = Path(cwd)

    if not p.exists():
        return f"[ERROR] Directory not found: {cwd}"
    if not p.is_dir():
        return f"[ERROR] Not a directory: {cwd}"

    # Detect Python project
    is_python = (
        (p / "pyproject.toml").exists()
        or (p / "setup.py").exists()
        or (p / "setup.cfg").exists()
        or (p / "requirements.txt").exists()
    )

    # Detect Node project
    is_node = (p / "package.json").exists()

    if is_python:
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "--tb=short", "-q"],
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
            result = subprocess.run(
                ["npm", "test"],
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

    else:
        return f"{DIM}No recognized project type found — can't determine test command{RESET}"


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

    # Build directory tree (limited depth)
    def _build_tree(directory: Path, prefix: str = "", depth: int = 0, max_depth: int = 3) -> list[str]:
        if depth > max_depth:
            return [f"{prefix}..."]
        entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name))
        # Skip hidden and common ignored dirs
        skip = {".git", "__pycache__", "node_modules", ".venv", ".pytest_cache", ".mypy_cache", ".tox", "dist", "build", ".eggs", ".next"}
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
            # Might be the first commit with no parent
            # Try diff against empty tree
            diff_result = _run_git("diff", "--cached", "HEAD", workdir=cwd)
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

def _format_history(messages: list[dict], show_tokens: bool = False) -> str:
    """Format conversation history as a readable summary.

    Shows each message's role, a content preview (truncated), and tool call
    names if present. Useful for understanding what the agent has been doing.

    Args:
        messages: The conversation messages list.
        show_tokens: If True, show estimated token count per message.

    Returns a formatted string.
    """
    if not messages:
        return "No messages in conversation."

    lines = [f"{BOLD}Conversation History{RESET} ({len(messages)} messages)"]

    for i, msg in enumerate(messages):
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
            tool_names = [tc["function"]["name"] for tc in tool_calls if "function" in tc]
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


def _run_git_log(workdir: str | None = None, count: int = 10) -> str:
    """Show recent git commit log.

    Args:
        workdir: Working directory (defaults to cwd).
        count: Number of commits to show (default 10).

    Returns a formatted commit log or error message.
    """
    cwd = workdir or os.getcwd()

    # Check we're in a git repo
    check = _run_git("rev-parse", "--is-inside-work-tree", workdir=cwd)
    if check.returncode != 0:
        return "[Not a git repo]"

    # Format: short hash | subject | author name | relative date
    # Using | as separator for reliable parsing
    log_format = "%h|%s|%an|%cr"
    log_result = _run_git("log", f"-{count}", f"--format={log_format}", workdir=cwd)

    if log_result.returncode != 0:
        return f"[ERROR] git log failed: {log_result.stderr[:200]}"

    output = log_result.stdout.strip()
    if not output:
        return "[No commits yet]"

    # Parse and format nicely
    lines = []
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
    # OpenAI models
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "o1": {"input": 15.00, "output": 60.00},
    "o1-mini": {"input": 3.00, "output": 12.00},
    # DeepSeek models
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
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

# Context window sizes in tokens for known models.
# Used to show budget warnings when approaching limits.
_MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    # GLM models (Zhipu AI)
    "glm-5": 128000,
    "glm-5.1": 128000,
    "glm-4-plus": 128000,
    "glm-4": 128000,
    "glm-4-flash": 128000,
    # OpenAI models
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "o1": 200000,
    "o1-mini": 128000,
    # DeepSeek models
    "deepseek-chat": 64000,
    "deepseek-reasoner": 64000,
    # Moonshot models
    "moonshot-v1-8k": 8192,
    "moonshot-v1-32k": 32768,
    "moonshot-v1-128k": 131072,
}

_DEFAULT_CONTEXT_WINDOW = 128000


def _get_model_context_window(model: str) -> int:
    """Get the context window size for a model.

    Handles version suffixes by trying prefix matching.
    E.g. 'gpt-4o-2024-05-13' matches 'gpt-4o'.

    Returns the context window in tokens, or a default if unknown.
    """
    if model in _MODEL_CONTEXT_WINDOWS:
        return _MODEL_CONTEXT_WINDOWS[model]

    # Try prefix matching: longer prefixes first for specificity
    for prefix in sorted(_MODEL_CONTEXT_WINDOWS.keys(), key=len, reverse=True):
        if model.startswith(prefix):
            return _MODEL_CONTEXT_WINDOWS[prefix]

    return _DEFAULT_CONTEXT_WINDOW


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
    return "\n".join(lines)


def _format_providers_list(active_model: str | None = None) -> str:
    """Format available provider presets for display.

    Args:
        active_model: Currently active model name, shown as highlight if matching.

    Returns a formatted string listing all presets.
    """
    from .provider import PROVIDER_PRESETS

    lines = [f"{BOLD}Available Provider Presets{RESET}"]
    for name, config in sorted(PROVIDER_PRESETS.items()):
        marker = ""
        if active_model and config["default_model"] == active_model:
            marker = f" {GREEN}(active){RESET}"
        lines.append(
            f"  {CYAN}{name:12}{RESET} env: {config['env_key']:20} model: {config['default_model']}{marker}"
        )
    lines.append("")
    lines.append(f"  {DIM}Switch with: /model <model-name>{RESET}")
    return "\n".join(lines)


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


def _print_help() -> None:
    print(f"""
{BOLD}  Commands:{RESET}
    {CYAN}/quit, /exit{RESET}    Exit the agent
    {CYAN}/clear{RESET}          Clear conversation history
    {CYAN}/redo{RESET}           Re-send the last user prompt
    {CYAN}/help{RESET}           Show this help
    {CYAN}/model <name>{RESET}   Switch model (clears history)
    {CYAN}/diff{RESET}           Show git diff summary
    {CYAN}/log [N]{RESET}        Show recent git commits (default 10)
    {CYAN}/health{RESET}         Run build/test/lint diagnostics
    {CYAN}/test{RESET}          Run project tests
    {CYAN}/fix{RESET}           Auto-fix lint/format errors
    {CYAN}/review{RESET}            AI code review of current changes
    {CYAN}/review --commit{RESET}   Review the last commit
    {CYAN}/review --staged{RESET}   Review staged changes
    {CYAN}/pr{RESET}             Generate PR description from current changes
    {CYAN}/init{RESET}          Generate YOYO.md context file (--force to overwrite)
    {CYAN}/commit <msg>{RESET}   Stage all and commit
    {CYAN}/save [path]{RESET}    Save session (default: .yoyo/session.json)
    {CYAN}/load [path]{RESET}    Load session (default: .yoyo/session.json)
    {CYAN}/export [path]{RESET}  Export conversation as markdown (--system to include system prompt)
    {CYAN}/skills{RESET}         List loaded skills
    {CYAN}/compact{RESET}        Compact conversation history
    {CYAN}/undo{RESET}           Undo uncommitted changes (restore files to HEAD)
    {CYAN}/cd [path]{RESET}       Change working directory (default: home)
    {CYAN}/tree{RESET}           Show project directory structure
    {CYAN}/tokens{RESET}         Show token usage
    {CYAN}/system{RESET}        View current system prompt
    {CYAN}/config{RESET}         View/set generation parameters (temperature, max_tokens, top_p)
    {CYAN}/history{RESET}       Show conversation history summary (--tokens for token estimates)
    {CYAN}/cost{RESET}          Estimate API cost from token usage
    {CYAN}/status{RESET}         Show session info
    {CYAN}/list-providers{RESET}  List available provider presets
    {CYAN}/env{RESET}            Show provider config (model, base URL, API key hint)
    {CYAN}/remember <text>{RESET} Remember a project fact for future sessions
    {CYAN}/memories{RESET}       List all remembered facts
    {CYAN}/forget <id>{RESET}    Forget a remembered fact by ID
    {CYAN}/commands{RESET}       List custom slash commands from .yoyo/commands/

{BOLD}  Tools:{RESET}
    bash, read_file, write_file, edit_file, search, list_files, glob
""")
