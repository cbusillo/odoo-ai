# Codex MCP Advanced Features Guide

## Overview

This document covers advanced configuration options for the OpenAI Codex MCP server that can significantly enhance
performance and capabilities.

See also:

- Basic usage and examples: ./usage.md
- Shared reference (models, sandbox, sessions, issues): ./reference.md

## Key Advanced Features

### 1. MCP Server Compatibility Mode

The Codex MCP server runs in compatibility mode by default, which provides synchronous responses required by most MCP
clients:

```python
# Compatibility mode is enabled by default in the MCP server
# This ensures session IDs are returned immediately in the response

response = mcp__gpt - codex__codex(
    prompt="Your task here",
    sandbox="workspace-write"
)

# Session ID is immediately available
session_id = response['structuredContent']['sessionId']

# Continue the conversation
mcp__gpt - codex__codex - reply(
    prompt="Follow-up question",
    sessionId=session_id
)
```

**Note**: The MCP server must be started with `--compatibility-mode` flag or have `mcp.compatibility_mode = true` in
config.toml.

### 2. Reasoning Configuration

Control how deeply the model thinks about problems:

```python
mcp__gpt - codex__codex(
    prompt="Complex architectural decision needed",
    model="gpt-5",
    config={
        "model_reasoning_effort": "high",  # Options: "low", "medium", "high"
        "model_reasoning_summary": "detailed",  # Options: "auto", "concise", "detailed"
        "show_raw_agent_reasoning": true  # Show raw chain-of-thought
    }
)
```

**When to use HIGH reasoning:**

- Complex architectural decisions
- Debugging intricate issues
- Performance optimization problems
- Security vulnerability analysis
- Algorithm design and optimization

### 3. Network Access in Sandbox

Enable network access while maintaining workspace write restrictions:

```python
config = {
    "sandbox_workspace_write.network_access": true,
    "sandbox_workspace_write.exclude_tmpdir_env_var": false,
    "sandbox_workspace_write.exclude_slash_tmp": false
}
```

**Use cases:**

- Installing packages during execution
- Making API calls for testing
- Downloading dependencies
- Fetching documentation

### 4. Environment Variable Control

Fine-tune which environment variables are passed to subprocesses:

```python
config = {
    "shell_environment_policy.inherit": "all",  # "all", "core", or "none"
    "shell_environment_policy.ignore_default_excludes": false,
    "shell_environment_policy.exclude": ["AWS_*", "AZURE_*", "GITHUB_*"],
    "shell_environment_policy.set": {
        "CI": "1",
        "NODE_ENV": "development",
        "DEBUG": "true"
    },
    "shell_environment_policy.include_only": ["PATH", "HOME", "USER"]
}
```

### 5. Performance Tuning

Optimize for large contexts and network reliability:

```python
config = {
    # Context management
    "model_context_window": 400000,  # Override default context size
    "model_max_output_tokens": 16384,  # Maximum output length
    "project_doc_max_bytes": 32768,  # Max bytes from AGENTS.md

    # Network tuning (per-provider basis)
    "request_max_retries": 4,  # HTTP request retries
    "stream_max_retries": 10,  # SSE stream reconnect attempts
    "stream_idle_timeout_ms": 300000  # 5 minute idle timeout
}
```

### 6. Zero Data Retention (ZDR)

For enterprise accounts with ZDR requirements:

```python
config = {
    "disable_response_storage": true  # Required for ZDR accounts
}
```

### 6. Custom Instructions

Override default system prompts:

```python
mcp__gpt - codex__codex(
    prompt="Your task",
    base - instructions = """You are an expert Python developer.
    Follow PEP 8 strictly.
    Always include type hints.
    Write comprehensive docstrings."""
)
```

### 7. Profile-Based Configuration

Use predefined profiles from ~/.codex/config.toml:

```toml
# In ~/.codex/config.toml
[profiles.deep-reasoning]
model = "gpt-5"
model_reasoning_effort = "high"
model_reasoning_summary = "detailed"
approval_policy = "never"

[profiles.deep-reasoning.sandbox_workspace_write]
network_access = true

[profiles.dev-standard]
model = "gpt-5"
model_reasoning_effort = "medium"
approval_policy = "never"

[profiles.test-runner]
model = "gpt-5"
model_reasoning_effort = "medium"
approval_policy = "never"

[profiles.safe-production]
model = "gpt-5"
model_reasoning_effort = "medium"
approval_policy = "on-request"
disable_response_storage = true

[profiles.quick]
model = "gpt-5"
model_reasoning_effort = "low"
model_reasoning_summary = "none"
approval_policy = "never"
```

Then use:

```python
# Use profiles with appropriate sandbox flags
mcp__gpt_codex__codex(
    prompt="Your task",
    profile="deep-reasoning",
    sandbox="workspace-write"  # Must specify sandbox explicitly
)

mcp__gpt_codex__codex(
    prompt="Run tests",
    profile="test-runner",
    sandbox="workspace-write"  # Must specify sandbox explicitly
)
```

## Common Advanced Patterns

### Maximum Intelligence Mode

For the most complex problems:

```python
mcp__gpt - codex__codex(
    prompt="Solve [complex problem]",
    model="gpt-5",  # Or "gpt-4.1" for 1M+ token contexts
    config={
        "model_reasoning_effort": "high",
        "model_reasoning_summary": "detailed",
        "show_raw_agent_reasoning": true,
        "hide_agent_reasoning": false,
        "model_max_output_tokens": 16384
    }
)
```

### Fast Iteration Mode

For quick development cycles:

```python
mcp__gpt - codex__codex(
    prompt="Quick implementation",
    model="gpt-5",
    approval - policy = "never",
config = {
    "model_reasoning_effort": "low",
    "hide_agent_reasoning": true,
    "sandbox_workspace_write.network_access": true
}
)
```

### Secure Production Mode

For production environments:

```python
mcp__gpt_codex__codex(
    prompt="Production task",
    profile="safe-production",  # Use safe-production profile
    sandbox="read-only",
    config={
        "shell_environment_policy.inherit": "none",
        "shell_environment_policy.set": {
            "NODE_ENV": "production"
        }
    }
)
```

## Troubleshooting

### Issue: Model not using enough reasoning

**Solution**: Set `model_reasoning_effort: "high"` and `model_reasoning_summary: "detailed"`

### Issue: Network requests failing in sandbox

**Solution**: Add `sandbox_workspace_write.network_access: true` to config

### Issue: Environment variables not available

**Solution**: Check `shell_environment_policy.exclude` patterns and adjust

### Issue: Context window exceeded

**Solution**: Override with `model_context_window` or switch to gpt-4.1 for 1M+ tokens

## Profile Limitations

### Sandbox Mode Cannot Be Set in Profiles

**CRITICAL**: Sandbox mode must be specified via CLI flags or config overrides, never in profiles:

```bash
# Via MCP (always specify sandbox explicitly)
mcp__gpt_codex__codex(
    prompt="Task",
    profile="deep-reasoning",
    sandbox="workspace-write"  # Required - profiles cannot set this
)
```

**Why this matters:**

- Profiles define reasoning, approval, and environment settings
- Sandbox mode is a security boundary that must be explicit

## Best Practices

1. **Start with defaults**: Only add config overrides when needed
2. **Use profiles**: Define common configurations in ~/.codex/config.toml
3. **Explicit sandbox**: Always specify sandbox mode explicitly, never rely on profile defaults
4. **Reasoning vs Speed**: High reasoning = slower but more thorough
5. **Security first**: Start with restrictive sandbox, escalate only when needed
6. **Monitor tokens**: Use `model_max_output_tokens` to prevent excessive output

## Reference

For complete configuration documentation, see:

- OpenAI Codex repository: `/codex-rs/config.md`
- MCP protocol specification
- OpenAI Platform documentation on reasoning models