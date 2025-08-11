# ChatGPT Analysis Patterns

## GPT-5 Unified Model (August 2025)

GPT-5 on chatgpt.com uses a unified model with automatic routing. No manual model selection needed - just use prompt patterns to trigger the right capabilities.

## Prompt Patterns by Task

### Code Review
```python
# Standard review - auto-routes based on complexity
"Review this Odoo code for issues"

# Deep analysis - add "think hard" or "think step by step"
"Think hard: Analyze this complex business logic for edge cases"
```

### Architecture & Design
```python
# With web search for current best practices
"Search the web: Current best practices for Odoo 18 multi-tenant architecture"

# With reasoning for trade-offs
"Think step by step: Design a scalable inventory system considering [requirements]"
```

### Performance Analysis
```python
# Standard optimization
"Analyze this query for performance bottlenecks"

# Complex multi-system
"Think hard: Analyze performance across these interconnected systems"
```

### Development Tasks
```python
# Quick fixes
"Fix this Python error: [code]"

# Feature implementation
"Generate a complete Odoo model for [feature] with tests"

# Refactoring
"Refactor this code following Odoo 18 patterns"
```

### Fact-Checking & Verification
```python
# Verify information
"Fact-check with sources: [claim or response]"

# Current information
"Search the web: Latest Odoo 18 features and migration guide"

# Breaking loops
"Verify if this is correct: [potentially incorrect information]"
```

## Mode Triggers

| Intent | Prompt Pattern | Mode Activated |
|--------|---------------|----------------|
| Deep reasoning | "Think hard:", "Think step by step:" | Think longer mode |
| Current info | "Search the web:", "Latest", "Current" | Web search |
| Verification | "Fact-check:", "Verify with sources:" | Web search |
| Research | "Research best practices for" | Deep research (if complex) |

## Agent Collaboration Examples

### Debugger → GPT Flow
```python
Task(
    description="Deep error analysis",
    prompt="""@docs/agents/gpt.md

Think hard: Debug this complex issue
[error details from Debugger]

Focus on: root cause, similar issues, proven fixes""",
    subagent_type="gpt"
)
```

### Fact-Checking Claude
```python
Task(
    description="Verify response",
    prompt="""@docs/agents/gpt.md

Fact-check this response for accuracy:
[Claude's response]

Use web search if needed. Provide corrections with sources.""",
    subagent_type="gpt"
)
```

## Confidence-Based Routing

### When to Verify with GPT-5

**Uncertainty indicators that should trigger verification:**
- "I think..."
- "It might be..."
- "Possibly..."
- "Could be..."
- "If I remember correctly..."
- "I believe..."
- "Probably..."

**When Claude uses these phrases, verify with GPT:**
```python
# Example: When uncertain, route to GPT for verification
Task(
    description="Verify uncertain information",
    prompt="""@docs/agents/gpt.md
    
I'm uncertain about this claim: [your uncertain statement]
Please fact-check with web search and provide the correct information.""",
    subagent_type="gpt"
)
```

## Best Practices

### DO ✅
- Use natural language - GPT-5 understands intent
- Add "think hard" for complex reasoning
- Include "search the web" for current information
- Be specific about what you want verified
- Save important conversations
- Batch similar verifications together

### DON'T ❌
- Manually select models (auto-routing handles it)
- Worry about model tiers (nano/mini/full is automatic)
- Use Deep Research for simple queries (250/month quota)
- Ignore web search for time-sensitive info

## Error Recovery
- If response seems wrong → Ask to fact-check with web search
- If stuck in loop → Start new chat
- If timeout → Retry with longer timeout
- If confused → Be more specific in prompt