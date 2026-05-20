---
name: self-assess
description: Evaluate your own capabilities, find weaknesses, and plan improvements
tools: [bash, read_file, search]
---

# Self-Assessment

## How to assess yourself

Every evolution session starts with self-assessment. Here's how:

1. **Read your own source code.** Start with `src/agent.py` (your core loop), then `src/tools.py` (your capabilities), then `src/repl.py` (your interface).
2. **Try yourself.** Pick a small task and attempt it. Note any friction, errors, or missing capabilities.
3. **Check for known issues.** Read LEARNINGS.md for past problems. Search for TODO/FIXME/HACK comments in your source.
4. **Compare against the roadmap.** Read ROADMAP.md. What's the next item you should tackle?

## What to look for

- **Missing error handling.** What happens when the API returns an error? When a tool fails? When the user types garbage?
- **Missing features.** What would make you more useful? What do users of other coding agents expect?
- **Code quality.** Are there functions that are too long? Duplicate logic? Unclear names?
- **Test coverage.** Are there paths in your code that aren't tested?
- **Performance.** Are you slow in ways that matter? Unnecessary API calls? Redundant file reads?

## Priority order

1. Data loss or crash bugs (always fix first)
2. User-facing friction (things that make you annoying to use)
3. Missing error handling (things that break silently)
4. New features from roadmap
5. Code quality improvements
