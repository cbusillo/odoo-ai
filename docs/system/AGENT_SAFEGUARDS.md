# Agent Safeguards and Anti-Patterns

## Delegation Thresholds (Canonical)

**These are the ONLY delegation thresholds. All documentation should reference this section.**

| Context/Scope           | Action                      | Rationale                                      |
|-------------------------|-----------------------------|------------------------------------------------|
| **1-2 files**           | Handle directly             | Small scope, quick edits                       |
| **3-5 files**           | Consider specialists        | Medium complexity benefits from expertise      |
| **5+ files**            | ALWAYS delegate to GPT      | Preserves context, GPT has efficient execution |
| **20+ files**           | MUST use GPT agent          | Only GPT can handle this scale effectively     |
| **Context >30%**        | Offload everything          | Critical context preservation needed           |
| **Any uncertainty**     | GPT for verification        | External validation prevents errors            |
| **Web research needed** | GPT with danger-full-access | Only GPT has web access capability             |

## Critical Issue: Recursive Agent Calls

### The Problem

Agents can inadvertently call themselves, creating infinite loops that crash Claude Code:

```python
# ❌ DANGEROUS: Inspector calling Inspector
Task(
    description="Code quality check",
    prompt="@docs/agents/inspector.md\n\nAnalyze this code",
    subagent_type="inspector"  # Same agent!
)
```

### Why This Happens

1. Agents might delegate "similar" tasks without checking agent type
2. Generic task descriptions can match multiple agents
3. No built-in loop detection in Claude Code

## Safeguard Patterns

### 1. Agent Self-Awareness

Each agent should know its own identity and avoid self-delegation:

```python
# In agent documentation
## What I DON'T Do
- ❌ Call
myself(Inspector)
for sub - tasks
    - ❌ Create
recursive
delegation
loops
```

### 2. Explicit Delegation Rules

Define clear handoff patterns:

```python
# ✅ GOOD: Inspector delegates to Refactor
if bulk_fixes_needed:
    Task(
        description="Fix issues",
        prompt="@docs/agents/refactor.md\n\nFix these issues",
        subagent_type="refactor"  # Different agent
    )

# ❌ BAD: Inspector delegates to Inspector
if more_analysis_needed:
    Task(
        description="Deep analysis",
        prompt="@docs/agents/inspector.md\n\nAnalyze deeper",
        subagent_type="inspector"  # RECURSIVE!
    )
```

### 3. Task Context Passing

When agents need to maintain context, pass it explicitly rather than re-delegating:

```python
# ✅ GOOD: Return results for main context to handle
return {
    "initial_findings": [...],
    "needs_deeper_analysis": True,
    "suggested_next_steps": ["Check performance", "Review security"]
}

# ❌ BAD: Self-delegation for "deeper analysis"
Task(subagent_type="inspector", prompt="Analyze deeper...")
```

## Delegation Matrix

Safe delegation patterns between agents:

| From Agent | Safe to Call                      | Never Call       |
|------------|-----------------------------------|------------------|
| Inspector  | Refactor, QC, GPT                 | Inspector (self) |
| QC         | Inspector, Scout, Flash, Refactor | QC (self)        |
| Refactor   | Archer, Owl, Inspector            | Refactor (self)  |
| Scout      | Playwright, Owl                   | Scout (self)     |
| Debugger   | Dock, GPT                         | Debugger (self)  |
| Planner    | Archer, GPT                       | Planner (self)   |

## Implementation Recommendations

### 1. Add Call Stack Tracking

```python
# Hypothetical Claude Code enhancement
def Task(..., subagent_type, _call_stack=None):
    if _call_stack and subagent_type in _call_stack:
        raise RecursionError(f"Agent {subagent_type} already in call stack")

    new_stack = (_call_stack or []) + [subagent_type]
    # Pass new_stack to sub-tasks
```

### 2. Agent Metadata Validation

```python
# In smart context manager
def validate_delegation(from_agent: str, to_agent: str) -> bool:
    """Prevent dangerous delegations"""
    if from_agent == to_agent:
        raise ValueError(f"Agent {from_agent} cannot delegate to itself")

    # Additional rules...
    return True
```

### 3. Documentation Standards

Every agent should explicitly list:

- ✅ Agents it CAN safely call
- ❌ Agents it should NEVER call
- 📋 Preferred delegation patterns

## Testing for Recursive Calls

Before using an agent delegation pattern:

1. **Check agent types**: Ensure from_agent ≠ to_agent
2. **Review call chain**: Trace through potential delegation paths
3. **Test with small scope**: Verify no loops before large tasks
4. **Monitor execution**: Watch for repeated similar outputs

## Recovery from Crashes

If Claude Code crashes from recursion:

1. **Restart Claude Code**: Clear the stuck state
2. **Review agent calls**: Find the self-delegation
3. **Update documentation**: Add explicit "DON'T call self" warnings
4. **Report issue**: Help improve Claude Code safeguards