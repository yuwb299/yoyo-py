# Learnings

## Day 0
- GLM 5 uses an OpenAI-compatible API at open.bigmodel.cn
- Tool calling format follows OpenAI's function calling spec
- Python's async/await works well for streaming agent loops
- Always truncate tool output to avoid blowing up the context window
