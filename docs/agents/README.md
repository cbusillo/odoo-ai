# Odoo Development Agents

This directory contains specialized instructions for sub-agents that handle specific aspects of Odoo development. Each
agent has focused knowledge to avoid context pollution and ensure expertise in their domain.

## Tool Selection

**See [Tool Selection Guide](../TOOL_SELECTION.md)** for complete decision tree and performance benchmarks.

**Quick reminder**: MCP tools (`mcp__*`) are 10-100x faster than Bash alternatives.


## Available Agents

| Agent | Name                   | Specialty               | Primary Tools                                                                           |
|-------|------------------------|-------------------------|-----------------------------------------------------------------------------------------|
| 🏹    | **Archer**             | Odoo Source Research    | `mcp__odoo-intelligence__search_*`, Docker paths                                        |
| 🔍    | **Scout**              | Test Writing            | `.venv/bin/python tools/test_runner.py` via Bash, test templates                        |
| 🔬    | **Inspector**          | Code Quality            | `mcp__odoo-intelligence__*` (project-wide), `mcp__inspection-pycharm__*` (current file) |
| 🔍    | **QC**                 | Quality Control         | Multi-agent coordination, enforcement, `mcp__odoo-intelligence__*`                      |
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
| 💬    | **GPT**                | ChatGPT Consultation    | `mcp__chatgpt_automation__*`, GPT-5 models, thinking mode, web search                   |
| 📝    | **Doc**                | Documentation Updates   | Maintain accurate docs, track changes, update guides                                    |

## Quick Agent Selection Guide

| Scenario                   | Primary Agent    | Supporting Agents                 |
|----------------------------|------------------|-----------------------------------|
| "Error in traceback"       | 🐛 Debugger      | 🚢 Dock (logs), 💬 GPT (analysis) |
| "Write tests for X"        | 🔍 Scout         | 🏹 Archer (examples)              |
| "Optimize performance"     | ⚡ Flash          | 🔬 Inspector (quality)            |
| "Fix code quality issues"  | 🔬 Inspector     | 🔧 Refactor (bulk fixes)          |
| "Quality audit/review"     | 🔍 QC            | 🔬 Inspector, ⚡ Flash, 🔍 Scout   |
| "Implement new feature"    | 📋 Planner       | 🏹 Archer (research)              |
| "Debug UI/browser issue"   | 🎭 Playwright    | 🦉 Owl (frontend)                 |
| "Shopify integration"      | 🛍️ Shopkeeper   | 🏹 Archer (patterns)              |
| "Frontend development"     | 🦉 Owl           | 🎭 Playwright (testing)           |
| "Container problems"       | 🚢 Dock          | 🐛 Debugger (logs)                |
| "Complex code review"      | 💬 GPT           | 🔬 Inspector (quality)            |
| "Migration issues"         | 🔥 Phoenix       | 🏹 Archer (patterns)              |
| "Architecture design"      | 🧙 Odoo Engineer | 📋 Planner (implementation)       |
| **"Large implementation"** | 💬 **GPT (4.1)** | **Claude analyzes, GPT codes**    |
| "Update documentation"     | 📝 Doc           | 🏹 Archer (technical details)     |

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

For detailed performance benchmarks and real-world examples, see:

- [Tool Selection Performance Guide](../TOOL_SELECTION_PERFORMANCE_GUIDE.md) - Complete patterns and anti-patterns
- [Performance Reference Guide](../PERFORMANCE_REFERENCE.md) - Agent-specific improvements

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

## Agent Collaboration (Your Team Works Together!)

**Important**: Agents can and should call other agents (except themselves) when it helps complete the task. This is how your team collaborates effectively.

### Key Collaboration Principles:

1. **Cross-functional teamwork**: Agents call specialists in other domains
2. **No recursive calls**: Agents cannot call themselves
3. **Context preservation**: Each agent works in its own context window
4. **Parallel execution**: Multiple agents can work simultaneously

### Common Collaboration Patterns:

| Primary Agent | Calls | Purpose |
|---------------|-------|---------|
| 🦉 Owl | 🚢 Dock | Restart containers after frontend changes |
| 🔬 Inspector | 🔧 Refactor | Fix systematic issues found in analysis |
| 📋 Planner | 🏹 Archer | Research patterns before planning |
| 🐛 Debugger | 🚢 Dock, 💬 GPT | Get logs, analyze complex errors |
| 🔧 Refactor | 🏹 Archer, 🦉 Owl | Get patterns, delegate domain-specific changes |
| 🔍 Scout | 🎭 Playwright | Browser test debugging |

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
    - `mcp__pycharm__*` = Current/single file only
- **Always include agent doc**: Use @mention to include the agent's instructions
- **Be specific**: Clear, focused prompts get better results
- **Check agent specialties**: Use the right agent for the job
- **Shared tools**: See `docs/agents/SHARED_TOOLS.md` for tools ALL agents should know about
- **Model selection**: See `docs/agents/MODEL_SELECTION_GUIDE.md` for model selection syntax and optimization
- **Agent safeguards**: See `docs/agents/AGENT_SAFEGUARDS.md` for preventing recursive calls

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