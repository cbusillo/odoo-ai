# 🛡️ Error Recovery Framework for Agents

This document explains how to use the systematic error recovery framework for resilient agent operations.

## Overview

The error recovery framework (`tools/error_recovery.py`) provides:

- Automatic error classification
- Intelligent retry strategies
- Fallback agent chains
- Context-aware recovery
- Error pattern learning

## Error Categories & Recovery Strategies

| Category               | Examples                                   | Strategy           | Details                               |
|------------------------|--------------------------------------------|--------------------|---------------------------------------|
| **RATE_LIMIT**         | "429 Too Many Requests", "quota exceeded"  | Retry with backoff | 30s delay, 5 retries                  |
| **TIMEOUT**            | "operation timed out", "deadline exceeded" | Retry with backoff | 5s delay, 3 retries                   |
| **NETWORK**            | "connection error", "DNS failed"           | Immediate retry    | 2s delay, 3 retries                   |
| **PERMISSION**         | "403 Forbidden", "access denied"           | Fail immediately   | No recovery possible                  |
| **RESOURCE_NOT_FOUND** | "404 Not Found", "file not found"          | Try fallback       | Alternative approach                  |
| **MODEL_UNAVAILABLE**  | "claude-3-opus unavailable"                | Fallback model     | Use simpler model                     |
| **CONTEXT_LIMIT**      | "context too long", "token limit"          | Offload to GPT     | Hooks will remind to reload CLAUDE.md |
| **AGENT_FAILURE**      | Agent crashes or fails                     | Fallback agent     | Use alternative agent                 |

## Agent Fallback Chains

When an agent fails, the framework automatically suggests fallback agents:

```python
FALLBACK_CHAINS = {
    "flash": ["inspector", "archer"],  # Performance analysis
    "inspector": ["archer", "gpt"],  # Code quality
    "scout": ["gpt"],  # Test writing
    "owl": ["gpt"],  # Frontend
    "debugger": ["gpt", "anthropic-engineer"],  # Complex reasoning
    "planner": ["gpt", "anthropic-engineer"],  # Architecture
}
```

## Integration Patterns

### Pattern 1: Basic Error Handling

```python
from tools.error_recovery import handle_agent_error

try:
    # Agent task that might fail
    result = Task(
        description="Analyze performance",
        prompt="@docs/agents/flash.md\n\nCheck for N+1 queries",
        subagent_type="flash"
    )
except Exception as e:
    # Get recovery recommendations
    recovery = handle_agent_error(
        error=e,
        agent="flash",
        task="performance analysis",
        context={"module": "product_connect"}
    )

    if recovery["can_retry"]:
        # Wait and retry
        time.sleep(recovery["retry_delay"])
        result = retry_task()
    elif recovery["fallback_agent"]:
        # Use fallback agent
        result = Task(
            description="Fallback analysis",
            prompt=f"@docs/agents/{recovery['fallback_agent']}.md\n\n{original_task}",
            subagent_type=recovery["fallback_agent"]
        )
```

### Pattern 2: Multi-Agent Workflow with Recovery

```python
def resilient_quality_check(module_name):
    """Run quality checks with automatic recovery."""
    results = {}

    # Phase 1: Code analysis with fallback
    try:
        results["code"] = Task(
            description="Code analysis",
            prompt=f"@docs/agents/inspector.md\n\nAnalyze {module_name}",
            subagent_type="inspector"
        )
    except Exception as e:
        recovery = handle_agent_error(e, "inspector", "code analysis")
        if recovery["fallback_agent"]:
            print(f"Inspector failed, using {recovery['fallback_agent']}")
            results["code"] = Task(
                description="Fallback analysis",
                prompt=f"@docs/agents/{recovery['fallback_agent']}.md\n\nAnalyze {module_name}",
                subagent_type=recovery["fallback_agent"]
            )

    # Continue with other phases...
    return results
```

### Pattern 3: Rate Limit Handling

```python
def api_aware_task(task_description, agent="archer"):
    """Handle API rate limits gracefully."""
    retry_count = 0

    while retry_count < 5:
        try:
            return Task(
                description=task_description,
                prompt=f"@docs/agents/{agent}.md\n\n{task_description}",
                subagent_type=agent
            )
        except Exception as e:
            recovery = handle_agent_error(e, agent, task_description)

            if "rate" in str(e).lower() and recovery["can_retry"]:
                print(f"Rate limited, waiting {recovery['retry_delay']:.1f}s...")
                time.sleep(recovery["retry_delay"])
                retry_count += 1
            else:
                raise
```

### Pattern 4: Context Limit Recovery

```python
def handle_large_context_task(files, task):
    """Automatically offload to GPT when context is too large."""
    try:
        # Try with Claude first
        return Task(
            description=task,
            prompt=f"@docs/agents/inspector.md\n\nAnalyze files: {files}",
            subagent_type="inspector"
        )
    except Exception as e:
        recovery = handle_agent_error(e, "inspector", task)

        if recovery["fallback_agent"] == "gpt":
            print("Context too large for Claude, offloading to GPT...")
            return Task(
                description=task,
                prompt=f"@docs/agents/gpt.md\n\nUse gpt-5 for large context\n\n{task}",
                subagent_type="gpt"
            )
```

## Error Classification Examples

```python
from tools.error_recovery import classify_error

# Example errors and their classifications
errors = [
    "Rate limit exceeded: 429",  # RATE_LIMIT, RETRYABLE
    "Connection timeout after 30s",  # TIMEOUT, RETRYABLE
    "Model claude-3-opus not available",  # MODEL_UNAVAILABLE, FALLBACK
    "Permission denied to /etc/passwd",  # PERMISSION, FATAL
    "Context exceeds 200k tokens",  # CONTEXT_LIMIT, FALLBACK
]

for error_msg in errors:
    try:
        raise Exception(error_msg)
    except Exception as e:
        context = classify_error(e)
        print(f"{error_msg} -> {context.category.value}, {context.severity.value}")
```

## Exponential Backoff

The framework implements smart exponential backoff with jitter:

```
Retry 1: 2^0 * base_delay = 1-2 seconds
Retry 2: 2^1 * base_delay = 2-4 seconds  
Retry 3: 2^2 * base_delay = 4-8 seconds
Retry 4: 2^3 * base_delay = 8-16 seconds
Retry 5: 2^4 * base_delay = 16-32 seconds
(Capped at 5 minutes max)
```

## Best Practices

### 1. Always Handle Critical Operations

```python
# ✅ GOOD: Wrapped in error handling
try:
    critical_result = Task(...)
except Exception as e:
    recovery = handle_agent_error(e, agent, task)
    # Handle based on recovery recommendations

# ❌ BAD: No error handling
critical_result = Task(...)  # Will crash on failure
```

### 2. Log Recovery Actions

```python
if recovery["fallback_agent"]:
    print(f"Primary agent {agent} failed, using {recovery['fallback_agent']}")
    # Log to monitoring system
```

### 3. Respect Retry Limits

```python
if not recovery["can_retry"]:
    # Don't retry - either fail or use fallback
    raise Exception(f"Max retries exceeded for {task}")
```

### 4. Context-Aware Recovery

```python
# Include context for better error handling
recovery = handle_agent_error(
    error=e,
    agent="inspector",
    task="analyze module",
    context={
        "module": module_name,
        "file_count": len(files),
        "attempt": retry_count
    }
)
```

## Monitoring Error Patterns

The framework tracks error history to detect patterns:

- Repeated rate limits → Suggests throttling needed
- Frequent timeouts → May need performance optimization
- Context limits → Should pre-filter or chunk data
- Agent failures → May indicate agent-specific issues

## Integration with Claude

When Claude encounters errors, the framework provides clear guidance:

```
Agent 'flash' failed: Connection timeout
Category: TIMEOUT (retryable)
Recovery: Retry after 5.2 seconds (attempt 1/3)

OR

Agent 'inspector' failed: Context window exceeded
Category: CONTEXT_LIMIT (fallback)
Recovery: Fallback to gpt agent for large context handling
```

This allows Claude to make informed decisions about retrying, failing, or using alternatives.