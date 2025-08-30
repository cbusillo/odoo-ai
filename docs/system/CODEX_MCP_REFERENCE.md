# Codex MCP Reference for Odoo Development

## Overview

This document provides quick reference for Codex MCP usage in the Odoo project context.

## Core Documentation Links

### Essential References

- **Model Selection**: [reference.md#model-selection](../codex/reference.md#model-selection)
- **Sandbox Modes**: [reference.md#sandbox-modes](../codex/reference.md#sandbox-modes)
- **Session Management**: [reference.md#session-management](../codex/reference.md#session-management)
- **Common Issues**: [reference.md#common-issues](../codex/reference.md#common-issues)

### Usage Guides

- **Basic Usage**: [usage.md](../codex/usage.md)
- **Advanced Features**: [advanced.md](../codex/advanced.md)
- **Agent Integration**: [gpt.md](../agents/gpt.md)

## Project-Specific Configuration

### Odoo Development Settings

When using Codex MCP for Odoo development, use these configurations:

```python
mcp__gpt-codex__codex(
    prompt="Your Odoo task",
    profile="deep-reasoning",  # For complex Odoo patterns
    sandbox="workspace-write",  # For code modifications
    cwd="/volumes/",  # Container path for Odoo
    config={
        "shell_environment_policy.set": {
            "ODOO_RC": "/volumes/odoo.local.conf",
            "PYTHONPATH": "/volumes/addons"
        }
    }
)
```

### Key Differences for Odoo

1. **Working Directory**: Use `/volumes/` (container path) not host paths
2. **Python Execution**: Never run Python directly, use Odoo's environment
3. **Database Context**: Include `--database ${ODOO_DB_NAME}` in Odoo commands
4. **Test Commands**: Use `uv run` commands defined in pyproject.toml

## Important Notes

### Session Management

- Codex MCP server runs in **compatibility mode** for synchronous responses
- Session IDs are returned directly in the response's `structuredContent.sessionId` field
- Direct tool calls return immediate responses with session information
- The GPT agent can extract session IDs from the response for multi-turn conversations

## Quick Reference

### Profile Selection for Odoo Tasks

- **quick**: Simple fixes, syntax errors
- **dev-standard**: Standard implementation, refactoring
- **deep-reasoning**: Complex architectural changes, optimization
- **test-runner**: Test execution and debugging
- **safe-production**: Production analysis and audits

### Sandbox Selection for Odoo Tasks

- **read-only**: Code analysis, pattern searches
- **workspace-write**: Implementation, refactoring (default)

Note: Package installation and system operations should be done directly in Claude Code.

## See Also

- Internal patterns: [gpt-session-patterns.md](../agent-patterns/gpt-session-patterns.md)
- Performance tips: [gpt-performance-patterns.md](../agent-patterns/gpt-performance-patterns.md)
- Odoo-specific guidelines: [ODOO_WORKFLOW.md](../ODOO_WORKFLOW.md)