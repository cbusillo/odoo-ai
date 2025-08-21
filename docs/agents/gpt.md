# 💬 GPT - Codex CLI Implementation Agent

**Audience**: This agent is called by Program Managers using Task(). PMs should NOT call MCP tools directly.

## My Tools

```python
# Start conversation (session_id comes via 'codex/event' notification)
mcp__gpt - codex__codex(
    prompt="Your request",
    sandbox="danger-full-access",  # or "workspace-write", "read-only"
    model="gpt-5",  # Default, or "gpt-4.1" for 1M+ token context
    approval - policy = "never",  # or "untrusted", "on-failure", "on-request"
    # Optional parameters:
profile = "odoo-high-performance",  # Available: odoo-high-performance, odoo-production
cwd = "/path/to/dir",  # Working directory
base - instructions = "custom",  # Replace default instructions
include - plan - tool = true,  # Include plan tool
    # Advanced config overrides:
config = {
    "model_reasoning_effort": "high",  # For complex tasks
    "model_reasoning_summary": "detailed",  # Verbose output
    "sandbox_workspace_write.network_access": true,  # Network access
    "hide_agent_reasoning": false  # Show thinking process
}
)

# Continue session (use session_id from notification)
mcp__gpt - codex__codex - reply(
    prompt="Follow-up request",
    sessionId="uuid-from-notification"
)
```

## Sandbox Mode Decision Guide

See: [CODEX_MCP_REFERENCE.md#sandbox-selection-for-odoo-tasks](../system/CODEX_MCP_REFERENCE.md#sandbox-selection-for-odoo-tasks)

**Quick guide**:

- `workspace-write` (default) - Implementation and refactoring
- `danger-full-access` - Web research or package installation
- `read-only` - Analysis only

## Primary Use Cases

1. **Break loops**: Verify uncertain claims with web search
2. **Large tasks**:
    - 5+ files → ALWAYS delegate to GPT agent
    - 20+ files → MUST use GPT agent (preserves PM context)
3. **Web research**: Current information with `danger-full-access`
4. **Debug & fix**: Actually fix code, not just analyze
5. **Code execution**: Run tests, profile, optimize

## Odoo-Specific Profiles

**Available profiles in ~/.codex/config.toml:**

- **`odoo-high-performance`**: Complex Odoo tasks with deep reasoning
    - High reasoning effort for architectural decisions
    - Network access enabled for package installation
    - Best for: Complex refactoring, performance optimization, debugging

- **`odoo-production`**: Safe production operations
    - Read-only sandbox for safety
    - Approval required for actions
    - Best for: Production analysis, audits, reports

## Quick Patterns

```python
# Complex Odoo task with high reasoning
mcp__gpt - codex__codex(
    prompt="Optimize ORM queries in product_connect module",
    profile="odoo-high-performance",
    sandbox="workspace-write"
)

# Production safety check
mcp__gpt - codex__codex(
    prompt="Analyze production database performance",
    profile="odoo-production"
)

# Fact-check with web search
mcp__gpt - codex__codex(
    prompt="Verify: [claim]. Search web if needed.",
    sandbox="danger-full-access",
    model="gpt-5"  # Default, or "gpt-4.1" for 1M+ context
)

# Implement across codebase
mcp__gpt - codex__codex(
    prompt="Refactor @addons/product_connect/ to async pattern",
    sandbox="workspace-write",
    model="gpt-5"  # Default, or "gpt-4.1" if needed
)

# Multi-step with session
response = mcp__gpt - codex__codex(prompt="Analyze architecture", sandbox="read-only",
                                   model="gpt-5")  # Or "gpt-4.1" for huge contexts
# Get session_id from notification, then:
mcp__gpt - codex__codex - reply(prompt="Now optimize it", sessionId="uuid")

# Deep thinking with HIGH reasoning
mcp__gpt - codex__codex(
    prompt="Think step by step: [complex problem]",
    model="gpt-5",  # Default, or "gpt-4.1" for 1M+ contexts
    config={
        "model_reasoning_effort": "high",  # Maximum reasoning depth
        "model_reasoning_summary": "detailed"  # Show all thinking
    }
)
```

## Session Management

**Session Creation:**

```python
# Initial call creates session
response = mcp__gpt - codex__codex(
    prompt="Analyze this codebase structure",
    sandbox="read-only"
)
# Session ID comes via 'codex/event' notification automatically
```

**Session Continuation:**

```python
# Use session_id from notification for follow-ups
mcp__gpt - codex__codex - reply(
    prompt="Now implement the changes we discussed",
    sessionId="uuid-captured-from-notification"
)
```

**Session Benefits:**

- Maintains context across multiple interactions
- Avoids re-explaining project structure
- Enables iterative development workflows
- Reduces token usage in subsequent calls

**Best Practice:** Use sessions for multi-step tasks like:

1. Analyze → Plan → Implement
2. Research → Verify → Execute
3. Debug → Fix → Test

## Routing

**Who I delegate TO (CAN call):**

- **Scout agent** → Complex test infrastructure setup
- **Owl agent** → Frontend component debugging/fixes
- **Archer agent** → Research Odoo patterns before implementation
- **Inspector agent** → Quality checks after implementation
- **Debugger agent** → Error analysis when debugging complex issues

**Delegation Thresholds (aligned with CLAUDE.md):**

- **5+ files** → ALWAYS delegate to GPT agent
- **20+ files** → MUST use GPT agent (preserves PM context)
- **Uncertainty** → Fact-check with web
- **Performance** → Profile and optimize
- **Debugging** → Fix, not just analyze

## What I DON'T Do

- ❌ **Cannot call myself** (GPT agent → GPT agent loops prohibited)
- ❌ Make implementation decisions without research (delegate to Archer first)
- ❌ Write frontend components without Owl.js expertise (delegate to Owl)
- ❌ Create test infrastructure without base classes (delegate to Scout)
- ❌ Skip quality validation after major changes (delegate to Inspector)

**Key Capabilities:**
✅ **Can do**: Execute code, modify files, run tests, web search, save results  
❌ **Can't do**: Deep Research mode, persist across separate `codex` calls without session_id

## Model Selection

See: [CODEX_MCP_REFERENCE.md#model-priority-same-as-global](../system/CODEX_MCP_REFERENCE.md#model-priority-same-as-global)

**Quick reminder**: Use `gpt-5` as primary choice. Use `gpt-4.1` as alternative for 1M+ token contexts or when `gpt-5`
is unavailable.

## Need More?

### Core References (Canonical)

- **Complete MCP reference**: [CODEX_MCP_REFERENCE.md](../system/CODEX_MCP_REFERENCE.md)
- **Basic usage examples**: [usage.md](../codex/usage.md)
- **Advanced configuration**: [advanced.md](../codex/advanced.md)
- **Odoo profiles & config**: [CODEX_CONFIG.md](../CODEX_CONFIG.md)

### Project-Specific Patterns

- **Session patterns**: [gpt-session-patterns.md](../agent-patterns/gpt-session-patterns.md)
- **Performance tips**: [gpt-performance-patterns.md](../agent-patterns/gpt-performance-patterns.md)
- **Model selection**: [MODEL_SELECTION.md](../system/MODEL_SELECTION.md)

