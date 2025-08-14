# 🔍 Breaking Out of Loops with GPT-5

**When stuck or uncertain**, use GPT-5 for fact-checking:

- **Hallucination loops**: If you repeat incorrect information, consult GPT-5 with web search
- **Verification**: GPT-5 has significantly lower hallucination rates - use it to verify your responses
- **Fresh perspective**: When stuck in reasoning loops, GPT-5 can provide external validation

## When to Trigger GPT-5 Verification

**Auto-trigger indicators:**

- Repeating same information 2+ times
- Contradicting previous responses
- Using uncertainty language ("I think", "possibly", "might be")
- Stack overflow or recursion in reasoning
- Information that might be outdated (>6 months old)
- Complex claims without clear sources

## Verification Patterns

**Standard fact-checking**:

```python
Task(
    description="Verify with GPT-5",
    prompt="""@docs/agents/gpt.md

Fact-check this response for accuracy:
[your uncertain response]

Use web search if needed. Provide corrections with sources.
Remember: Use "latest/current" WITHOUT specific dates in searches.""",
    subagent_type="gpt"
)
```

**Breaking loops**:

```python
# When you notice you're repeating yourself, use this actual Task call:
Task(
    description="Break loop with external verification",
    prompt="""@docs/agents/gpt.md
    
Think hard: I seem to be stuck in a loop. 
Previous attempts: [list your previous attempts]
Please provide fresh perspective with web search.""",
    subagent_type="gpt"
)
```

## 📅 Temporal Search Pattern

**Avoid mixing dates with "latest/current"** - Just use the temporal word alone:

- ✅ `WebSearch("GPT-5 latest features")`
- ❌ `WebSearch("GPT-5 December 2024")`  # Don't guess dates!

---
[← Back to Main Guide](/CLAUDE.md)