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
- Session ID is returned in the direct response's `structuredContent.sessionId` field
- Session IDs are standard UUIDs: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
- Never manually create session IDs - always extract from the response
- Use the session ID with `mcp__gpt-codex__codex-reply` to maintain context across turns.
- For the code snippet to continue a session, see: [usage.md#continuing-a-session](./usage.md#continuing-a-session)

## Common Issues

### Empty or Missing Response

1. Verify Codex CLI is available: `codex --help`
2. Ensure the MCP server is running: `codex mcp`
3. Confirm your MCP configuration in the assistant settings
4. Retry with a simpler prompt and escalate sandbox if needed

### Session ID Problems

**Error**:
`"Failed to parse session_id: invalid UUID format"`

**Root Cause**: Using invalid session ID format (e.g., "gpt-5", "session-1", etc.)

**Solutions**:

1. **Never manually create session IDs** - they must come from Codex MCP server
2. **Extract from direct response**: `response.structuredContent.sessionId`
3. **Use proper UUID format**: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
4. **Example of correct extraction**:
   ```python
   # From the codex tool response:
   session_id = response['structuredContent']['sessionId']
   # "12345678-1234-1234-1234-123456789abc"
   ```

**Common mistakes**:

- ❌ `sessionId="gpt-5"` (arbitrary string)
- ❌ `sessionId="session-1"` (custom format)
- ❌ `sessionId="urn:uuid:" + uuid` (don't add urn:uuid: prefix)
- ✅ `sessionId="12345678-1234-1234-1234-123456789abc"` (from response)