# Codex MCP Usage Guide

## Overview

Codex MCP (`mcp__gpt-codex__codex`) is a powerful tool for delegating complex tasks to OpenAI models via the Codex CLI
MCP server.

## Basic Usage

### Starting a Conversation

```python
mcp__gpt - codex__codex(
    prompt="Your request here",
    sandbox="workspace-write",  # or "danger-full-access", "read-only"
    model="gpt-5",  # Default, or "gpt-4.1" (1M+ token context), "gpt-4.5"
    approval - policy = "never",  # or "untrusted", "on-failure", "on-request"
    # Additional optional parameters:
profile = "profile-name",  # Config profile from ~/.codex/config.toml
cwd = "/path/to/dir",  # Working directory
config = {"key": "value"},  # Config overrides (as TOML)
base - instructions = "custom",  # Replace default instructions
include - plan - tool = true  # Include plan tool
)
```

### Continuing a Session

**IMPORTANT**: The session ID is delivered via `codex/event` notification (NOT in the direct response).

```python
# After initial codex call, look for notification like:
# {"type": "codex/event", "sessionId": "urn:uuid:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"}

mcp__gpt - codex__codex - reply(
    prompt="Follow-up request",
    sessionId="urn:uuid:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # From codex/event notification
)
```

**Session ID Requirements**:

- Must be exact UUID from `codex/event` notification
- Format: `urn:uuid:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
- Never use arbitrary strings like "gpt-5" or "session-1"

Tip for Claude users: set the environment variable `CODEX_MCP_IMMEDIATE_RESULT=1` when launching the Codex MCP server to
receive an immediate `tools/call` result that contains `{ type: "session_started", sessionId }`. Event notifications
will continue to stream via `codex/event` until `task_complete`.

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
mcp__gpt - codex__codex(
    prompt="Research the best practices for [topic]. Search the web for current information.",
    sandbox="danger-full-access",
    model="gpt-5"  # Default - use this for most tasks
)
```

### Large Refactoring

```python
mcp__gpt - codex__codex(
    prompt="Refactor all files in @/path/to/directory to use async patterns",
    sandbox="workspace-write",
    model="gpt-5"  # Or "gpt-4.1" for very large contexts (1M+ tokens)
)
```

### Debug and Fix

```python
mcp__gpt - codex__codex(
    prompt="Debug and fix the failing tests in @/tests/. Run the tests and fix any issues.",
    sandbox="workspace-write"
)
```
