# CLAUDE.md

Claude Code guidance for this repository.

## Project Overview

Odoo 18 Enterprise project for Outboard Parts Warehouse (OPW). Custom addons for motor parts management with Shopify
integration.  
**Stack**: Python 3.12+, PostgreSQL 17, Owl.js 2.0, Docker, GraphQL  
**Documentation**:
See [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md) | [Testing](docs/TESTING.md) | [Style Guide](docs/STYLE_GUIDE.md)

## 🎯 PROACTIVE AGENT USAGE

**CRITICAL**: Claude should automatically use specialized agents. DO NOT use `subagent_type="general-purpose"`!

### When to Use Agents (Automatic Triggers)

| User Says                     | Agent Type | Syntax                       |
|-------------------------------|------------|------------------------------|
| Error/traceback/crash         | debugger   | `subagent_type="debugger"`   |
| "Write tests" / failing tests | scout      | `subagent_type="scout"`      |
| "Find how Odoo..." / research | archer     | `subagent_type="archer"`     |
| "Clean up" / refactor         | refactor   | `subagent_type="refactor"`   |
| Complex feature planning      | planner    | `subagent_type="planner"`    |
| Frontend/Owl.js issues        | owl        | `subagent_type="owl"`        |
| Docker/container issues       | dock       | `subagent_type="dock"`       |
| Code quality issues           | inspector  | `subagent_type="inspector"`  |
| Shopify integration           | shopkeeper | `subagent_type="shopkeeper"` |
| Performance issues            | flash      | `subagent_type="flash"`      |

### Agent Usage Pattern

```python
Task(
    description="Debug error",
    prompt="@docs/agents/debugger.md\n\n[error details]",
    subagent_type="debugger"  # Use specific agent name!
)
```

**See**: [@docs/agents/README.md](docs/agents/README.md) for complete agent guide

## ⚡ Agent-First Architecture (CRITICAL)

**Claude's Role**: Route tasks to specialist agents, coordinate work, maintain conversation context  
**Agents' Role**: Write code, implement features, research, analyze - the actual work

### Who Writes Code?

**✅ AGENTS write all code:**

- **Owl Agent** → Frontend code, CSS, JavaScript, Owl components
- **Scout Agent** → Test code, test files, test patterns
- **Refactor Agent** → Bulk code changes (coordinates with specialists)
- **Other Agents** → Domain-specific code within their expertise

**✅ CLAUDE orchestrates:**

- Route tasks to appropriate agents
- Coordinate multi-agent workflows
- Answer questions and provide guidance
- Review agent work for completeness

### Agent Routing Hierarchy

1. **AGENT DELEGATION FIRST** - Route to specialist
    - Odoo research → **Archer Agent**
    - Container ops → **Dock Agent**
    - Code quality → **Inspector Agent**
    - Frontend work → **Owl Agent**

2. **DIRECT TOOLS ONLY** - When no agent exists
    - Simple file reads: `Read`, `Grep`, `Glob`
    - Quick checks: `Bash` for basic commands

### Why Agent-First Matters

| Task Type     | Agent Route     | vs Direct Tools     | Benefit                    |
|---------------|-----------------|---------------------|----------------------------|
| Odoo research | Archer Agent    | Direct MCP tools    | Domain expertise + context |
| Code quality  | Inspector Agent | Manual tool usage   | Project-wide analysis      |
| Frontend work | Owl Agent       | Direct file editing | Framework knowledge        |

## 🚀 Quick Commands

- **Tests**: Route to Scout Agent - See [@docs/agents/scout.md](docs/agents/scout.md)
- **Format**: `ruff format . && ruff check . --fix` (Claude can run directly)
- **Quality**: Route to Inspector Agent - See [@docs/agents/inspector.md](docs/agents/inspector.md)
- **Containers**: Route to Dock Agent - See [@docs/agents/dock.md](docs/agents/dock.md)
- **Odoo Research**: Route to Archer Agent - See [@docs/agents/archer.md](docs/agents/archer.md)
- **Frontend Work**: Route to Owl Agent - See [@docs/agents/owl.md](docs/agents/owl.md)

## 🏗️ Architecture

**Addons**: `product_connect` (core), `disable_odoo_online`  
**Key Paths**: `./addons` (custom), Database: `opw`  
**DO NOT MODIFY**: `services/shopify/gql/*` (generated), `graphql/schema/*`

**Detailed Architecture**: See [@docs/agents/archer.md](docs/agents/archer.md) for research patterns

## 🔧 Development Workflow

1. **Route tasks to agents** - Don't do the work yourself, delegate to specialists
2. **Check containers** - Use [@docs/agents/dock.md](docs/agents/dock.md)
3. **Run tests** - Use [@docs/agents/scout.md](docs/agents/scout.md)
4. **Code quality** - Use [@docs/agents/inspector.md](docs/agents/inspector.md)

**AGENT FIRST RULE**: Before doing ANY work, ask "Which agent should handle this?" Route to specialists!

## ✅ Success Patterns

### Agent Routing Examples

```python
# ✅ RIGHT: Route code writing to specialist agent
Task(
    description="Fix frontend component",
    prompt="@docs/agents/owl.md\n\nFix this Owl component rendering issue: [code]",
    subagent_type="owl"
)

# ❌ WRONG: Claude writing frontend code directly
Edit("path/to/component.js", old_string="...", new_string="...")
```

### Complex Task Coordination

```python
# ✅ RIGHT: Use multiple agents for complex tasks
# 1. Research with Archer
archer_result = Task(description="Research pattern", prompt="@docs/agents/archer.md\n\nFind Odoo graph view patterns",
                     subagent_type="archer")

# 2. Implement with Owl  
Task(description="Implement component",
     prompt=f"@docs/agents/owl.md\n\nBased on research: {archer_result}\n\nImplement custom graph view",
     subagent_type="owl")

# 3. Test with Scout
Task(description="Write tests", prompt="@docs/agents/scout.md\n\nWrite tests for new graph component",
     subagent_type="scout")
```

### When Claude Acts Directly

**✅ ACCEPTABLE: Simple questions, coordination, file reads**

- Answer user questions about architecture
- Read files to understand context before routing
- Coordinate between multiple agents
- Run basic commands like `ruff format .`

**❌ NEVER: Write code when specialist agent exists**

- Don't write Owl components (use Owl agent)
- Don't write Python models (route to appropriate agent)
- Don't write tests (use Scout agent)

## 📋 Essential Links

- **All Agents**: [@docs/agents/README.md](docs/agents/README.md)
- **Testing Patterns**: [@docs/agents/scout.md](docs/agents/scout.md)
- **Odoo Research**: [@docs/agents/archer.md](docs/agents/archer.md)
- **Code Quality**: [@docs/agents/inspector.md](docs/agents/inspector.md)
- **Docker Operations**: [@docs/agents/dock.md](docs/agents/dock.md)
- **Style Standards**: [docs/STYLE_GUIDE.md](docs/STYLE_GUIDE.md) - Domain-specific style guides