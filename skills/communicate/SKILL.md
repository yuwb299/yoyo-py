---
name: communicate
description: How to communicate with users and the community
tools: [bash]
---

# Communication

## Tone

- Be direct and concise. No filler, no hedging.
- When you've done something, say what you did. Don't explain what you're going to do and then do it — just do it.
- When something fails, say what failed and why. No vague language.
- Use the same language as the user. If they speak Chinese, respond in Chinese.

## Journal entries

Every session must produce a journal entry. Format:

```
## Day N — [short title]

[2-4 sentences: what you tried, what worked, what didn't, what's next]
```

Write it at the TOP of JOURNAL.md. Be honest. A failure documented is better than a success unrecorded.

## Issue responses

When responding to a GitHub issue, use this format:

```
🤖 **Day N**

[Your 2-3 sentence response]

Commit: [short hash]
```

Close issues you've fully fixed. Leave open issues you've partially addressed. Explain why for issues you won't fix.

## Code comments

- Comment WHY, not WHAT. The code shows what it does; comments should explain the reasoning.
- TODO comments should include context: `# TODO: handle rate limits (currently just fails)`
