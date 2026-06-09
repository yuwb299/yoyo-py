# Evolution Roadmap

## Level 1: Survival (Day 1–7)
- [x] Basic REPL with streaming output
- [x] 6 core tools (bash, read_file, write_file, edit_file, search, list_files)
- [x] GLM 5 provider via OpenAI-compatible API
- [x] Skills system with YAML frontmatter
- [x] Colored tool feedback
- [x] Add unit tests for all tools (Day 1)
- [x] Add integration test for agent loop (Day 1)
- [x] Graceful error handling (API errors, rate limits, timeouts) (Day 1)
- [x] Ctrl+C handling to interrupt agent responses

## Level 2: Awareness (Day 8–21)
- [x] Token usage tracking per turn and per session
- [x] `/model` command to switch models mid-session
- [x] `/status` command with model, git branch, tokens
- [x] `/diff` — show git diff summary (Day 2)
- [x] `/commit` — stage all and commit with message (Day 2, bug fixed Day 3)
- [x] Multi-line input support (backslash continuation) (Day 2)
- [x] Session save/load (`/save`, `/load`) (Day 3)
- [x] Auto-compact when context gets too long (Day 3)
- [x] Git-aware context (recently changed files in system prompt) (Day 3)
- [x] REPL tests (slash commands, pipe input, error display) (Day 4)
- [x] `/undo` — revert uncommitted changes to HEAD state (Day 4)

## Level 3: Competence (Day 22–42)
- [x] `/health` — run build/test/lint diagnostics (Day 5)
- [x] `/fix` — auto-fix build/lint errors (Day 5)
- [x] `/test` — detect project type and run tests (Day 5)
- [x] `/init` — scan project and generate YOYO.md context file (Day 5)
- [x] `/tree` — project structure visualization (Day 4)
- [x] Permission system (confirm before bash/write/edit) (Day 5)
- [x] `--yes` flag to auto-approve all (Day 5)
- [x] Project memory (`/remember`, `/memories`, `/forget`) (Day 5)

## Level 4: Mastery (Day 43–70)
- [x] Multiple provider support (Anthropic, OpenAI, DeepSeek, etc.) (Day 5)
- [x] Extended thinking / reasoning depth control (Day 30)
- [x] `/review` — AI code review of changes (Day 7)
- [x] `/pr` — full PR workflow (Day 11)
- [x] Custom slash commands from `.yoyo/commands/` (Day 5)
- [ ] MCP server integration
- [ ] Subagent spawning for parallel tasks
- [x] Provider failover on API failure (Day 5)
- [x] `/env` — show provider config with masked API key (Day 10)
- [x] `/redo` — re-send last user prompt (Day 14)
- [x] `/export` — export conversation as markdown (Day 14)
- [x] `/status` with context token estimate (Day 14)
- [x] Command registry — extensible slash command dispatch (Day 29)

- [x] Auto-save conversation on exit (Day 20)
- [x] Tool output preview in REPL (Day 20)

## Level 5: Evolution (Day 71+)
- [x] Self-assessment skill: analyze own code quality (Day 45, /selfassess command)
- [ ] Auto-evolution: read own source → plan → implement → test → commit
- [ ] GitHub Actions CI for automated evolution
- [ ] Issue tracking integration (read + respond to GitHub issues)
- [ ] Social learning from discussions
- [ ] Daily memory synthesis (compress old learnings)
- [ ] Skill evolution: create, refine, and retire own skills
