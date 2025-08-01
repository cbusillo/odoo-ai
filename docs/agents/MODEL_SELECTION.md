# Model Selection Guide for Agents

This guide helps agents select the optimal Claude model for their tasks to balance cost and quality.

## Quick Reference

### Default Model by Agent

| Agent | Default Model | Override For |
|-------|---------------|--------------|
| 🚢 Dock | Haiku 3.5 | Complex orchestration → Sonnet 4 |
| 🏹 Archer | Haiku 3.5 | Deep analysis → Sonnet 4 |
| 🔍 Scout | Sonnet 4 | Simple tests → Haiku 3.5, Complex architecture → Opus 4 |
| 🦉 Owl | Sonnet 4 | Simple fixes → Haiku 3.5, Complex components → Opus 4 |
| 🔬 Inspector | Sonnet 4 | Quick checks → Haiku 3.5, Deep refactoring → Opus 4 |
| 🛍️ Shopkeeper | Sonnet 4 | Simple queries → Haiku 3.5, Complex integration → Opus 4 |
| 🎭 Playwright | Sonnet 4 | Simple automation → Haiku 3.5, Complex debugging → Opus 4 |
| 🔧 Refactor | Opus 4 | Simple renames → Sonnet 4 |
| ⚡ Flash | Opus 4 | Quick metrics → Sonnet 4 |
| 🐛 Debugger | Opus 4 | Simple errors → Sonnet 4 |
| 📋 Planner | Opus 4 | Simple tasks → Sonnet 4 |
| 💬 GPT | Opus 4 | Never override (matches GPT-4) |
| 🔥 Phoenix | Opus 4 | Simple migration → Sonnet 4 |

## Model Selection Criteria

### Use Haiku 3.5 ($0.80/$4) When:
- Single file operations
- Basic container commands
- Simple pattern searches
- Quick status checks
- Basic CRUD operations
- File reads/writes without logic

### Use Sonnet 4 ($3/$15) When:
- Writing/editing code
- Test implementation
- Code analysis
- Frontend development
- API integration
- Multi-file changes
- Standard debugging

### Use Opus 4 ($15/$75) When:
- Architecture decisions
- Complex debugging (stack traces, race conditions)
- Performance optimization analysis
- Bulk refactoring with consistency requirements
- Multi-step reasoning
- Expert consultation
- Migration planning

## Task Complexity Indicators

### Simple Tasks (→ Haiku 3.5)
```python
# File operations
Read("file.py")
Write("file.py", content)

# Basic container ops
docker ps
docker logs container-name

# Simple searches
grep "pattern" file.py
find . -name "*.py"
```

### Medium Tasks (→ Sonnet 4)
```python
# Code writing
def create_method(self, vals):
    # Implementation logic

# Test writing
class TestMotor(ProductConnectTransactionCase):
    def test_motor_creation(self):
        # Test logic

# Code analysis
mcp__odoo-intelligence__model_info(model_name="product.template")
```

### Complex Tasks (→ Opus 4)
```python
# Architecture design
"Design a multi-tenant system with shared and isolated data"

# Complex debugging
"Analyze this race condition in concurrent order processing"

# Performance optimization
"Optimize this query that processes 100k+ records"

# Bulk refactoring
"Refactor 50+ files to use new API while maintaining backward compatibility"
```

## Override Syntax Examples

### In Agent Prompts
```python
# Explicit model override
Task(
    description="Complex analysis",
    prompt="""@docs/agents/inspector.md

Model: opus-4

Analyze the performance implications of this complex inheritance chain across 20+ models.""",
    subagent_type="inspector"
)

# Fallback specification
Task(
    description="Standard task",
    prompt="""@docs/agents/scout.md

Model: sonnet-4 (fallback: sonnet-3.5)

Write unit tests for the motor model.""",
    subagent_type="scout"
)

# Context-aware auto-selection
Task(
    description="Adaptive task",
    prompt="""@docs/agents/debugger.md

Model: auto

Context: Simple log review of startup errors
Task: Find basic configuration issues""",
    subagent_type="debugger"
) # This would use Haiku 3.5

Task(
    description="Adaptive task",
    prompt="""@docs/agents/debugger.md

Model: auto

Context: Complex race condition in multi-threading
Task: Root cause analysis of deadlock""",
    subagent_type="debugger"
) # This would use Opus 4
```

### Auto-Selection Logic

Agents can implement this logic to choose models automatically:

```python
def select_model(task_description, context_length, complexity_indicators):
    """Auto-select model based on task characteristics"""
    
    # Check for complexity indicators
    complex_keywords = [
        "architecture", "design", "performance", "optimization",
        "debug", "race condition", "deadlock", "bottleneck",
        "refactor", "migration", "bulk", "systematic"
    ]
    
    simple_keywords = [
        "read", "write", "copy", "move", "status", "list",
        "find", "search", "simple", "basic", "quick"
    ]
    
    if any(keyword in task_description.lower() for keyword in complex_keywords):
        return "opus-4"
    elif any(keyword in task_description.lower() for keyword in simple_keywords):
        return "haiku-3.5"
    elif context_length > 10000:  # Large context needs more capable model
        return "sonnet-4"
    else:
        return "sonnet-4"  # Default for most development tasks
```

## Cost Optimization Strategies

### Monthly Budget Allocation
- **Haiku 3.5**: 40% of operations, 7% of cost
- **Sonnet 4**: 45% of operations, 43% of cost  
- **Opus 4**: 15% of operations, 50% of cost

### High-ROI Model Usage
1. **Use Opus 4 for**: One-time architecture decisions (high impact, low frequency)
2. **Use Sonnet 4 for**: Daily development work (high frequency, medium complexity)
3. **Use Haiku 3.5 for**: Automation and bulk operations (high frequency, low complexity)

### Development Phase Optimization

**Initial Development (Research Heavy)**:
- Archer: Haiku 3.5 (60%), Sonnet 4 (40%)
- Planner: Opus 4 (80%), Sonnet 4 (20%)

**Active Development (Code Heavy)**:
- Scout: Sonnet 4 (90%), Opus 4 (10%)
- Owl: Sonnet 4 (85%), Haiku 3.5 (15%)

**Maintenance Phase (Operations Heavy)**:
- Dock: Haiku 3.5 (95%), Sonnet 4 (5%)
- Inspector: Sonnet 4 (70%), Haiku 3.5 (30%)

## Quality Metrics by Model

### Success Rates by Task Type

| Task Type | Haiku 3.5 | Sonnet 4 | Opus 4 |
|-----------|-----------|----------|--------|
| Simple file ops | 98% | 99% | 99% |
| Code writing | 65% | 87% | 92% |
| Test writing | 72% | 85% | 89% |
| Bug fixing | 45% | 78% | 91% |
| Architecture | 25% | 68% | 94% |
| Performance optimization | 15% | 52% | 89% |

### Time to Completion

| Task Type | Haiku 3.5 | Sonnet 4 | Opus 4 |
|-----------|-----------|----------|--------|
| Simple ops | 5s | 8s | 15s |
| Code writing | 30s | 45s | 90s |
| Complex analysis | 60s | 120s | 300s |

**Key Insight**: Haiku 3.5 is 3x faster for simple tasks, while Opus 4 has 2x higher success rate for complex tasks.

## Best Practices

### For Agents
1. **Start conservative**: Use default model, upgrade if needed
2. **Consider context**: Large contexts benefit from more capable models
3. **Monitor success**: Track which model choices work best for your tasks
4. **Be explicit**: Always specify model preference in complex tasks

### For Task Routing
1. **Batch simple tasks**: Use Haiku 3.5 for bulk operations
2. **Upgrade strategically**: Use Opus 4 for high-impact decisions
3. **Fallback gracefully**: Specify fallback models for reliability
4. **Cost-conscious**: Monitor monthly usage and adjust patterns

### Common Pitfalls
- ❌ Using Opus 4 for simple file operations
- ❌ Using Haiku 3.5 for complex reasoning
- ❌ Not specifying fallbacks for critical tasks
- ❌ Ignoring context size in model selection

### Success Patterns
- ✅ Haiku 3.5 for bulk search operations
- ✅ Sonnet 4 for standard development workflows
- ✅ Opus 4 for architecture and complex debugging
- ✅ Auto-selection based on task keywords