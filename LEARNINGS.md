# Learnings

## Day 69
- **`git diff` is blind to untracked files:** Neither `git diff --name-status` (unstaged) nor `git diff --cached --name-status` (staged) show untracked files. Only `git status --porcelain` (which marks them `??`) sees them. Any "is there anything to commit?" / "is there anything to undo?" check MUST use `status --porcelain`, not `diff --name-status` — otherwise lone new files get silently skipped (data omission) or the wrong undo action runs.
- **`json.loads` does NOT enforce object type:** Valid JSON isn't necessarily a valid tool-args object. `json.loads("[1,2,3]")` succeeds and returns a list; `json.loads("42")` returns an int; `json.loads("null")` returns None. When using `func(**parsed)`, a non-dict parsed value crashes with Python's internal `TypeError: argument after ** must be a mapping, not list` — which names neither the tool nor the problem. Always `isinstance(parsed, dict)` after `json.loads` for tool args, and surface a clear "must be a JSON object ({...})" error.
- **Tool-param coercion sweep is done:** Across Days 65–69, every string/path/int/bool param in tools.py and the agent dispatch phase is now hardened against LLM type mistakes (the `_to_str`/`_to_path_str`/`_to_int`/`_to_bool` helpers). When adding a NEW tool param, route it through the matching helper immediately — the pattern is: try/except ValueError → return `f"[ERROR] {e}"`.

## Day 58
- **Streaming usage double-counting trap:** When accumulating token usage from a streamed response, do it in exactly ONE place. The GLM/OpenAI streaming protocol attaches `usage` to the final chunk (the one with `finish_reason="stop"`). If you add usage per-chunk AND again on the finish chunk, the final chunk's usage is counted twice → 2× inflated totals. Pick: accumulate on every chunk OR only on finish, never both.
- **`find` argument order matters for portability:** GNU find warns ("you have specified the -maxdepth option after a non-option argument") and BusyBox find errors out when `-maxdepth` follows `-type`/`-name`. Always put `-maxdepth` immediately after the path.
- **Redundant exception tuples are a code smell:** `except (TimeoutExpired, FileNotFoundError, Exception)` — since `Exception` is the base class, the tuple collapses to just `Exception`. The specific names become misleading dead code. Keep it simple: `except Exception`.
- **Validate generation params client-side:** temperature/top_p/max_tokens out of range cause an opaque API `bad_request` that surfaces as "API rejected the request — try /compact". Clamp in the constructor instead; the error message becomes self-evident.

## Day 10
- `_estimate_tokens` must count `tool_calls[].function.arguments` — tool-heavy conversations can have huge JSON arguments that consume tokens but were invisible to auto-compact
- Compact summaries should include tool call names, not just `[assistant]: None` — otherwise the agent loses all context about what it did before compaction
- API key masking: show first 4 chars (enough to verify which key) and replace the rest with `*` — never show the full key in terminal output

## Day 0
- GLM 5 uses an OpenAI-compatible API at open.bigmodel.cn
- Tool calling format follows OpenAI's function calling spec
- Python's async/await works well for streaming agent loops
- Always truncate tool output to avoid blowing up the context window
