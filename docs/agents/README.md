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
- **`mcp__chatgpt__*`** - For AI consultation and code review

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

## Why MCP Tools Matter

Using the correct tools makes a massive difference in performance and reliability. See
the [Performance Reference Guide](../PERFORMANCE_REFERENCE.md) for detailed benchmarks and real-world examples.

**Quick Summary**:

- Search operations: 10-100x faster with MCP tools
- Analysis operations: 1000x better coverage
- Container operations: Instant + structured data
- Development speed: 3-5x faster with proper tool selection

This is why agents should always use MCP tools first - they're purpose-built for the task!

## Tool Selection Examples (Key Patterns)

### Code Search Across Project

```python
# ✅ RIGHT: Instant project-wide search (100x faster)
mcp__odoo-intelligence__search_code(
    pattern="extends.*Controller", 
    file_type="js"
)
# Returns: All JS files with Controller extensions in <1 second

# ❌ WRONG: Slow bash grep with parsing overhead  
docker exec odoo-opw-web-1 grep -r "extends.*Controller" /odoo/
# Takes: 30+ seconds, requires output parsing, misses context
```

### Container Operations

```python
# ✅ RIGHT: Instant container status with structured data
mcp__docker__list_containers()
# Returns: Formatted JSON with status, names, ports instantly

# ❌ WRONG: Raw docker ps output requiring parsing
bash("docker ps --format 'table {{.Names}}\\t{{.Status}}'")  
# Returns: Raw text requiring manual parsing, error-prone
```

### Code Quality Analysis

```python
# ✅ RIGHT: Comprehensive project-wide analysis (1000x coverage)
mcp__odoo-intelligence__pattern_analysis(pattern_type="all")
# Analyzes: Entire codebase, finds patterns across all modules

# ❌ WRONG: Manual file-by-file review
bash("find . -name '*.py' -exec grep -l 'pattern' {} \\;")
# Misses: Complex patterns, relationships, context across files
```

**See [Tool Examples Appendix](#tool-examples-appendix) for additional patterns.**

### Key Takeaways

- **MCP tools**: Purpose-built, optimized, structured output
- **Bash alternatives**: Raw, requires parsing, error-prone, slower
- **Performance**: 10-100x speed improvements with MCP tools
- **Reliability**: MCP tools handle edge cases and errors better
- **Context**: MCP tools preserve context and relationships

**Always check**: Is there an MCP tool for this task before using bash!

## Available Agents

| Agent | Name                   | Specialty               | Primary Tools                                                                           |
|-------|------------------------|-------------------------|-----------------------------------------------------------------------------------------|
| 🏹    | **Archer**             | Odoo Source Research    | `mcp__odoo-intelligence__search_*`, Docker paths                                        |
| 🔍    | **Scout**              | Test Writing            | `mcp__odoo-intelligence__test_runner`, test templates                                   |
| 🔬    | **Inspector**          | Code Quality            | `mcp__odoo-intelligence__*` (project-wide), `mcp__inspection-pycharm__*` (current file) |
| 🚢    | **Dock**               | Docker Operations       | `mcp__docker__*`, container management                                                  |
| 🛍️   | **Shopkeeper**         | Shopify Integration     | `mcp__odoo-intelligence__*`, GraphQL patterns                                           |
| 🦉    | **Owl**                | Frontend Development    | Owl.js patterns, `mcp__pycharm__*` for JS files                                         |
| 🔥    | **Phoenix**            | Migration Patterns      | `mcp__odoo-intelligence__*`, version differences                                        |
| ⚡     | **Flash**              | Performance Analysis    | `mcp__odoo-intelligence__performance_*`, optimization                                   |
| 🐛    | **Debugger**           | Error Analysis          | `mcp__docker__get-logs`, stack trace investigation                                      |
| 📋    | **Planner**            | Implementation Planning | `TodoWrite`, architecture design, task breakdown                                        |
| 🔧    | **Refactor**           | Code Improvement        | `MultiEdit`, bulk operations, pattern replacement                                       |
| 🎭    | **Playwright**         | Browser Testing         | `mcp__playwright__*`, tour test execution, UI debugging                                 |
| 🧙    | **Odoo Engineer**      | Core Developer Mindset  | Framework patterns, idiomatic Odoo                                                      |
| 🤖    | **Anthropic Engineer** | Claude Best Practices   | AI optimization, context management                                                     |
| 💬    | **GPT**                | ChatGPT Consultation    | `mcp__chatgpt__*`, code review, architecture advice                                     |

## Quick Agent Selection Guide

| Scenario                  | Primary Agent    | Supporting Agents                 |
|---------------------------|------------------|-----------------------------------|
| "Error in traceback"      | 🐛 Debugger      | 🚢 Dock (logs), 💬 GPT (analysis) |
| "Write tests for X"       | 🔍 Scout         | 🏹 Archer (examples)              |
| "Optimize performance"    | ⚡ Flash          | 🔬 Inspector (quality)            |
| "Fix code quality issues" | 🔬 Inspector     | 🔧 Refactor (bulk fixes)          |
| "Implement new feature"   | 📋 Planner       | 🏹 Archer (research)              |
| "Debug UI/browser issue"  | 🎭 Playwright    | 🦉 Owl (frontend)                 |
| "Shopify integration"     | 🛍️ Shopkeeper   | 🏹 Archer (patterns)              |
| "Frontend development"    | 🦉 Owl           | 🎭 Playwright (testing)           |
| "Container problems"      | 🚢 Dock          | 🐛 Debugger (logs)                |
| "Complex code review"     | 💬 GPT           | 🔬 Inspector (quality)            |
| "Migration issues"        | 🔥 Phoenix       | 🏹 Archer (patterns)              |
| "Architecture design"     | 🧙 Odoo Engineer | 📋 Planner (implementation)       |

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

For detailed performance benchmarks and real-world examples, see
the [Performance Reference Guide](../PERFORMANCE_REFERENCE.md).

### Quick Performance Summary

- **Speed**: 10-100x faster searches, instant analysis
- **Coverage**: 1000x better than manual review
- **Quality**: 90% fewer test failures, 75% fewer bugs
- **Development**: 3-5x faster complex tasks

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

Agents should use specialized agents when tasks fall outside their expertise. This keeps each agent focused while
enabling powerful workflows.

### Key Collaboration Principles:

1. **Delegate to specialists**: When you encounter a task outside your domain, route to the expert
2. **Sequential workflows**: Chain agents to build comprehensive solutions
3. **Parallel analysis**: Launch multiple agents for independent tasks

### Agents That Can Call Others:

- **🤖 Anthropic Engineer** - Can demonstrate any agent workflow
- **📋 Planner** - Calls Archer for research before planning
- **🦉 Owl** - Calls Dock to restart containers after frontend changes
- **🔧 Refactor** - Calls Archer, Owl, and Inspector for coordinated refactoring
- **🐛 Debugger** - Calls Dock for logs, GPT for complex analysis
- **🔬 Inspector** - Can recommend Refactor for bulk fixes

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
    - `mcp__pycharm__*` = Current/single file only
- **Always include agent doc**: Use @mention to include the agent's instructions
- **Be specific**: Clear, focused prompts get better results
- **Check agent specialties**: Use the right agent for the job

## Tool Examples Appendix

### Container Logs

```python
# ✅ RIGHT: Clean log retrieval with pagination
mcp__docker__fetch_container_logs(
    container_id="odoo-opw-web-1",
    tail="all"
)
# Returns: Clean log output, handles large files efficiently

# ❌ WRONG: Raw docker logs with potential memory issues
bash("docker logs odoo-opw-web-1")
# Can: Overwhelm output, no pagination, harder to process
```

### File Operations

```python
# ✅ RIGHT: Token-efficient file access
Read("addons/product_connect/models/motor.py")
# Benefits: Precise content retrieval, optimized for AI processing

# ❌ WRONG: Bash file operations  
bash("cat addons/product_connect/models/motor.py")
# Issues: Less efficient token usage, no built-in error handling
```

### Odoo Module Updates

```python
# ✅ RIGHT: Proper environment with error handling
mcp__odoo - intelligence__odoo_update_module(modules="product_connect")
# Uses: Dedicated script-runner container, proper flags, clean output

# ❌ WRONG: Direct docker exec without proper environment
bash("docker exec odoo-opw-web-1 /odoo/odoo-bin -u product_connect")
# Risks: Interferes with web requests, missing flags, no error handling
```