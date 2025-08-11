# Tool Selection Guide

## 30-Second Quick Decision

1. **Complex task?** → Route to specialized agent (preserves context)
2. **MCP tool exists?** → Use it (10-100x faster than alternatives)
3. **Simple file operation?** → Read/Write/Edit/Grep/Glob
4. **No other option?** → Bash (document why)

**Key Insight**: Agents work in separate contexts, keeping Claude's main window clean for coordination

## Common Tasks Reference

| Need to... | Use This | Not This | Why |
|------------|----------|----------|-----|
| Write tests | Scout agent | Write directly | Preserves context, knows patterns |
| Debug error | Debugger agent | Analyze in main context | Complex reasoning isolated |
| Find patterns | Archer agent | `grep -r` | Research in separate context |
| Frontend work | Owl agent | Edit JS directly | Framework expertise isolated |
| Code quality | Inspector agent | Manual review | Full analysis without bloat |
| Simple search | `mcp__odoo-intelligence__search_code()` | `bash grep` | Instant vs 30+ seconds |
| Container status | `mcp__docker__list_containers()` | `docker ps` | Structured data |
| Run tests | `mcp__odoo-intelligence__test_runner()` | `docker exec` | Proper environment |

## Why Agents First, Then MCP Tools

### Agents Preserve Context
- Each agent works in a **separate context window**
- Claude's main context stays clean for coordination
- Complex tasks don't bloat the conversation
- Multiple agents can work in parallel

### MCP Tools Are Fast
- **Speed**: 10-100x faster (0.3s vs 30s for searches)
- **Reliability**: Structured output, proper error handling
- **Context**: Understand Odoo relationships, not just text matching
- **Coverage**: Analyze entire codebase, not just visible files

## When Bash Is Actually OK

✅ **Use Bash when:**
- Running custom scripts (`tools/test_runner.py`)
- MCP doesn't support specific flags you need
- Complex piping operations
- One-off system administration

**Document your exception:**
```bash
# Using Bash because MCP doesn't support --dev=all flag
docker exec odoo-opw-web-1 /odoo/odoo-bin --dev=all --stop-after-init
```

## Tool Categories

### MCP Tools (`mcp__*`)
- **odoo-intelligence**: Odoo-specific operations (search, analysis, testing)
- **docker**: Container management (status, logs, deployment)
- **pycharm**: IDE operations (single file scope)
- **playwright**: Browser automation
- **chatgpt-automation**: AI consultation

### Built-in Tools
- **Read/Write/Edit/MultiEdit**: File operations
- **Grep/Glob**: Pattern matching (when MCP not available)
- **Task**: Launch specialized agents
- **WebFetch/WebSearch**: Documentation lookup

### Bash (Last Resort)
- Custom scripts in the repo
- System operations not covered by MCP
- Always document why MCP wasn't suitable

## Performance Impact

| Wrong Choice | Real Impact | Example |
|--------------|-------------|---------|
| `grep` instead of MCP | 30s wait | User watches spinner |
| Raw `docker` commands | Parse errors | Silent test failures |
| Manual file inspection | Missed bugs | Production issues |

## Need Help?

- **Not sure which tool?** → Check the quick reference above
- **Complex task?** → Route to appropriate agent
- **Tool not working?** → Document the issue, use fallback

Remember: Using the right tool makes development 3-5x faster. The few seconds to check this guide save minutes of waiting.