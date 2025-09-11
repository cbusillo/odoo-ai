# Odoo Development Agents

This directory contains specialized instructions for sub-agents that handle specific aspects of Odoo development. Each
agent has focused knowledge to avoid context pollution and ensure expertise in their domain.

## Tool Selection

**See [Tool Selection Guide](../TOOL_SELECTION.md)** for complete decision tree and performance benchmarks.

**Quick reminder**: Prefer MCP tools (`mcp__*`) for structured outputs and reliability.

## Available Agents

| Agent | Name                   | Purpose                                  |
|-------|------------------------|------------------------------------------|
| 🏹    | **Archer**             | Odoo source research and pattern finding |
| 🔍    | **Scout**              | Test writing and test infrastructure     |
| 🔬    | **Inspector**          | Code quality and performance analysis    |
| 🔍    | **QC**                 | Multi-agent quality coordination         |
| 🚢    | **Dock**               | Docker and container operations          |
| 🛍️   | **Shopkeeper**         | Shopify integration and sync             |
| 🦉    | **Owl**                | Frontend development (Owl.js/JS)         |
| 🔥    | **Phoenix**            | Version migration and upgrades           |
| ⚡     | **Flash**              | Performance optimization                 |
| 🐛    | **Debugger**           | Error analysis and debugging             |
| 📋    | **Planner**            | Implementation planning                  |
| 🔧    | **Refactor**           | Bulk code improvements                   |
| 🎭    | **Playwright**         | Browser automation and UI testing        |
| 🧙    | **Odoo Engineer**      | Framework expertise                      |
| 🤖    | **Anthropic Engineer** | Claude optimization                      |
| 💬    | **GPT**                | External verification via Codex CLI      |
| 📝    | **Doc**                | Documentation maintenance                |

**Note**: Full trigger conditions and collaboration details are in each agent's description (visible in Task tool).

## Using Agents

Agents are invoked using the Task tool with their specialized documentation:

```python
Task(
    description="Find Odoo patterns",
    prompt="""
    @docs/agents/archer.md
    
    Find all models that inherit from product.template and override the create method.
    """,
    subagent_type="archer"
)
```

## Key Principles

1. **Focused Context**: Each agent only gets the information it needs
2. **Tool Expertise**: Agents know exactly which tools work best for their domain
3. **No Context Pollution**: Main conversation stays clean
4. **Parallel Work**: Launch multiple agents for different aspects of a task
5. **Do The Work**: Subagents apply changes and run tests; main thread coordinates

## Execution Norms (All Subagents)

- Prefer Edit/Write tools to modify files; if edit prompts cannot be approved in non‑interactive runs, fall back to Bash
  here‑docs for file writes.
- To run and gate tests reliably in one call, use `uv run test-gate --json` (exits 0/1). For targeted phases, use
  `uv run test-*` and read JSON summaries under `tmp/test-logs/latest/`.
- Keep changes small and focused; save long logs to `tmp/subagent-runs/<RUN_ID>/<agent>/`.
- Return a short summary: Decision • Diffs/Paths • Test results • Next steps • Risks.

## Common Patterns

### Research then Implement

```python
# First: Research with Archer
research_result = Task(
    description="Research patterns",
    prompt="@docs/agents/archer.md\n\nFind how Odoo implements graph views",
    subagent_type="archer"
)

# Then: Implement based on findings
implementation = Task(
    description="Implement feature",
    prompt=f"Based on this research: {research_result}\n\nImplement a custom graph view",
    subagent_type="owl"
)
```

### Quality Check Pipeline

```python
# Write code, then inspect
Task(
    description="Quality check",
    prompt="@docs/agents/inspector.md\n\nRun full inspection on product_connect module",
    subagent_type="inspector"
)
```

## Agent Effectiveness Metrics

For detailed performance benchmarks and real-world examples, see:

- [Tool Selection Guide](../TOOL_SELECTION.md) - Complete patterns, anti-patterns, and performance analysis
- Performance patterns: see [Flash agent](./flash.md) and [Odoo performance ORM](../odoo18/PERFORMANCE_ORM.md)

### Quick Summary

- **Speed**: Less parsing and fewer retries when using structured tools
- **Coverage**: Project-wide analysis vs single-file views
- **Quality**: Consistent, repeatable operations reduce mistakes
- **Development**: Cleaner contexts enable parallel work

### Key Improvements by Agent

- **Archer**: Instant codebase search vs 30+ seconds
- **Inspector**: Complete project analysis vs single file
- **Flash**: Finds all performance issues systematically
- **Scout**: Pre-validated test data prevents failures
- **Dock**: Zero container overhead, instant operations

## When to Use Agents vs Main Context

### Use Agents When:

✅ Task requires specialized knowledge (Docker paths, test patterns)
✅ Multiple similar operations (bulk testing, searching)
✅ Context is getting large (>50% through conversation)
✅ Need parallel execution of independent tasks
✅ Want clean, focused results without context pollution

### Use Main Context When:

✅ Quick questions with immediate answers
✅ Iterative development on same feature
✅ Need to maintain state between operations
✅ Simple file edits or reads
✅ Discussing architecture or planning

## Agent Collaboration

**Important**: Agents can and should call other agents (except themselves) when it helps complete the task. This enables
efficient task routing to specialists.

### Key Collaboration Principles:

1. **Cross-functional coordination**: Agents call specialists in other domains
2. **No recursive calls**: Agents cannot call themselves
3. **Context preservation**: Each agent works in its own context window
4. **Parallel execution**: Multiple agents can work simultaneously

### Common Collaboration Patterns:

| Primary Agent | Calls             | Purpose                                        |
|---------------|-------------------|------------------------------------------------|
| 🦉 Owl        | 🚢 Dock           | Restart containers after frontend changes      |
| 🔬 Inspector  | 🔧 Refactor       | Fix systematic issues found in analysis        |
| 📋 Planner    | 🏹 Archer         | Research patterns before planning              |
| 🐛 Debugger   | 🚢 Dock, 💬 GPT   | Get logs, analyze complex errors               |
| 🔧 Refactor   | 🏹 Archer, 🦉 Owl | Get patterns, delegate domain-specific changes |
| 🔍 Scout      | 🎭 Playwright     | Browser test debugging                         |

### Why This Matters:

- **Efficiency**: Tasks get routed to the right expert
- **Quality**: Each agent applies its specialized knowledge
- **Context**: Main conversation stays clean while agents work
- **Speed**: Parallel execution when tasks are independent

### Collaboration Matrix

| Agent                 | Can Call                        | Purpose                                                          |
|-----------------------|---------------------------------|------------------------------------------------------------------|
| 🤖 Anthropic Engineer | All agents                      | Demonstrate any workflow                                         |
| 📋 Planner            | 🏹 Archer                       | Research before planning                                         |
| 🦉 Owl                | 🚢 Dock, 🎭 Playwright          | Restart containers, debug UI issues                              |
| 🐛 Debugger           | 🚢 Dock, 💬 GPT                 | Get container logs, complex analysis                             |
| 🔧 Refactor           | 🏹 Archer, 🦉 Owl, 🔬 Inspector | Research patterns, delegate domain refactoring, validate results |
| 🔬 Inspector          | 🔧 Refactor                     | Recommend bulk fixes for systematic issues                       |
| Other agents          | Case-by-case                    | Route when tasks exceed their specialty                          |

### Example Collaboration:

```python
# Owl agent calling Dock after frontend changes
restart_task = Task(
    description="Apply frontend changes",
    prompt="@docs/agents/dock.md\n\nRestart web container to apply component changes",
    subagent_type="dock"
)

# Inspector finding bulk issues, routing to Refactor
if bulk_issues_found:
    refactor_task = Task(
        description="Fix systematic issues",
        prompt="@docs/agents/refactor.md\n\nFix these 20+ similar issues found by analysis",
        subagent_type="refactor"
    )
```

### Benefits:

- Agents stay focused on their core strength
- Complex workflows get expert attention at each step
- No single agent becomes a bottleneck

## Important Notes

- **Project-wide vs Single-file**:
    - `mcp__odoo-intelligence__*` = Entire project analysis
    - `mcp__jetbrains__*` = Current/single file only
- **Always include agent doc**: Use @mention to include the agent's instructions
- **Be specific**: Clear, focused prompts get better results
- **Check agent specialties**: Use the right agent for the job
- **Shared tools**: See `docs/system/SHARED_TOOLS.md` for tools ALL agents should know about
- **Model selection**: See `docs/system/MODEL_SELECTION.md` for model selection syntax and optimization
- **Agent safeguards**: See `docs/system/AGENT_SAFEGUARDS.md` for preventing recursive calls

## Tool Examples Reference

For detailed tool examples, performance comparisons, and anti-patterns, see:

- **[Tool Selection Guide](../TOOL_SELECTION.md)** - Complete decision trees and performance benchmarks
- **Performance patterns**: [Flash agent](./flash.md) and [Odoo performance ORM](../odoo18/PERFORMANCE_ORM.md)
- **[Codex Configuration](../CODEX_CONFIG.md)** - Profiles and settings for GPT agent (Codex CLI)
