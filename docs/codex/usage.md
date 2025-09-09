# Codex MCP Usage Guide

## Overview

Codex MCP (`mcp__codex__codex`) is a powerful tool for delegating complex tasks to OpenAI models via the Codex CLI
MCP server.

## Basic Usage

### Starting a Conversation

```python
response = mcp__codex__codex(
    prompt="Your request here",
    sandbox="workspace-write",  # or "read-only" for analysis only
    # model: omit to use CLI default; set env("OPENAI_PRIMARY_MODEL") only when you must override.
    # model=env("OPENAI_PRIMARY_MODEL"),
    approval_policy="never",  # or "untrusted", "on-failure", "on-request"
    # Additional optional parameters:
    profile="profile-name",  # Config profile from ~/.codex/config.toml
    cwd="/path/to/dir",  # Working directory
    config={"key": "value"},  # Config overrides (as TOML)
    base_instructions="custom",  # Replace default instructions
    include_plan_tool=True  # Include plan tool
)

# Extract session ID from response
session_id = response['structuredContent']['sessionId']
```

### Continuing a Session

**IMPORTANT**: The session ID is now returned directly in the response.

```python
# Use the session ID from the initial codex call response
mcp__codex__codex_reply(
    prompt="Follow-up request",
    sessionId=session_id  # From response['structuredContent']['sessionId']
)
```

**Session ID Requirements**:

- Must be the exact UUID from the initial response
- Format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` (standard UUID)
- Never use arbitrary strings like a model name or "session-1"
- Do NOT add "urn:uuid:" prefix

## Sandbox Modes

See: [reference.md#sandbox-modes](./reference.md#sandbox-modes)

## Model Selection

See: [reference.md#model-selection](./reference.md#model-selection)

## When to Use Codex

### ALWAYS Use For:

- Tasks involving 5+ files
- Web research requiring current information
- Complex multi-step implementations
- When you need to verify uncertain information
- Code execution and testing

### Session Management Notes

See: [reference.md#session-management](./reference.md#session-management)

## Common Issues

See: [reference.md#common-issues](./reference.md#common-issues)

## See Also

- Reference: [reference.md](./reference.md)
- Advanced features: [advanced.md](./advanced.md)

## Example Patterns

### Web Research

```python
response = mcp__codex__codex(
    prompt="Research the best practices for [topic]. Search the web for current information.",
    sandbox="workspace-write",  # Sufficient for network access
    # Omit model to use CLI default; select a large‑context model via env only if configured and truly needed.
)
session_id = response['structuredContent']['sessionId']
```

### Large Refactoring

```python
response = mcp__codex__codex(
    prompt="Refactor all files in @/path/to/directory to use async patterns",
    sandbox="workspace-write",
    model=env("OPENAI_PRIMARY_MODEL")
)
session_id = response['structuredContent']['sessionId']
```

### Debug and Fix

```python
response = mcp__codex__codex(
    prompt="Debug and fix the failing tests in @/tests/. Run the tests and fix any issues.",
    sandbox="workspace-write"
)
session_id = response['structuredContent']['sessionId']

# Continue with follow-up if needed
mcp__codex__codex_reply(
    prompt="Now add test coverage for the edge cases",
    sessionId=session_id
)
```
