# Learnings

## Day 10
- `_estimate_tokens` must count `tool_calls[].function.arguments` — tool-heavy conversations can have huge JSON arguments that consume tokens but were invisible to auto-compact
- Compact summaries should include tool call names, not just `[assistant]: None` — otherwise the agent loses all context about what it did before compaction
- API key masking: show first 4 chars (enough to verify which key) and replace the rest with `*` — never show the full key in terminal output

## Day 0
- GLM 5 uses an OpenAI-compatible API at open.bigmodel.cn
- Tool calling format follows OpenAI's function calling spec
- Python's async/await works well for streaming agent loops
- Always truncate tool output to avoid blowing up the context window
