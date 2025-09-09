# Codex MCP Advanced Guide (Trimmed)

Purpose: capture advanced, supported usage for our local Codex MCP setup without speculative options.

See also:
- Basic usage and examples: ./usage.md
- Shared reference (models, sandbox, sessions, issues): ./reference.md

## Session Continuation (codex_reply)

Our local Codex MCP server exposes two tools:
- `mcp__codex__codex` — start a task/conversation
- `mcp__codex__codex_reply` — continue a prior session

```python
response = mcp__codex__codex(
    prompt="Your task here",
    sandbox="workspace-write"
)
session_id = response["structuredContent"]["sessionId"]

mcp__codex__codex_reply(
    prompt="Follow-up question",
    sessionId=session_id
)
```

## Environment Variables

Pass specific variables to subprocesses invoked by tools:

```python
mcp__codex__codex(
    prompt="Run tests",
    sandbox="workspace-write",
    # Omit model to use CLI default. If you have a large‑context model configured, pass model=env("OPENAI_PRIMARY_MODEL") only when necessary.
    config={
        "shell_environment_policy.set": {
            "ODOO_RC": "/volumes/odoo.local.conf"
        }
    }
)
```

## Profiles

Define profiles in `~/.codex/config.toml` for common settings, then select with `profile=...`. Always pass `sandbox` explicitly in calls.

```toml
[profiles.test-runner]
model = env("OPENAI_PRIMARY_MODEL")
approval_policy = "never"
```

```python
mcp__codex__codex(
    prompt="Run unit tests",
    profile="test-runner",
    sandbox="workspace-write"
)
```

## Best Practices

1. Keep config minimal; prefer profiles for repeatable settings.
2. Specify sandbox explicitly (`read-only` or `workspace-write`).
3. Use `codex_reply` for multi-turn sessions from external clients (e.g., Claude Code).
4. Prefer built-in tools for routine IO; use JetBrains only for IDE-specific actions.

## Troubleshooting

- If a call fails due to missing env, add needed keys under `shell_environment_policy.set`.
- If session continuation fails, re-check the `sessionId` value from the initial response.
