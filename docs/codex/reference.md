# Codex MCP Reference

## What This Covers

- Model selection and when to use each
- Sandbox modes and recommended defaults
- Session management essentials
- Common issues and error handling

See also:

- Basic usage and examples: [usage.md](./usage.md)
- Advanced configuration: [advanced.md](./advanced.md)

## Model Selection (Provider‑Agnostic)

- `OPENAI_PRIMARY_MODEL` — Primary model to use when you need to override the CLI default.
- `OPENAI_LARGE_CONTEXT_MODEL` — Optional; set only if you have a configured large‑context model and a task truly needs it.

Guidance:
- Omit the `model` parameter to use the CLI’s configured default.
- Override only for specific requirements (e.g., very large context or provider‑specific features available in your account).

## Sandbox Modes

| Mode                 | Use Case                     | Permissions                     |
|----------------------|------------------------------|---------------------------------|
| `read-only`          | Analysis, exploration        | Read files only                 |
| `workspace-write`    | Implementation, file changes | Read/write files within project |
| `danger-full-access` | ⚠️ **AVOID** - Security risk | Full system + network access    |

**🚨 SECURITY WARNING**: `danger-full-access` grants unrestricted system access and should be **avoided**.

- Default: Use `workspace-write` for all tasks (includes network access, Docker, files, tests)
- `danger-full-access` provides no additional capabilities needed for normal development
- Never use in automated workflows or when handling untrusted code

## Session Management

- Initial `codex` call creates a session automatically.
- Session ID is returned in the direct response's `structuredContent.sessionId` field
- Session IDs are standard UUIDs: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
- Never manually create session IDs - always extract from the response
- Use the session ID with `mcp__codex__codex_reply` to maintain context across turns.
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

**Root Cause**: Using invalid session ID format (e.g., a model name, "session-1", etc.)

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

- ❌ `sessionId="model-name"` (arbitrary string)
- ❌ `sessionId="session-1"` (custom format)
- ❌ `sessionId="urn:uuid:" + uuid` (don't add urn:uuid: prefix)
- ✅ `sessionId="12345678-1234-1234-1234-123456789abc"` (from response)
