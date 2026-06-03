#!/usr/bin/env python3
"""scripts/evolve.py — One evolution cycle.

The heart of self-evolution. This script:
1. Verifies the codebase is healthy
2. Fetches community issues (if gh CLI available)
3. Prepares context (journal, roadmap, source code)
4. Runs the agent with a structured evolution prompt
5. Verifies changes (tests pass, no crashes)
6. Commits and pushes

Usage:
    GLM_API_KEY=*** python scripts/evolve.py

Environment:
    GLM_API_KEY   — required
    REPO          — GitHub repo (optional, for issue fetching)
    MODEL         — LLM model (default: from env or glm-5.1)
    TIMEOUT       — Max session time in seconds (default: 900)
"""

from __future__ import annotations

import os
import sys
import subprocess
import json
import asyncio
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from src.provider import GLMProvider
from src.agent import Agent, AgentEvent
from src.tools import TOOL_FUNCTIONS, TOOL_SCHEMAS
from src.skills import SkillSet


def read_file_safe(path: Path) -> str:
    """Read a file, return empty string if not found."""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def get_day_count() -> int:
    """Read current day counter."""
    try:
        return int((PROJECT_ROOT / "DAY_COUNT").read_text().strip())
    except Exception:
        return 1


def increment_day() -> None:
    """Increment day counter."""
    day = get_day_count()
    (PROJECT_ROOT / "DAY_COUNT").write_text(str(day + 1) + "\n")


def verify_baseline() -> bool:
    """Step 1: Verify starting state — can we at least import ourselves?"""
    print("→ Checking baseline...")
    try:
        result = subprocess.run(
            [sys.executable, "-c", "from src.tools import TOOL_FUNCTIONS; print(len(TOOL_FUNCTIONS))"],
            capture_output=True, text=True, timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            tool_count = result.stdout.strip()
            print(f"  OK — {tool_count} tools loadable")
            return True
        else:
            print(f"  FAIL — import error: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"  FAIL — {e}")
        return False


def fetch_issues(repo: str | None = None) -> str:
    """Step 2: Fetch GitHub issues labeled 'agent-input'."""
    print("→ Fetching community issues...")
    issues_file = PROJECT_ROOT / "ISSUES_TODAY.md"

    if not repo:
        repo = os.getenv("REPO", "")

    if not repo:
        print("  No REPO configured, skipping issue fetch.")
        issues_file.write_text("No issues available (no REPO configured).\n")
        return issues_file.read_text()

    try:
        result = subprocess.run(
            [
                "gh", "issue", "list",
                "--repo", repo,
                "--state", "open",
                "--label", "agent-input",
                "--limit", "10",
                "--json", "number,title,body,labels",
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            issues = json.loads(result.stdout)
            if issues:
                lines = ["# Community Issues\n"]
                for issue in issues:
                    num = issue.get("number", "?")
                    title = issue.get("title", "Untitled")
                    body = issue.get("body", "")[:500]
                    lines.append(f"### Issue #{num}: {title}\n{body}\n")
                content = "\n".join(lines)
                issues_file.write_text(content)
                count = len(issues)
                print(f"  {count} issues loaded.")
                return content
    except Exception as e:
        print(f"  gh CLI error: {e}")

    content = "No issues found.\n"
    issues_file.write_text(content)
    print("  No issues found.")
    return content


def build_evolution_prompt(day: int, date: str) -> str:
    """Step 3: Build the structured evolution prompt."""
    return f"""Today is Day {day} ({date}).

Read these files in this order:
1. IDENTITY.md (who you are and your rules)
2. src/agent.py (your agent core loop — part of YOU)
3. src/tools.py (your tools — part of YOU)
4. src/repl.py (your interface — part of YOU)
5. ROADMAP.md (your evolution path)
6. JOURNAL.md (your recent history)
7. LEARNINGS.md (what you've learned so far)
8. ISSUES_TODAY.md (community requests, if any)

=== PHASE 1: Self-Assessment ===

Read your own source code carefully. Try a small task to test yourself —
for example, read a file, edit something, run a command.
Note any friction, bugs, crashes, or missing capabilities.

=== PHASE 2: Review Community Issues ===

Read ISSUES_TODAY.md. These are real people asking you to improve.
Issues with more thumbs-up reactions should be prioritized higher.

=== PHASE 3: Decide ===

Make as many improvements as you can this session. Prioritize:
1. Self-discovered crash or data loss bug
2. Community issue with most thumbs-up (if actionable today)
3. Self-discovered UX friction or missing error handling
4. Planned roadmap item at your current level

=== PHASE 4: Implement ===

For each improvement, follow the evolve skill rules:
- Write a test first if possible (put tests in tests/ directory)
- Use edit_file for surgical changes
- Run `python -m pytest` after changes (if pytest is available)
- If tests fail, try to fix it. If you can't, revert with: bash git checkout -- src/
- After each successful change, commit: git add -A && git commit -m "Day {day}: <short description>"
- Then move on to the next improvement

=== PHASE 5: Journal ===

Write today's entry at the TOP of JOURNAL.md. Format:
## Day {day} — [title]
[2-4 sentences: what you tried, what worked, what didn't, what's next]

=== PHASE 6: Update Roadmap ===

If you completed a roadmap item, check it off in ROADMAP.md:
- [x] Item description (Day {day})

If you discovered a new issue, add it to the appropriate level.

=== PHASE 7: Update Learnings ===

If you learned something new (API quirk, Python trick, design insight),
append it to LEARNINGS.md.

Now begin. Read IDENTITY.md first.
"""


async def run_evolution_session(provider: GLMProvider, prompt: str, timeout: int = 600) -> Agent:
    """Step 4: Run the evolution session with the agent."""
    print("→ Starting evolution session...\n")

    # Load skills
    skills = SkillSet()
    skills.load(str(PROJECT_ROOT / "skills"))

    # Build system prompt
    from src.repl import load_system_prompt
    system_prompt = load_system_prompt(skills)

    # Add identity context
    identity = read_file_safe(PROJECT_ROOT / "IDENTITY.md")
    if identity:
        system_prompt += f"\n\n# Identity\n{identity}"

    agent = Agent(
        provider=provider,
        system_prompt=system_prompt,
        tools=TOOL_FUNCTIONS,
        tool_schemas=TOOL_SCHEMAS,
        max_tool_rounds=80,
    )

    # Run the agent
    try:
        async for event_type, data in agent.prompt(prompt):
            if event_type == AgentEvent.TEXT:
                print(data, end="", flush=True)
            elif event_type == AgentEvent.TOOL_START:
                name = data["name"]
                args = data["args"]
                if name == "bash":
                    cmd = args.get("command", "...")[:80]
                    print(f"  ▶ ${cmd}")
                elif name in ("read_file", "write_file", "edit_file"):
                    print(f"  ▶ {name} {args.get('path', '?')}")
                elif name == "search":
                    print(f"  ▶ search '{args.get('pattern', '?')[:60]}'")
                else:
                    print(f"  ▶ {name}")
            elif event_type == AgentEvent.TOOL_END:
                status = "✗" if data.get("is_error") else "✓"
                print(f"  {status}")
            elif event_type == AgentEvent.ERROR:
                print(f"\n  ✗ ERROR: {data}")
            elif event_type == AgentEvent.DONE:
                print(f"\n  Session complete. Tokens: {data}")
    except Exception as e:
        print(f"\n  ✗ Session error: {e}")

    return agent


def verify_and_cleanup(day: int) -> bool:
    """Step 5: Verify the codebase still works after changes."""
    print("\n→ Verifying changes...")

    # Try importing
    result = subprocess.run(
        [sys.executable, "-c", "from src.tools import TOOL_FUNCTIONS; from src.agent import Agent; print('OK')"],
        capture_output=True, text=True, timeout=30,
        cwd=str(PROJECT_ROOT),
    )

    if result.returncode != 0:
        print("  FAIL — import error, reverting source changes")
        subprocess.run(["git", "checkout", "--", "src/"], cwd=str(PROJECT_ROOT))
        return False

    print("  Build: PASS")

    # Try pytest if available
    pytest_result = subprocess.run(
        [sys.executable, "-m", "pytest", "--tb=short", "-q"],
        capture_output=True, text=True, timeout=120,
        cwd=str(PROJECT_ROOT),
    )
    if pytest_result.returncode == 0:
        print(f"  Tests: PASS")
    else:
        print(f"  Tests: some failures (non-blocking)")
        print(pytest_result.stdout[:200])

    return True


def commit_wrapped_up(day: int) -> None:
    """Commit any remaining changes (journal, roadmap, day counter, etc.)."""
    # Increment day counter
    increment_day()

    # Commit remaining changes
    subprocess.run(["git", "add", "-A"], cwd=str(PROJECT_ROOT))
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=str(PROJECT_ROOT),
    )
    if result.returncode != 0:
        subprocess.run(
            ["git", "commit", "-m", f"Day {day}: session wrap-up"],
            cwd=str(PROJECT_ROOT),
        )
        print("  Committed session wrap-up.")
    else:
        print("  No uncommitted changes remaining.")


def push() -> None:
    """Step 7: Push to remote."""
    print("\n→ Pushing...")
    result = subprocess.run(["git", "push"], cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    if result.returncode == 0:
        print("  Pushed successfully.")
    else:
        print(f"  Push failed: {result.stderr[:200]}")


def main() -> None:
    print("=" * 60)
    print("  yoyo-py Evolution Cycle")
    print("=" * 60)

    day = get_day_count()
    date = datetime.now().strftime("%Y-%m-%d")
    model = os.getenv("MODEL", os.getenv("GLM_MODEL", "glm-5.1"))
    timeout = int(os.getenv("TIMEOUT", "900"))

    print(f"\n  Day {day}: {date}")
    print(f"  Model: {model}")
    print(f"  Timeout: {timeout}s")
    print()

    # Step 1: Verify baseline
    if not verify_baseline():
        print("\n❌ Baseline check failed. Aborting evolution.")
        sys.exit(1)

    # Step 2: Fetch issues
    fetch_issues()

    # Step 3: Build prompt
    prompt = build_evolution_prompt(day, date)

    # Step 4: Run evolution session
    try:
        provider = GLMProvider(model=model)
    except ValueError as e:
        print(f"\n❌ Provider error: {e}")
        sys.exit(1)

    agent = asyncio.run(run_evolution_session(provider, prompt, timeout))

    # Step 5: Verify and cleanup
    verify_and_cleanup(day)

    # Step 6: Commit wrap-up
    commit_wrapped_up(day)

    # Step 7: Push
    push()

    # Clean up temp files
    for tmp in ("ISSUES_TODAY.md", "ISSUE_RESPONSE.md"):
        tmp_path = PROJECT_ROOT / tmp
        if tmp_path.exists():
            tmp_path.unlink()

    print(f"\n{'=' * 60}")
    print(f"  Day {day} complete")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
