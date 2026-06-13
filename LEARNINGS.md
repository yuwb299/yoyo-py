# Learnings

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
