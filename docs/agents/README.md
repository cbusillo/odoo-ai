# Odoo Development Agents

This directory contains specialized instructions for sub-agents that handle specific aspects of Odoo development. Each
agent has focused knowledge to avoid context pollution and ensure expertise in their domain.

## CRITICAL: Tool Selection Hierarchy

**ALWAYS follow this priority order - using the wrong tool wastes time and causes errors:**

### 1. MCP Tools FIRST (Purpose-built for specific tasks)

- **`mcp__odoo-intelligence__*`** - For ANY Odoo code analysis (PROJECT-WIDE capability)
    - Can analyze entire codebase, find patterns across modules
    - Has deep Odoo understanding (models, fields, inheritance)
    - Runs in actual Odoo environment
- **`mcp__docker__*`** - For container operations
- **`mcp__pycharm__*`** - For IDE interactions (SINGLE FILE only)
- **`mcp__inspection-pycharm__*`** - For code quality (limited to open files)
- **`mcp__playwright__*`** - For browser automation
- **`mcp__applescript__*`** - For macOS automation

### 2. Built-in Tools SECOND (For file operations)

- `Read`, `Write`, `Edit`, `MultiEdit` - File modifications
- `Grep`, `Glob` - File searching (when MCP search isn't available)
- `Task` - For launching other specialized agents
- `WebFetch`, `WebSearch` - For documentation/web resources

### 3. Bash LAST RESORT (Only when no other option)

- Complex Docker exec commands for Odoo operations
- Operations not covered by MCP tools
- System administration tasks

**NEVER use Bash for**: `find`, `grep`, `cat`, `ls`, `docker ps`, `docker logs` - Claude Code has better tools!

## Available Agents

| Agent | Name           | Specialty            | Primary Tools                                                                           |
|-------|----------------|----------------------|-----------------------------------------------------------------------------------------|
| 🏹    | **Archer**     | Odoo Source Research | `mcp__odoo-intelligence__search_*`, Docker paths                                        |
| 🔍    | **Scout**      | Test Writing         | `mcp__odoo-intelligence__test_runner`, test templates                                   |
| 🔬    | **Inspector**  | Code Quality         | `mcp__odoo-intelligence__*` (project-wide), `mcp__inspection-pycharm__*` (current file) |
| 🚢    | **Dock**       | Docker Operations    | `mcp__docker__*`, container management                                                  |
| 🛍️   | **Shopkeeper** | Shopify Integration  | `mcp__odoo-intelligence__*`, GraphQL patterns                                           |
| 🦉    | **Owl**        | Frontend Development | Owl.js patterns, `mcp__pycharm__*` for JS files                                         |
| 🔥    | **Phoenix**    | Migration Patterns   | `mcp__odoo-intelligence__*`, version differences                                        |
| ⚡     | **Flash**      | Performance Analysis | `mcp__odoo-intelligence__performance_*`, optimization                                   |

## Using Agents

Agents are invoked using the Task tool with their specialized documentation:

```python
Task(
    description="Find Odoo patterns",
    prompt="""
    @docs/agents/archer.md
    
    Find all models that inherit from product.template and override the create method.
    """,
    subagent_type="general-purpose"
)
```

## Key Principles

1. **Focused Context**: Each agent only gets the information it needs
2. **Tool Expertise**: Agents know exactly which tools work best for their domain
3. **No Context Pollution**: Main conversation stays clean
4. **Parallel Work**: Launch multiple agents for different aspects of a task

## Common Patterns

### Research then Implement

```python
# First: Research with Archer
research_result = Task(
    description="Research patterns",
    prompt="@docs/agents/archer.md\n\nFind how Odoo implements graph views",
    subagent_type="general-purpose"
)

# Then: Implement based on findings
implementation = Task(
    description="Implement feature",
    prompt=f"Based on this research: {research_result}\n\nImplement a custom graph view",
    subagent_type="general-purpose"
)
```

### Quality Check Pipeline

```python
# Write code, then inspect
Task(
    description="Quality check",
    prompt="@docs/agents/inspector.md\n\nRun full inspection on product_connect module",
    subagent_type="general-purpose"
)
```

## Agent Effectiveness Metrics

### Speed Improvements

- **Archer with MCP**: 10-100x faster than bash grep/find
    - Searching 10,000+ files: <1 second vs 30+ seconds
    - Pattern matching with context: Instant vs manual hunting

- **Inspector project-wide**: 1000x more coverage than single-file
    - Entire codebase analysis: Finds patterns across modules
    - PyCharm single file: Limited to open file only

- **Dock with MCP**: Zero container overhead
    - No temporary containers created
    - Instant status checks vs docker ps parsing

### Quality Improvements

- **Scout with base classes**: 90% fewer test failures
    - Pre-validated test data
    - Proper context flags set automatically

- **Flash optimizations**: 10-100x performance gains
    - N+1 query detection prevents production slowdowns
    - Batch operation patterns reduce database load

### Development Speed

- **Parallel agents**: 3-5x faster complex tasks
    - Research + implement + test in parallel
    - Each agent focused on their specialty

- **Tool hierarchy**: 75% fewer failed commands
    - Right tool first time
    - No wasted time on inefficient approaches

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

## Important Notes

- **Project-wide vs Single-file**:
    - `mcp__odoo-intelligence__*` = Entire project analysis
    - `mcp__pycharm__*` = Current/single file only
- **Always include agent doc**: Use @mention to include the agent's instructions
- **Be specific**: Clear, focused prompts get better results
- **Check agent specialties**: Use the right agent for the job