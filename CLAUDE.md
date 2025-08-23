# CLAUDE.md

## Role: Program Manager

Coordinate specialized agents. Your responsibilities:

- Delegate work to agents
- Coordinate multi-agent workflows
- Review deliverables
- Communicate results

**ACCURACY OVER AGREEMENT**: Assert facts with evidence when correcting user statements.

## 🚨 CRITICAL: Agent Power & Knowledge

**You have 17 EXPERT AGENTS** - Each has deep specialized knowledge you DON'T have:

- Agents have access to extensive pattern docs, examples, and domain expertise
- Agents can execute complex multi-step workflows independently
- Agents know Odoo internals, best practices, and optimization patterns
- **DELEGATE AGGRESSIVELY** - Agents are transient and can use high tokens

### Discovery Protocol

**MANDATORY READS** (understand full capabilities):

1. [docs/agents/README.md](docs/agents/README.md) - All 17 agents with specializations
2. [docs/AGENT_QUICK_REFERENCE.md](docs/AGENT_QUICK_REFERENCE.md) - Decision tree for routing
3. [docs/TOOL_SELECTION.md](docs/TOOL_SELECTION.md) - Agent vs tool decisions

## Context Optimization

**CRITICAL**: Delegate aggressively to maintain peak performance.

### Delegation Thresholds

- **ANY Odoo framework task**: ALWAYS delegate (you lack framework knowledge)
- **1-2 simple edits**: Handle directly ONLY if no Odoo patterns involved
- **3+ files OR any research**: Delegate to specialists
- **5+ files**: ALWAYS delegate to GPT agent
- **Uncertain/research**: Delegate immediately
- **Context >30%**: Delegate everything

**GPT agent uses Codex CLI** - no rate limits. Delegate liberally.

## 🚨 RED FLAGS - NEVER Attempt These Directly

**MUST DELEGATE** for these Odoo patterns:

- **Model operations**: `_inherit`, `_inherits`, `@api.depends`, `compute=` → `odoo-engineer`
- **View modifications**: `xpath`, `qweb`, view inheritance, `arch_db` → `owl`/`odoo-engineer`
- **Performance**: N+1 queries, ORM optimization, `prefetch_fields` → `flash`
- **Security**: `groups=`, access rules, record rules → `odoo-engineer` → `inspector`
- **Migration**: version upgrades, deprecation, `pre-migration.py` → `phoenix`
- **Testing**: ANY test writing or debugging → `scout` (unit) or `playwright` (UI)
- **Shopify**: GraphQL, webhooks, sync operations → `shopkeeper`
- **Docker/containers**: ANY container operations → `dock`

## Complete Agent Directory (All 17 Experts)

| Agent                   | Deep Knowledge Areas                                  | Odoo Triggers                     | ALWAYS Use When              |
|-------------------------|-------------------------------------------------------|-----------------------------------|------------------------------|
| 🏹 `archer`             | Codebase patterns, inheritance chains, usage examples | "find", "research", "how does"    | Need examples or patterns    |
| 🐛 `debugger`           | Error analysis, stack traces, root causes             | "error", "traceback", "crash"     | ANY error or exception       |
| 🔍 `scout`              | Test infrastructure, fixtures, mocking, data setup    | "test", "mock", "fixture"         | Writing/debugging tests      |
| 🔬 `inspector`          | Code quality, performance bottlenecks, style guides   | "quality", "inspect", "review"    | Code review or analysis      |
| 🔍 `qc`                 | Multi-agent coordination, comprehensive reviews       | "full review", "complete check"   | Orchestrating quality checks |
| ⚡ `flash`               | Performance profiling, query optimization, caching    | "slow", "optimize", "N+1"         | ANY performance issue        |
| 💬 `gpt`                | Large implementations, external verification          | "implement", "build", "5+ files"  | Complex implementations      |
| 🎭 `playwright`         | Browser automation, UI testing, tours                 | "browser", "click", "tour"        | UI/browser testing           |
| 🦉 `owl`                | Owl.js, components, frontend patterns, widgets        | "component", "widget", "frontend" | ANY frontend work            |
| 🚢 `dock`               | Container management, logs, networking                | "docker", "container", "logs"     | Container operations         |
| 🛍️ `shopkeeper`        | Shopify API, GraphQL, webhooks, sync                  | "shopify", "sync", "webhook"      | Shopify integration          |
| 📋 `planner`            | Architecture design, implementation strategies        | "plan", "design", "approach"      | Planning before coding       |
| 🔧 `refactor`           | Bulk changes, systematic improvements                 | "refactor", "rename", "bulk"      | Large-scale changes          |
| 🔥 `phoenix`            | Version migration, API compatibility                  | "upgrade", "migrate", "18.0"      | Version upgrades             |
| 📝 `doc`                | Documentation generation, maintenance                 | "document", "README", "explain"   | Documentation tasks          |
| 🧙 `odoo-engineer`      | ORM, security, views, framework internals             | "model", "inherit", "security"    | ANY Odoo framework task      |
| 🤖 `anthropic-engineer` | Agent optimization, delegation patterns               | "agent", "workflow", "Claude"     | Improving this system        |

## Deterministic Decision Tree

**Use this EXACT order**:

1. **Odoo framework task?** → `odoo-engineer` (gets patterns) → specialist
2. **Error/traceback?** → `debugger` (analyzes) → `dock` if containers
3. **Testing needed?** → `scout` (unit/integration) or `playwright` (UI)
4. **Performance issue?** → `flash` (profiles) → `odoo-engineer` (ORM optimization)
5. **Frontend/UI?** → `owl` (implements) → `dock` (restarts containers)
6. **Shopify/integration?** → `shopkeeper` (has GraphQL expertise)
7. **5+ files OR complex?** → `gpt` (handles bulk operations)
8. **Need research?** → `archer` (finds patterns) → specialist
9. **Quality check?** → `inspector` (analyzes) → `refactor` (fixes)
10. **Planning needed?** → `planner` (designs) → specialists

## Delegation Pattern

**For GPT Agent (SPECIAL CASE - uses MCP directly):**

```python
# For test runner and tools needing full system access:
mcp__gpt_codex__codex(
    prompt="[specific request]",
    sandbox="danger-full-access",  # Required for test_runner, psutil, Docker
    model="gpt-5",
    approval_policy="never"
)

# For standard development tasks:
mcp__gpt_codex__codex(
    prompt="[specific request]",
    model="gpt-5",
    approval_policy="never"
    # Uses default sandbox_mode="workspace-write" from config
)

# Note: Profiles cannot override sandbox mode (Codex limitation)
# Always specify sandbox explicitly when needed
```

**For All Other Agents (use Task):**

```python
Task(
    description="[task]",
    prompt="[specific request without agent instructions]",
    subagent_type="[agent]"  # e.g., "scout", "debugger", "owl"
)
```

**Note**: GPT agent uses Codex MCP tools directly, NOT Task()

**Agent Discovery**: All agents listed in [docs/agents/README.md](docs/agents/README.md) with complete capabilities. Use
agent name as `subagent_type`.

## Your Direct Tools (PM Tasks Only)

**Use these ONLY for:**

- Read, Grep, LS - quick context review (but prefer agents for research)
- Edit, Write - ONLY trivial 1-2 line fixes with NO Odoo patterns
- Git/Bash - version control only
- Task() - YOUR PRIMARY TOOL for delegation

**NEVER use directly:**

- `mcp__gpt_codex__*` - GPT agent handles these
- `mcp__odoo-intelligence__*` - Agents have better access
- ANY Odoo-specific operations - ALWAYS delegate
- Complex implementation tools - ALWAYS delegate

## Agent Expertise You DON'T Have

**Agents have access to:**

- **Pattern libraries**: 29+ specialized pattern docs in `docs/agent-patterns/`
- **Framework internals**: Deep Odoo ORM, security, view architecture knowledge
- **Tool expertise**: Profilers, analyzers, GraphQL clients, test frameworks
- **Domain mastery**: Years of accumulated patterns and best practices
- **High token budget**: Can analyze entire modules without context limits

**This is why you MUST delegate aggressively!**

## Quick Workflows

- **Debug**: Debugger (analyzes) → Dock (logs) → GPT (fixes)
- **Feature**: Archer (research) → Planner (design) → specialists (implement)
- **Quality**: Inspector (finds issues) → QC (coordinates) → Refactor (bulk fixes)
- **Performance**: Flash (profiles) → Odoo-engineer (ORM optimization)
- **Frontend**: Owl (implements) → Dock (restarts) → Playwright (tests)
- **Migration**: Phoenix (patterns) → Odoo-engineer (framework) → Scout (tests)

## Knowledge Isolation Strategy

### What Agents Know (That You Don't)

**Each agent loads its own specialized knowledge:**

- `odoo-engineer`: Complete Odoo framework internals, ORM patterns, security models
- `owl`: Owl.js component lifecycle, patching system, QWeb templates
- `scout`: Test fixture patterns, TransactionCase, mock strategies
- `shopkeeper`: Shopify GraphQL schema, bulk operations, webhook handling
- `flash`: Performance profiling techniques, query optimization patterns
- `archer`: Instant codebase search algorithms, pattern matching

### Why This Matters

- **You stay lightweight**: Don't need framework details in your context
- **Agents stay expert**: Each loads only its domain knowledge
- **Better results**: Specialists apply deep expertise you can't access
- **Token efficiency**: Agents can use unlimited tokens (they're transient)

## Documentation Discovery

### Critical First Reads (Load These NOW)

1. **[Agent Quick Reference](docs/AGENT_QUICK_REFERENCE.md)** - ALL 17 agents with power levels
2. **[Agent Guide](docs/agents/README.md)** - Detailed capabilities and collaboration
3. **[Tool Selection](docs/TOOL_SELECTION.md)** - When agents beat direct tools

### Agent Pattern Libraries (29+ Specialized Docs)

**Agents auto-load their patterns from [docs/agent-patterns/](docs/agent-patterns/)**
You don't need these - agents have them!

## Commands

**IMPORTANT**: Never use `uv run` in addon directories with pyproject.toml files - they are for Docker dependencies
only.
Use `uv run` from project root for all commands:

- `uv run test-unit` - Unit tests
- `uv run test-integration` - Integration tests
- `uv run test-tour` - UI tests
- `uv run test-all` - Full suite
- `uv run ruff format . && uv run ruff check --fix` - Format

## Project Context

Odoo 18 Enterprise for OPW. Custom addons in `./addons`. Database: `opw`.
**DO NOT MODIFY**: `services/shopify/gql/*`, `graphql/schema/*`

## Git History

Use `git mv` before editing to preserve history.