"""Interactive REPL — the terminal interface for yoyo-py."""

from __future__ import annotations

import asyncio
import os
import sys

from .agent import Agent, AgentEvent
from .provider import GLMProvider
from .tools import TOOL_FUNCTIONS, TOOL_SCHEMAS
from .skills import SkillSet

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
    print(f"\n{BOLD}{CYAN}  yoyo-py{RESET} {DIM}— a self-evolving coding agent (Python + GLM 5){RESET}")
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
    ]

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
            line = input(f"{BOLD}{GREEN}> {RESET}")
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


def _truncate_str(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len] + "..."


def _print_help() -> None:
    print(f"""
{BOLD}  Commands:{RESET}
    {CYAN}/quit, /exit{RESET}    Exit the agent
    {CYAN}/clear{RESET}          Clear conversation history
    {CYAN}/help{RESET}           Show this help
    {CYAN}/model <name>{RESET}   Switch model (clears history)
    {CYAN}/skills{RESET}         List loaded skills
    {CYAN}/tokens{RESET}         Show token usage
    {CYAN}/status{RESET}         Show session info

{BOLD}  Tools:{RESET}
    bash, read_file, write_file, edit_file, search, list_files
""")
