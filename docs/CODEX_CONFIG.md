# Codex Configuration Guide

## Configuration Locations

1. **Global Config**: `~/.codex/config.toml`
    - Contains profiles and default settings
    - Shared across all projects

2. **Project Config**: `.codex/config.toml`
    - Currently used for project documentation reference
    - Not for profiles (use global config)

## Available Profiles

### deep-reasoning

Best for complex multi-step tasks with deep reasoning:

- High reasoning effort for deep thinking
- Network access enabled
- Workspace write permissions
- Auto-approval of commands
- Uses gpt-5 with detailed summaries

```bash
# CLI usage
codex exec "Complex task" --profile deep-reasoning

# Via GPT agent
Task(
    prompt="Complex Odoo refactoring",
    subagent_type="gpt"
)
# GPT will use: profile="deep-reasoning"
```

### dev-standard

Standard development profile for typical tasks:

- Balanced performance with gpt-5
- Workspace write permissions
- Auto-approval of commands
- Suitable for most development work

```bash
# CLI usage
codex exec "Implement feature" --profile dev-standard

# Via GPT agent
Task(
    prompt="Add new model field",
    subagent_type="gpt"
)
# GPT will use: profile="dev-standard"
```

### test-runner

Specialized profile for test execution:

- Medium reasoning effort for test analysis
- Requires --sandbox workspace-write CLI flag
- Suitable for running and debugging tests
- Network access may be needed for external dependencies

```bash
# CLI usage (requires sandbox flag)
codex exec "Run tests" --profile test-runner --sandbox workspace-write

# Via GPT agent
Task(
    prompt="Run unit tests and analyze failures",
    subagent_type="gpt"
)
# GPT will use: profile="test-runner"
```

### safe-production

Safe mode for production environments and analysis:

- Medium reasoning effort for production tasks
- Requires approval for actions (on-request)
- No response storage for security
- Protects against accidental changes

```bash
# CLI usage
codex exec "Analyze production" --profile safe-production

# Via GPT agent
Task(
    prompt="Audit production database",
    subagent_type="gpt"
)
# GPT will use: profile="safe-production"
```

### quick

Lightweight profile for simple, fast tasks:

- Low reasoning effort for speed
- No reasoning summary for faster responses
- Suitable for simple implementations or fixes
- Optimized for quick iterations

```bash
# CLI usage
codex exec "Quick fix" --profile quick

# Via GPT agent
Task(
    prompt="Simple bug fix",
    subagent_type="gpt"
)
# GPT will use: profile="quick"
```

## Testing Configuration

Run the test script to verify setup:

```bash
./test_codex_config.sh
```

## Environment Variables

Codex can pass environment variables to commands:

- `PYTHONPATH`: Set to Odoo module paths
- `DATABASE`: Set to "${ODOO_DB_NAME}"

## Quick Commands

```bash
# Basic execution
codex exec "Your task"

# With profile
codex exec "Task" --profile deep-reasoning

# Override settings
codex exec "Task" -c 'model_reasoning_effort="high"'

# Sandbox mode via CLI flag (cannot be set in profiles)
codex exec "Task" --sandbox workspace-write

# Multiple config overrides
codex exec "Task" \
  -c 'model_reasoning_effort="high"' \
  -c 'shell_environment_policy.set={"DATABASE":"${ODOO_DB_NAME}"}'
```

## GPT Agent Usage

The GPT agent automatically selects appropriate profiles based on task:

- Complex/debugging tasks → `deep-reasoning`
- Test execution → `test-runner`
- Production/audit tasks → `safe-production`
- Simple tasks → `quick`
- Standard development → `dev-standard`

## Troubleshooting

1. **Profile not found**: Ensure profile is in `~/.codex/config.toml`, not project config
2. **Sandbox mode ignored**: Profiles cannot set sandbox mode - use CLI flags like `--sandbox workspace-write`
3. **Environment variables missing**: Use config overrides or set in profile
4. **Network access denied**: Enable in profile or use `workspace-write` sandbox
5. **Authentication errors**: Run `codex login` to refresh credentials

## Important Notes

### Sandbox Mode Limitations

**CRITICAL**: Sandbox mode cannot be set in profiles. Always use CLI flags:

```bash
# Correct: CLI flag
codex exec "Task" --profile deep-reasoning --sandbox workspace-write

# Correct: Config override
codex exec "Task" -c 'sandbox_mode="workspace-write"'

# Incorrect: Cannot be set in profile
[profiles.my-profile]
sandbox_mode = "workspace-write"  # THIS DOESN'T WORK
```