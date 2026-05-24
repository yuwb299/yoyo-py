"""Interactive REPL — the terminal interface for yoyo-py."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

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
    parts = [
        "You are a coding assistant working in the user's terminal.",
        "You have access to the filesystem and shell. Be direct and concise.",
        "When the user asks you to do something, do it — don't just explain how.",
        "Use tools proactively: read files to understand context, run commands to verify your work.",
        "After making changes, run tests or verify the result when appropriate.",
        "You respond in the same language the user uses.",
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


async def run_repl(
    provider: GLMProvider,
    skill_dirs: list[str] | None = None,
    verbose: bool = False,
    initial_prompt: str | None = None,
    pipe_input: str | None = None,
) -> None:
    """Run the interactive REPL loop."""
    # Load skills
    skills = SkillSet()
    if skill_dirs:
        for d in skill_dirs:
            skills.load(d)

    system_prompt = load_system_prompt(skills)

    agent = Agent(
        provider=provider,
        system_prompt=system_prompt,
        tools=TOOL_FUNCTIONS,
        tool_schemas=TOOL_SCHEMAS,
        verbose=verbose,
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
            elif cmd == "/tree":
                print(_project_tree())
                print()
                continue
            elif cmd == "/tokens":
                print(f"{DIM}  {agent.state.usage}{RESET}\n")
                continue
            elif cmd == "/status":
                print(f"{DIM}  model: {provider.model}{RESET}")
                print(f"{DIM}  cwd:   {os.getcwd()}{RESET}")
                print(f"{DIM}  messages: {len(agent.state.messages)}{RESET}")
                print(f"{DIM}  tokens: {agent.state.usage}{RESET}")
                print(f"{DIM}  skills: {skills.count()}{RESET}\n")
                continue
            elif cmd == "/diff":
                print(_git_diff_summary())
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


def _git_context() -> str:
    """Collect git context for the system prompt: branch and recently changed files.

    Returns a formatted string for the system prompt, or empty string if not in a git repo.
    This helps the agent understand what files the user has been working on recently.
    """
    def _run_git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + list(args),
            capture_output=True,
            text=True,
            timeout=5,
        )

    # Check we're in a git repo
    check = _run_git("rev-parse", "--is-inside-work-tree")
    if check.returncode != 0:
        return ""

    # Get current branch name
    branch_result = _run_git("branch", "--show-current")
    if branch_result.returncode == 0 and branch_result.stdout.strip():
        branch = branch_result.stdout.strip()
    else:
        # Detached HEAD — show short commit hash instead
        head_result = _run_git("rev-parse", "--short", "HEAD")
        branch = head_result.stdout.strip() if head_result.returncode == 0 else "detached"

    # Get recently changed files (modified + untracked)
    changed_files = []
    diff_result = _run_git("diff", "--name-only")
    if diff_result.returncode == 0 and diff_result.stdout.strip():
        changed_files.extend(diff_result.stdout.strip().splitlines())

    # Staged changes too
    diff_cached = _run_git("diff", "--cached", "--name-only")
    if diff_cached.returncode == 0 and diff_cached.stdout.strip():
        for f in diff_cached.stdout.strip().splitlines():
            if f not in changed_files:
                changed_files.append(f)

    # Untracked files
    untracked = _run_git("ls-files", "--others", "--exclude-standard")
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

    def _run_git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + list(args),
            capture_output=True,
            text=True,
            timeout=10,
        )

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
    def _run_git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + list(args),
            capture_output=True,
            text=True,
            timeout=10,
        )

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

    def _run_git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + list(args),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=cwd,
        )

    # Check we're in a git repo
    check = _run_git("rev-parse", "--is-inside-work-tree")
    if check.returncode != 0:
        return "[ERROR] Not a git repo"

    # Check for any changes
    status = _run_git("status", "--porcelain")
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
        checkout = _run_git("checkout", "HEAD", "--", *reverted)
        if checkout.returncode != 0:
            return f"[ERROR] git checkout failed: {checkout.stderr.strip()}"

    # Remove untracked files
    if cleaned:
        clean = _run_git("clean", "-f", "--", *cleaned)
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


def _print_help() -> None:
    print(f"""
{BOLD}  Commands:{RESET}
    {CYAN}/quit, /exit{RESET}    Exit the agent
    {CYAN}/clear{RESET}          Clear conversation history
    {CYAN}/help{RESET}           Show this help
    {CYAN}/model <name>{RESET}   Switch model (clears history)
    {CYAN}/diff{RESET}           Show git diff summary
    {CYAN}/health{RESET}         Run build/test/lint diagnostics
    {CYAN}/test{RESET}          Run project tests
    {CYAN}/commit <msg>{RESET}   Stage all and commit
    {CYAN}/save [path]{RESET}    Save session (default: .yoyo/session.json)
    {CYAN}/load [path]{RESET}    Load session (default: .yoyo/session.json)
    {CYAN}/skills{RESET}         List loaded skills
    {CYAN}/compact{RESET}        Compact conversation history
    {CYAN}/undo{RESET}           Undo uncommitted changes (restore files to HEAD)
    {CYAN}/tree{RESET}           Show project directory structure
    {CYAN}/tokens{RESET}         Show token usage
    {CYAN}/status{RESET}         Show session info
    {CYAN}/remember <text>{RESET} Remember a project fact for future sessions
    {CYAN}/memories{RESET}       List all remembered facts
    {CYAN}/forget <id>{RESET}    Forget a remembered fact by ID

{BOLD}  Tools:{RESET}
    bash, read_file, write_file, edit_file, search, list_files
""")
