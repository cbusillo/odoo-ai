# 💬 GPT - Codex CLI Implementation Agent

**Audience**: This agent is called by Program Managers using Task(). PMs should NOT call MCP tools directly.

## My Tools

```python
# Start conversation (sessionId returned in response)
mcp__codex-mcp__codex(
    prompt="Your request",
    sandbox="workspace-write",  # Choose: read-only, workspace-write
    profile="dev-standard",     # Choose profile by task complexity
    cwd="/path/to/dir",         # Optional working dir
    base_instructions="custom", # Optional override
    include_plan_tool=True       # Optional plan tool
)

# CRITICAL: Always include documentation paths in prompts
# Example with documentation context:
mcp__codex-mcp__codex(
    prompt="""Review code quality in @addons/product_connect
    
    Key documentation:
    - Project instructions: @CLAUDE.md
    - Odoo patterns: @docs/agent-patterns/odoo-patterns.md
    - Style guides: @docs/style/ODOO.md @docs/style/PYTHON.md
    - Testing patterns: @docs/agent-patterns/testing.md
    
    Focus on Odoo framework compliance and performance.""",
    sandbox="workspace-write",
    profile="dev-standard"
)

# Continue session (reuse sessionId from initial response)
mcp__codex-mcp__codex(
    prompt="Follow-up request",
    sessionId="12345678-1234-1234-1234-123456789abc"
)
```

## Sandbox Mode Selection

Choose the appropriate sandbox mode for your task:

- **`read-only`** - Code analysis, pattern searches, auditing
- **`workspace-write`** - Implementation, refactoring, file modifications (default)

Note: Package installation and system operations should be done directly in Claude Code, not through Codex.

## Primary Use Cases

1. **Break loops**: Verify uncertain claims with web search
2. **Large tasks**:
    - 5+ files → ALWAYS delegate to GPT agent
    - 20+ files → MUST use GPT agent (preserves PM context)
3. **Web research**: Current information (web search enabled in config)
4. **Debug & fix**: Actually fix code, not just analyze
5. **Code execution**: Run tests, profile, optimize

## When To Switch From Claude Code To Codex

- 5+ files or bulk refactors/renames
- Heavy web research or long-running tasks
- You’re watching Claude’s 5‑hour window and want to preserve it
- Need separate session continuity for multi‑step large work

## Profile Selection

Choose the appropriate profile based on task complexity and requirements:

- **`quick`** - Simple, fast tasks (low reasoning effort)
    - Best for: Simple bug fixes, quick implementations

- **`dev-standard`** - Standard development tasks (medium reasoning, auto-approval)
    - Best for: Standard implementation, bug fixes, routine development

- **`deep-reasoning`** - Complex multi-step tasks (high reasoning effort)
    - Best for: Complex refactoring, performance optimization, debugging

- **`test-runner`** - Test execution and debugging (medium reasoning)
    - Best for: Running tests, test debugging, CI/CD tasks

- **`safe-production`** - Production analysis (approval required, no storage)
    - Best for: Production analysis, audits, reports

## Common Usage Patterns

```python
# Quick fix - simple tasks
mcp__codex-mcp__codex(
    prompt="Fix syntax error in views",
    profile="quick",
    sandbox="workspace-write"
)

# Standard development - typical implementation
mcp__codex-mcp__codex(
    prompt="Refactor @addons/product_connect/ to async pattern",
    profile="dev-standard",
    sandbox="workspace-write"
)

# Complex task - architectural changes  
mcp__codex-mcp__codex(
    prompt="Optimize ORM queries in product_connect module",
    profile="deep-reasoning",
    sandbox="workspace-write"
)

# Web research - fact checking
mcp__codex-mcp__codex(
    prompt="Verify: [claim]. Search web if needed.",
    profile="dev-standard",
    sandbox="workspace-write"  # Web search enabled in config
)

# Test execution 
mcp__codex-mcp__codex(
    prompt="Run unit tests and fix failures",
    profile="test-runner",
    sandbox="workspace-write"
)

# Production analysis - read-only safety
mcp__codex-mcp__codex(
    prompt="Analyze production database performance",
    profile="safe-production",
    sandbox="read-only"
)

# Multi-step with session
response = mcp__codex-mcp__codex(
    prompt="Analyze architecture",
    profile="dev-standard",
    sandbox="read-only"
)
session_id = response['structuredContent']['sessionId']
mcp__codex-mcp__codex(prompt="Now optimize it", sessionId=session_id)
```

## Session Management

**IMPORTANT**: The Codex MCP server runs in compatibility mode for synchronous responses:

- The `codex` tool returns an immediate response with session ID
- Session IDs are included in the response's `structuredContent.sessionId` field
- No async notifications or event handling required

**Session Creation:**

```python
# Initial call creates session and returns session ID directly
response = mcp__gpt - codex__codex(
    prompt="Analyze this codebase structure",
    sandbox="read-only"
)
# Extract session ID from response
session_id = response['structuredContent']['sessionId']
# Example: "12345678-1234-1234-1234-123456789abc"
```

**Session Continuation:**

```python
# Use UUID session_id from initial response for follow-ups
mcp__gpt - codex__codex_reply(
    prompt="Now implement the changes we discussed",
    sessionId=session_id  # From response['structuredContent']['sessionId']
)
```

**Session Benefits:**

- Maintains context across multiple interactions
- Avoids re-explaining project structure
- Enables iterative development workflows
- Reduces token usage in subsequent calls

**Session ID Format Requirements:**

- Must be valid UUID format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
- Never use arbitrary strings (e.g., model names) or custom IDs
- Always extract from response's `structuredContent.sessionId` field
- Session IDs are automatically generated by Codex CLI
- Do NOT add "urn:uuid:" prefix

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

## Troubleshooting

### Session ID Parsing Errors

**Error**:
`"Failed to parse session_id: invalid UUID format"`

**Cause**: Using invalid session ID format (e.g., a model name instead of a proper UUID)

**Solution**:

1. Never manually create session IDs
2. Always extract from response's `structuredContent.sessionId`
3. Ensure format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` (no urn:uuid: prefix)

```python
# ❌ WRONG - Manual session ID
mcp__gpt - codex__codex_reply(
    prompt="Continue task",
    sessionId="gibberish"  # This will fail
)

# ✅ CORRECT - UUID from response
mcp__gpt - codex__codex_reply(
    prompt="Continue task",
    sessionId="12345678-1234-1234-1234-123456789abc"  # From response['structuredContent']['sessionId']
)
```

### Session Continuation Issues

**Common Problems**:

1. **Session Not Found**: Session may have expired or been cleaned up
    - **Solution**: Start new session, provide context in prompt

2. **Context Lost**: Session doesn't remember previous conversation
    - **Solution**: Include key context in continuation prompt

3. **Permission Errors**: Session sandbox mode conflicts with new task
    - **Solution**: Start new session with appropriate sandbox mode

### Sandbox Mode Requirements

**Error**: Permission denied or insufficient access

**Solutions by Operation Type**:

```python
# File analysis only - read-only sufficient
mcp__gpt - codex__codex(
    prompt="Analyze code patterns in this file",
    sandbox="read-only"
)

# Code implementation - workspace-write required
mcp__gpt - codex__codex(
    prompt="Implement new feature in existing files",
    sandbox="workspace-write"  # Default for most tasks
)

# Note: For package installation or system operations, use Claude Code directly instead of Codex
```

### Model Availability Issues

**Error**: Model not available or rate limited

**Solution**: Model selection strategy

```python
# Primary: Use default (no model parameter)
mcp__gpt - codex__codex(
    prompt="Your task"
    # No model parameter - uses OPENAI_PRIMARY_MODEL from config
)

# Extended context: ONLY when needed for 400K+ tokens
mcp__gpt - codex__codex(
    prompt="Your task",
    model="gpt-4.1"  # ONLY specify for huge contexts (1M+ tokens)
)

# Note: gpt-4.5 exists but rarely needed - let config handle fallbacks
```

### Context Size Issues

**Error**: Context too large or token limit exceeded

**Solutions**:

1. **Use gpt-4.1**: 1M+ token context window
2. **Break into smaller tasks**: Decompose large requests
3. **Use sessions**: Maintain context across multiple calls
4. **Focus scope**: Be specific about files/areas to analyze

### Performance Issues

**Symptoms**: Slow responses, timeouts

**Optimizations**:

```python
# Quick tasks - use quick profile (uses OPENAI_PRIMARY_MODEL)
mcp__gpt - codex__codex(
    prompt="Fix simple syntax error",
    profile="quick"  # Low reasoning effort, faster
    # No model parameter - uses OPENAI_PRIMARY_MODEL
)

# Complex tasks - optimize reasoning
mcp__gpt - codex__codex(
    prompt="Complex architectural refactoring",
    profile="deep-reasoning",  # High reasoning effort
    config={
        "model_reasoning_effort": "high",
        "model_reasoning_summary": "detailed"
    }
)
```

## Related Documentation

### Codex MCP References

- **Complete MCP Reference**: [CODEX_MCP_REFERENCE.md](../system/CODEX_MCP_REFERENCE.md) - Full Codex tool documentation
- **Odoo Profiles & Config**: [CODEX_CONFIG.md](../CODEX_CONFIG.md) - Pre-configured profiles for Odoo tasks
- **Model Selection**: [MODEL_SELECTION.md](../system/MODEL_SELECTION.md) - When to use different models

### Pattern Documentation

- **Session Patterns**: [gpt-session-patterns.md](../agent-patterns/gpt-session-patterns.md) - Multi-turn conversation
  patterns
- **Performance Patterns**: [gpt-performance-patterns.md](../agent-patterns/gpt-performance-patterns.md) - Optimization
  strategies

### External Resources

- **Codex CLI**: Check latest features via MCP tools (post-training)
- **Model Updates**: OpenAI models evolve; set OPENAI_PRIMARY_MODEL accordingly
