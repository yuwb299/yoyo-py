# yoyo-py: A Self-Evolving Coding Agent (Python + GLM 5)

A Python reincarnation of [yoyo-evolve](https://github.com/yologdev/yoyo-evolve). Born as ~300 lines of Python, growing up in public.

**Zero human code in its future. One rule: evolve or die.**

## How It Works

```
Every evolution cycle, yoyo-py wakes up and:
    → Reads its own source code
    → Checks GitHub issues for community input (if configured)
    → Plans what to improve
    → Makes changes, runs tests
    → If tests pass → commit. If not → revert.
    → Pushes and goes back to sleep
```

## Quick Start

### 1. Install dependencies

```bash
cd yoyo-py
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure API key

```bash
cp .env.example .env
# Edit .env and add your GLM API key
```

### 3. Run the REPL

```bash
python -m src.main

# Or with a single prompt
python -m src.main -p "explain this codebase"

# Or pipe input
echo "list all Python files" | python -m src.main
```

### 4. Run an evolution cycle

```bash
GLM_API_KEY=your_key python scripts/evolve.py
```

## Architecture

```
yoyo-py/
├── src/
│   ├── agent.py       Agent core — tool-calling loop
│   ├── provider.py    GLM 5 API provider (OpenAI-compatible)
│   ├── tools.py       6 built-in tools (bash, read_file, write_file, edit_file, search, list_files)
│   ├── repl.py        Interactive REPL with slash commands
│   ├── skills.py      Skills loader (YAML frontmatter + Markdown)
│   └── main.py        Entry point + CLI args
├── skills/
│   ├── evolve/        Self-evolution rules
│   ├── self-assess/   Self-assessment methodology
│   └── communicate/   Communication style rules
├── scripts/
│   └── evolve.py      Evolution pipeline (7 phases)
├── tests/             44 unit tests
├── IDENTITY.md        "Constitution" — who I am and my rules
├── ROADMAP.md         Evolution path (5 levels)
├── JOURNAL.md         Daily evolution journal
└── LEARNINGS.md       Accumulated knowledge
```

## Tools

| Tool | What it does |
|------|-------------|
| `bash` | Run shell commands with timeout and working directory |
| `read_file` | Read files with line numbers, offset, and limit |
| `write_file` | Create or overwrite files |
| `edit_file` | Surgical text replacement (find & replace) |
| `search` | Regex search across files (ripgrep-powered) |
| `list_files` | Directory listing with sizes and glob filtering |

## REPL Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/quit`, `/exit` | Exit the agent |
| `/clear` | Clear conversation history |
| `/model <name>` | Switch model mid-session |
| `/skills` | List loaded skills |
| `/tokens` | Show token usage |
| `/status` | Show session info |

## Evolution Phases

Each evolution cycle runs through 7 phases:

1. **Self-Assessment** — Read own source code, find weaknesses
2. **Review Issues** — Check community requests
3. **Decide** — Prioritize what to work on
4. **Implement** — Write code, run tests, commit
5. **Journal** — Document what happened
6. **Update Roadmap** — Check off completed items
7. **Update Learnings** — Record new knowledge

## Test

```bash
python -m pytest tests/ -v
```

## License

MIT
