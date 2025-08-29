# AGENTS.md - Project Context for Codex CLI

## Style Guides

All style rules are documented in `docs/style/`:

- **[Core Rules](docs/style/CORE.md)** - Tool hierarchy, naming, git practices
- **[Python](docs/style/PYTHON.md)** - Type hints, f-strings, Odoo patterns
- **[JavaScript](docs/style/JAVASCRIPT.md)** - No semicolons, Owl.js 2.0
- **[Testing](docs/style/TESTING.md)** - Test patterns, SKU validation
- **[Odoo](docs/style/ODOO.md)** - Odoo 18 patterns, container paths

## Critical Rules

- **Python line length**: 133 characters max
- **JavaScript**: No semicolons, use Owl.js patterns
- **Tools**: ALWAYS use MCP tools over Bash (10-100x faster)
- **Git**: Use `git mv` to preserve history
- **Tests**: Run via `uv run` commands only
- **Formatting**: Use Ruff for Python, PyCharm/IntelliJ for JavaScript

## Commands

```bash
# Testing
uv run test-unit          # Unit tests
uv run test-integration   # Integration tests  
uv run test-tour          # Browser/UI tests
uv run test-all           # Full test suite

# Code Quality
uv run ruff format .      # Format Python
uv run ruff check --fix   # Fix Python issues
```

## Project Structure

- **Custom addons**: `./addons/`
- **Odoo version**: 18 Enterprise
- **DO NOT MODIFY**: `services/shopify/gql/*`, `graphql/schema/*` (if present)

## Container Paths

- **Host paths**: Project root directory
- **Container paths**: `/volumes/` (mapped from host)
- **Never run Python directly**: Always use Odoo environment

## Implementation Focus

This file provides context for Codex CLI implementation tasks.
For coordination and delegation patterns, see CLAUDE.md.

## Claude MCP

Use the Claude Code CLI via a direct MCP server (no file bridge).

- Requirements: Install the Claude Code CLI and make it available on PATH or set `CLAUDE_BIN`.
- MCP server: `node tmp/claude-mcp/src/server.js` (temporary location; will be externalized).
- Add to Codex: configure in `~/.codex/config.toml` under `[mcp.servers.claude-bridge]` with `command = "node"` and
  `args = ["<abs path>/tmp/claude-mcp/src/server.js"]`.

### Claude MCP Tools (for Codex)

- **claude_bridge_health**: Quick availability check; returns `{ ok, backend, version? | error? }`.
- **claude_bridge_mcp_list**: Lists Claude-registered MCP servers; returns `{ backend, code, parsed|raw }`.
- **claude_bridge_mcp_add**: `({ name, command, args?, scope?='user' })` → Registers an MCP server with Claude.
- **claude_bridge_mcp_remove**: `({ name, scope?='user' })` → Unregisters an MCP server from Claude.
- **claude_bridge_exec_safe**: `({ args[], env?, cwd? })` → Runs only whitelisted Claude CLI subcommands (`mcp`, `help`,
  `--version`, and supported chat flags). Not for arbitrary execution.
- **claude_bridge_echo_stream**: Test helper that emits streaming notifications with provided `chunks`.
- **claude_chat_prompt**:
  `({ prompt, outputFormat?, systemPrompt?, appendSystemPrompt?, allowedTools?, disallowedTools?, mcpConfig?, permissionMode?, permissionPromptTool?, env?, cwd?, verbose? })` →
  Single‑turn chat via Claude CLI.
- **claude_chat_continue**: Same flags as `prompt` (with optional `prompt?`); continues the most recent conversation.
- **claude_chat_resume**: `({ sessionId, ...promptFlags })` → Resumes a specific conversation by `sessionId`.

### Notes for Codex

- **Streaming (optional)**: Chat tools accept `stream: true`. When enabled, the server emits JSON‑RPC notifications
  `claude.chat/stream` with `{ streamId, source: 'stdout'|'stderr', chunk }`, followed by a final `tools/call` result
  `{ streamed: true }`.
- **Protocol**: Minimal JSON‑RPC (`initialize`, `tools/list`, `tools/call`) with additional notifications for streaming.
- **Execution safety**: `exec_safe` enforces an allowlist; sensitive env vars are filtered before spawning the Claude
  CLI.

### Client Integration (Streaming)

- **Call**: Use `tools/call` with `name = "claude_chat_prompt" | "claude_chat_continue" | "claude_chat_resume"` and
  `arguments.stream = true`.
- **Notifications**: Handle `method = "claude.chat/stream"` with `params = { streamId, source, chunk }` and render
  `stdout` progressively; surface `stderr` distinctly.
- **Finalize**: Treat the original `tools/call` reply with `{ streamed: true }` as completion for `streamId`.
- **JSON mode**: When `outputFormat = "json"`, buffer chunks and parse after completion, or provide a raw stream view.
- **Testing**: `claude_bridge_echo_stream({ chunks: ["one", "two"], delayMs: 10 })` emits stream notifications without
  requiring the Claude CLI.

### Errors & Schemas

- **Input schemas**: Each tool advertises an `inputSchema` (JSON‑schema‑like) in `tools/list`. The server validates
  params and returns `-32602 Invalid params` with `data.errors` when validation fails.
- **Standardized errors**:
    - `-32602 Invalid params` → `data: { errors: [{ path, reason, ... }] }`
    - `-32011 CLI_ERROR` → `data: { exitCode, stderr? }` when the Claude CLI exits non‑zero
- **Behavior**: On CLI errors during streaming, the server still emits any streamed chunks and then returns a JSON‑RPC
  error for the original `tools/call`.

## Web Search

Enable Codex web search by default via global config:

- `~/.codex/config.toml` additions:
    - `[tools]` → `web_search = true`
    - `[sandbox_workspace_write]` → `network_access = true`
- Effect: The built-in `web_search` tool is available and network is allowed in workspace-write mode, so Codex can
  research online without extra prompts.
