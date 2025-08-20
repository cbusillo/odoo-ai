# Codex MCP Reference for Odoo-OPW

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
- **Agent Integration**: [gpt-codex.md](../agents/gpt-codex.md)

## Project-Specific Configuration

### Odoo Development Settings

When using Codex MCP for Odoo development, use these configurations:

```python
mcp__gpt-codex__codex(
    prompt="Your Odoo task",
    model="gpt-5",  # Default, or "gpt-4.1" for 1M+ context
    sandbox="workspace-write",  # For code modifications
    cwd="/volumes/",  # Container path for Odoo
    config={
        "model_reasoning_effort": "high",  # For complex Odoo patterns
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
3. **Database Context**: Include `--database opw` in Odoo commands
4. **Test Commands**: Use `uv run` commands defined in pyproject.toml

## Quick Reference

### Model Priority (Same as Global)

1. **gpt-5** - Primary choice for most tasks
2. **gpt-4.1** - Alternative with 1M+ token context (use when gpt-5 unavailable or context exceeds 400K)
3. **gpt-4.5** - Additional fallback option when needed

### Sandbox Selection for Odoo Tasks

- **read-only**: Code analysis, pattern searches
- **workspace-write**: Implementation, refactoring (default)
- **danger-full-access**: Package installation, API testing

## See Also

- Internal patterns: [gpt-session-patterns.md](../agent-patterns/gpt-session-patterns.md)
- Performance tips: [gpt-performance-patterns.md](../agent-patterns/gpt-performance-patterns.md)
- Odoo-specific guidelines: [ODOO_WORKFLOW.md](../ODOO_WORKFLOW.md)