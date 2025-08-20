# Codex MCP Reference

## What This Covers

- Model selection and when to use each
- Sandbox modes and recommended defaults
- Session management essentials
- Common issues and error handling

See also:

- Basic usage and examples: [usage.md](./usage.md)
- Advanced configuration: [advanced.md](./advanced.md)

## Model Selection

| Model             | Best For                   | Context Window | Notes                                                        |
|-------------------|----------------------------|----------------|--------------------------------------------------------------|
| `gpt-5` (default) | Most tasks, fast & capable | ~400K tokens   | Use for 99% of tasks                                         |
| `gpt-4.1`         | Extremely large codebases  | 1M+ tokens     | Alternative when `gpt-5` context insufficient or unavailable |
| `gpt-4.5`         | Alternative option         | ~400K tokens   | Additional fallback if others unavailable                    |

### Model Priority

1. **gpt-5** - Primary choice for most tasks
2. **gpt-4.1** - Alternative for massive contexts (1M+ tokens) or when gpt-5 unavailable
3. **gpt-4.5** - Additional fallback option when needed

## Sandbox Modes

| Mode                 | Use Case                      | Permissions                     |
|----------------------|-------------------------------|---------------------------------|
| `read-only`          | Analysis, exploration         | Read files only                 |
| `workspace-write`    | Implementation, file changes  | Read/write files within project |
| `danger-full-access` | Web research, external access | Full system + network access    |

- Default: Start with `workspace-write`. Switch to `danger-full-access` only when internet or system-wide access is
  required.

## Session Management

- Initial `codex` call creates a session automatically.
- Session ID is delivered via `codex/event` notification (not in the direct response).
- Session IDs must be valid UUIDs.
- Use the session ID with `mcp__gpt-codex__codex-reply` to maintain context across turns.
- For the code snippet to continue a session, see: [usage.md#continuing-a-session](./usage.md#continuing-a-session)

## Common Issues

### Empty or Missing Response

1. Verify Codex CLI is available: `codex --help`
2. Ensure the MCP server is running: `codex mcp`
3. Confirm your MCP configuration in the assistant settings
4. Retry with a simpler prompt and escalate sandbox if needed

### Session ID Problems

- Error: "Failed to parse session_id"
- Ensure you use the UUID from the `codex/event` notification
- Do not manually construct session IDs