# 🤖 Anthropic Engineer - Detailed AI Assistant Best Practices

This file contains detailed patterns and examples extracted from the Anthropic Engineer agent documentation.

## Claude Code Post-Training Resources

**IMPORTANT**: Claude Code was released after Claude's knowledge cutoff. For current information:

- **Official Documentation**: https://docs.anthropic.com/en/docs/claude-code/overview
- **GitHub Repository**: https://github.com/anthropics/claude-code
- **Latest Features**: Check GitHub releases and issues for post-training updates
- **Community Patterns**: GitHub discussions for real-world usage patterns

### Staying Current with Post-Training Updates

```python
# Check for latest Claude Code capabilities
WebFetch(
    url="https://docs.anthropic.com/en/docs/claude-code",
    prompt="What new features or patterns were added recently?"
)

# Verify against GitHub for community patterns
WebFetch(
    url="https://github.com/anthropics/claude-code",
    prompt="What are the latest issues, discussions, or examples?"
)
```

## Claude Code CLI Deep Dive

### MCP (Model Context Protocol) Management

#### Core Commands Reference

```bash
# List and check MCP server health
claude mcp list

# Add an MCP server (user-scoped/global)
claude mcp add -s user server-name command

# Add MCP with JSON configuration
claude mcp add-json -s user server-name '{"command": "cmd", "args": ["arg1"]}'

# Remove an MCP server
claude mcp remove -s user server-name

# Check Claude Code version
claude --version
```

#### Python MCP Setup Patterns

```bash
# PREFERRED: uv-based Python projects (environment isolation)
claude mcp add-json -s user python-mcp-server '{
  "command": "uv", 
  "args": ["run", "--project", "/absolute/path/to/project", "entry-point"]
}'

# Alternative: Direct .venv path (less robust)
claude mcp add -s user server-name /path/to/project/.venv/bin/python /path/to/script.py

# One-off tools with uvx:
claude mcp add -s user docker uvx mcp-server-docker
```

#### Why Prefer `uv run`?

- **Environment isolation**: Ensures correct Python environment
- **Dependency management**: Handles virtual environments automatically
- **Cross-platform**: Works consistently across systems
- **Future-proof**: uv is becoming the Python project standard

### Staying Current with Claude Code

```bash
# Check Claude Code version regularly
claude --version

# When updates happen:
# 1. Check GitHub releases: https://github.com/anthropics/claude-code/releases
# 2. Use WebFetch for latest documentation
# 3. Update agent docs with new features
# 4. Test MCP configurations still work
# 5. Check official docs for API changes
```

### Version-Aware Documentation Updates

```python
# Check for new features before updating docs
WebFetch(
    url="https://docs.anthropic.com/en/docs/claude-code/overview",
    prompt="What new features were added in the latest version?"
)

# Check GitHub for community patterns and issues
WebFetch(
    url="https://github.com/anthropics/claude-code/issues",
    prompt="What common issues or new patterns are being discussed?"
)

# Update agent docs when capabilities change
Task(
    description="Update agent capabilities",
    prompt="@docs/agents/scout.md\n\nAdd new test runner features from latest release",
    subagent_type="scout"
)
```

## AI Design Thinking Process

### When designing AI workflows, consider:

1. **Context efficiency**
    - Is context being used wisely?
    - Are we repeating information unnecessarily?
    - Should we use specialized agents?

2. **Tool selection**
    - Are we using the most efficient tool?
    - Is the tool hierarchy being followed?
    - Can we batch operations?

3. **User experience**
    - Is the output concise and actionable?
    - Are we showing progress appropriately?
    - Is the interaction natural?

## Tool Use Optimization Patterns

### Batch Operations (Efficient)

```python
# GOOD: Batch operations
results = []
for file in files:
    results.append(Read(file))  # All sent in one message

# BAD: Sequential operations
result1 = Read(file1)
# Wait for response
result2 = Read(file2)
# Wait for response
```

### Context Management Patterns

```python
# Use specialized agents for focused tasks
Task(
    description="Research Odoo patterns",
    prompt="@docs/agents/archer.md\n\nFind how Odoo implements wizard patterns",
    subagent_type="archer"
)

# Don't pollute main context with specialized knowledge
```

### Communication Patterns

```
# GOOD: Concise, actionable
Fixed the import error in motor.py by adding the missing module.

# BAD: Verbose explanation
I've analyzed the error and determined that it was caused by a missing 
import statement. After reviewing the codebase, I found that the module
needed to be imported from...
```

## Documentation Structure Optimization

### Recommended Structure

1. **CLAUDE.md** - Core instructions, kept minimal
2. **Agent docs** - Specialized knowledge, detailed
3. **Slash commands** - Quick access patterns
4. **Success patterns** - What works, not what fails

### Agent Design Principles

```yaml
# Each agent should have:
expertise: "Clear domain focus"
tools: "Specific tool preferences"
patterns: "Proven success examples"
context: "Only relevant information"
```

## Performance Optimization Strategies

### Tool Hierarchy (Follow This Order)

1. **MCP tools first** (purpose-built)
2. **Built-in tools second** (efficient)
3. **Bash last resort** (overhead)

### Parallel Operations

- Batch file reads
- Multiple searches
- Concurrent agents

### Token Efficiency

- Concise responses
- No unnecessary preambles
- Focus on user's specific ask

## Common Antipatterns and Fixes

### 1. Context Pollution

```python
# BAD: Everything in main conversation

# GOOD: Specialized agents
Task(description="Research", prompt="@archer.md\n\nFind X")
```

### 2. Inefficient Tool Use

```python
# BAD: Bash for everything
docker
exec - it
container
grep - r
"pattern"

# GOOD: Purpose-built tools
mcp__odoo - intelligence__search_code(pattern="pattern")
```

### 3. Verbose Outputs

```
# BAD: Long explanations
"I'll help you with that. First, let me explain..."

# GOOD: Direct action
"Running tests now."
```

## MCP Configuration Best Practices

### Preferred Patterns

```bash
# ✅ GOOD: Absolute paths, uv for Python
claude mcp add-json -s user my-server '{
  "command": "uv",
  "args": ["run", "--project", "/Users/me/project", "server"]
}'

# ❌ AVOID: Relative paths, direct Python calls
claude mcp add -s user my-server python ./script.py
```

## Debugging Claude Performance Issues

### When Claude struggles:

1. **Check context size** - Over 50%? Use agents
2. **Review tool selection** - Following hierarchy?
3. **Examine patterns** - Using success examples?
4. **Validate assumptions** - Verifying against real code?

### Performance Tips

- Pre-filter with MCP tools before reading files
- Use regex in search tools effectively
- Cache common operations in slash commands
- Design agents to be stateless and focused
- Keep documentation current with Claude Code updates
- Use `uv run` for reliable Python MCP environments

## Documentation Maintenance Workflow

### When Claude Code Updates

1. **Check version**: `claude --version`
2. **Review changes**: Check GitHub releases and changelog
3. **Update practices**: Use WebFetch on docs.anthropic.com and GitHub
4. **Test MCPs**: Verify existing configurations work
5. **Update agents**: Add new capabilities to agent docs
6. **Check community**: Review GitHub issues for new patterns or breaking changes
7. **Verify examples**: Test that documented patterns still work

## The Anthropic Way

1. **Helpful** - Solve the actual problem
2. **Harmless** - Respect system resources and user intent
3. **Honest** - Acknowledge limitations and uncertainties

Remember: The best AI assistant is one that gets out of the way and lets users accomplish their goals efficiently.