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
- [ ] `/fix` — auto-fix build/lint errors
- [ ] `/test` — detect project type and run tests
- [ ] `/init` — scan project and generate YOYO.md context file
- [x] `/tree` — project structure visualization (Day 4)
- [ ] Permission system (confirm before bash/write/edit)
- [ ] `--yes` flag to auto-approve all
- [ ] Project memory (`/remember`, `/memories`, `/forget`)

## Level 4: Mastery (Day 43–70)
- [ ] Multiple provider support (Anthropic, OpenAI, DeepSeek, etc.)
- [ ] Extended thinking / reasoning depth control
- [ ] `/review` — AI code review of changes
- [ ] `/pr` — full PR workflow
- [ ] Custom slash commands from `.yoyo/commands/`
- [ ] MCP server integration
- [ ] Subagent spawning for parallel tasks
- [ ] Provider failover on API failure

## Level 5: Evolution (Day 71+)
- [ ] Self-assessment skill: analyze own code quality
- [ ] Auto-evolution: read own source → plan → implement → test → commit
- [ ] GitHub Actions CI for automated evolution
- [ ] Issue tracking integration (read + respond to GitHub issues)
- [ ] Social learning from discussions
- [ ] Daily memory synthesis (compress old learnings)
- [ ] Skill evolution: create, refine, and retire own skills
