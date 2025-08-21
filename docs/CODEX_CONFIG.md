# Codex Configuration Guide

## Configuration Locations

1. **Global Config**: `~/.codex/config.toml`
    - Contains profiles and default settings
    - Shared across all projects

2. **Project Config**: `.codex/config.toml`
    - Currently used for project documentation reference
    - Not for profiles (use global config)

## Available Profiles

### odoo-high-performance

Best for complex Odoo development tasks:

- High reasoning effort for deep thinking
- Network access enabled
- Workspace write permissions
- Auto-approval of commands

```bash
# CLI usage
codex exec "Complex task" --profile odoo-high-performance

# Via GPT agent
Task(
    prompt="Complex Odoo refactoring",
    subagent_type="gpt"
)
# GPT will use: profile="odoo-high-performance"
```

### odoo-production

Safe mode for production environments:

- Read-only sandbox
- Requires approval for actions
- No automatic command execution
- Protects against accidental changes

```bash
# CLI usage
codex exec "Analyze production" --profile odoo-production

# Via GPT agent
Task(
    prompt="Audit production database",
    subagent_type="gpt"
)
# GPT will use: profile="odoo-production"
```

## Testing Configuration

Run the test script to verify setup:

```bash
./test_codex_config.sh
```

## Environment Variables

Codex can pass environment variables to commands:

- `PYTHONPATH`: Set to Odoo module paths
- `DATABASE`: Set to "opw"

## Quick Commands

```bash
# Basic execution
codex exec "Your task"

# With profile
codex exec "Task" --profile odoo-high-performance

# Override settings
codex exec "Task" -c 'model_reasoning_effort="high"'

# Multiple overrides
codex exec "Task" \
  -c 'sandbox_mode="read-only"' \
  -c 'shell_environment_policy.set={"DATABASE":"opw"}'
```

## GPT Agent Usage

The GPT agent automatically selects appropriate profiles based on task:

- Complex/debugging tasks → `odoo-high-performance`
- Production/audit tasks → `odoo-production`
- Default tasks → Standard settings

## Troubleshooting

1. **Profile not found**: Ensure profile is in `~/.codex/config.toml`, not project config
2. **Environment variables missing**: Use config overrides or set in profile
3. **Network access denied**: Enable in profile or use `danger-full-access` sandbox
4. **Authentication errors**: Run `codex login` to refresh credentials