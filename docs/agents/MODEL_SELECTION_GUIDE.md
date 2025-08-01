# Claude Code Model Selection Guide

## Overview

Claude Code agents can request specific AI models based on task complexity. This feature enables cost and performance optimization by matching the right model to each task.

## Quick Reference

### Model Tiers

| Model | Speed | Tokens | Rate Limit Impact | Best For |
|-------|-------|--------|-------------------|----------|
| **Haiku 3.5** | <1s | 1K-5K | LOW | Simple queries, status checks |
| **Sonnet 4** | ~5s | 15K-50K | MEDIUM | Standard development |
| **Opus 4** | ~15s | 100K-300K | HIGH | Complex analysis |
| **GPT-4.1** | ~30s | 0 Claude | NONE | Large implementations |

### Syntax

```python
Task(
    description="Task description",
    prompt="""@docs/agents/agent-name.md

Model: model-name

Task details...""",
    subagent_type="agent-name"
)
```

## Model Selection by Agent

### Default Models

Each agent has an optimal default model based on typical task complexity:

| Agent | Default Model | Reasoning |
|-------|---------------|-----------|
| 🚢 **Dock** | Haiku 3.5 | Simple container operations |
| 🏹 **Archer** | Haiku 3.5 | Fast pattern searches |
| 🔍 **Scout** | Sonnet 4 | Test writing complexity |
| 🦉 **Owl** | Sonnet 4 | Frontend development |
| 🔬 **Inspector** | Sonnet 4 | Code analysis |
| 🛍️ **Shopkeeper** | Sonnet 4 | Business logic |
| 🎭 **Playwright** | Sonnet 4 | Browser automation |
| 🔧 **Refactor** | Opus 4 | Systematic changes |
| ⚡ **Flash** | Opus 4 | Performance analysis |
| 🐛 **Debugger** | Opus 4 | Complex reasoning |
| 📋 **Planner** | Opus 4 | Architecture design |
| 💬 **GPT** | Opus 4 | Match ChatGPT capability |
| 🔥 **Phoenix** | Opus 4 | Migration complexity |

### Override Examples

#### 1. Simple Task → Downgrade to Haiku

```python
# Quick syntax check (normally Sonnet 4)
Task(
    description="Quick lint check",
    prompt="""@docs/agents/inspector.md

Model: haiku-3.5

Run basic syntax check on current file""",
    subagent_type="inspector"
)
```

#### 2. Complex Task → Upgrade to Opus

```python
# Complex test architecture (normally Sonnet 4)
Task(
    description="Complex test suite",
    prompt="""@docs/agents/scout.md

Model: opus-4

Design comprehensive test suite for multi-tenant system""",
    subagent_type="scout"
)
```

#### 3. Large Implementation → Offload to GPT

```python
# Massive refactoring (preserve Claude tokens)
Task(
    description="Large refactoring via GPT",
    prompt="""@docs/agents/gpt.md

Use GPT-4.1 for this 50+ file refactoring to preserve Claude rate limits""",
    subagent_type="gpt"
)
```

## Smart Context Manager Integration

The smart context manager automatically selects models based on task analysis:

```python
from tools.smart_context_manager import SmartContextManager

manager = SmartContextManager()
analysis = manager.analyze_task("Check container status")

# analysis.recommended_model = ModelTier.HAIKU
# Prompt automatically includes "Model: haiku-3.5"
```

## Rate Limit Optimization

With Pro/Max subscriptions, the real constraint is Claude rate limits, not cost. GPT usage is essentially free (just time cost).

### Token Usage by Model

- **Haiku 3.5**: 1K-5K tokens → Minimal rate limit impact
- **Sonnet 4**: 15K-50K tokens → Moderate rate limit usage
- **Opus 4**: 100K-300K tokens → Heavy rate limit usage
- **GPT-4.1**: 0 Claude tokens → Zero rate limit impact! (Free via ChatGPT Pro)

### Optimization Strategy

1. **High-volume operations** → Use Haiku 3.5
2. **Standard development** → Use Sonnet 4 (default)
3. **Complex analysis** → Use Opus 4 sparingly
4. **Large implementations** → Offload to GPT-4.1 (preserves 100% Claude tokens)

## Best Practices

### DO ✅

- Match model complexity to task complexity
- Use Haiku for repetitive/simple tasks
- Offload large implementations to GPT
- Consider rate limit impact for long sessions

### DON'T ❌

- Use Opus for simple status checks
- Forget to specify model for non-default cases
- Let agents call themselves (recursive loop)
- Ignore token usage in long conversations

## Fallback Behavior (Future)

```python
# Not yet implemented but documented
Model: sonnet-4 (fallback: sonnet-3.5)
Model: auto  # Let Claude Code decide
```

## Performance Benchmarks

### Response Times
Based on real testing:

| Task Type | Model | Response Time | Quality |
|-----------|-------|---------------|---------|
| Container status | Haiku 3.5 | <1s | Perfect |
| Write unit test | Sonnet 4 | ~5s | Excellent |
| Architecture analysis | Opus 4 | ~15s | Comprehensive |
| 50-file refactor | GPT-4.1 | ~30s | Consistent |

### Success Rates by Task Type

| Task Type | Haiku 3.5 | Sonnet 4 | Opus 4 |
|-----------|-----------|----------|--------|
| Simple file ops | 98% | 99% | 99% |
| Code writing | 65% | 87% | 92% |
| Test writing | 72% | 85% | 89% |
| Bug fixing | 45% | 78% | 91% |
| Architecture | 25% | 68% | 94% |
| Performance optimization | 15% | 52% | 89% |

**Key Insight**: Haiku 3.5 is 3-15x faster but with lower success rates on complex tasks. Opus 4 has 2x higher success rate for complex work.

## Troubleshooting

### Agent Not Using Specified Model?

1. Check syntax: `Model: model-name` on its own line
2. Ensure model name is exact (e.g., "haiku-3.5" not "haiku")
3. Verify agent supports model override

### Recursive Agent Calls

See [AGENT_SAFEGUARDS.md](./AGENT_SAFEGUARDS.md) for prevention strategies.

### Rate Limit Issues

1. Monitor token usage in Claude Code output
2. Switch to Haiku for high-volume tasks
3. Use GPT-4.1 for large implementations
4. Break complex tasks into smaller chunks

## Related Documentation

- [MODEL_SELECTION_TESTING.md](./MODEL_SELECTION_TESTING.md) - Test results
- [AGENT_SAFEGUARDS.md](./AGENT_SAFEGUARDS.md) - Recursive call prevention
- [Smart Context Manager](/tools/smart_context_manager.py) - Automatic routing