# Agent Quick Reference

**CRITICAL**: Each agent has DEEP SPECIALIZED KNOWLEDGE you don't have access to.
Agents can use high tokens since they're transient - delegate liberally!

## All 17 Expert Agents (Each Has Domain Mastery)

### Core Development (These Know Odoo Internals)

| Agent       | Deep Expertise                           | Odoo-Specific Triggers                       | Power Level |
|-------------|------------------------------------------|----------------------------------------------|-------------|
| `archer`    | Finds ANY pattern in codebase instantly  | "_inherit", "how does Odoo", "find examples" | 🔥🔥🔥      |
| `debugger`  | Traces errors through Odoo stack         | "traceback", "@api error", "compute failed"  | 🔥🔥🔥      |
| `inspector` | Knows all Odoo style guides & patterns   | "code review", "PEP8", "Odoo conventions"    | 🔥🔥        |
| `gpt`       | Handles massive refactoring (100+ files) | "implement feature", "refactor module"       | 🔥🔥🔥      |

### Testing & Quality (Know Test Patterns)

| Agent   | Deep Expertise                          | Odoo-Specific Triggers            | Power Level |
|---------|-----------------------------------------|-----------------------------------|-------------|
| `scout` | Test fixtures, TransactionCase, mocking | "test_", "setUp", "fixture"       | 🔥🔥🔥      |
| `qc`    | Orchestrates multiple quality checks    | "full review", "pre-commit check" | 🔥🔥        |
| `flash` | Profiles ORM queries, finds N+1 issues  | "slow query", "prefetch", "N+1"   | 🔥🔥🔥      |

### Specialized Domains (Domain Masters)

| Agent        | Deep Expertise                   | Odoo-Specific Triggers                    | Power Level |
|--------------|----------------------------------|-------------------------------------------|-------------|
| `owl`        | Owl.js components, widgets, QWeb | "t-", "widget", "component", "patch"      | 🔥🔥🔥      |
| `playwright` | Tour testing, UI automation      | "tour", "click", "browser test"           | 🔥🔥        |
| `dock`       | Odoo containers, debugging, logs | "docker", "container logs", "restart web" | 🔥🔥        |
| `shopkeeper` | Shopify GraphQL, webhooks, sync  | "shopify", "graphql", "bulk operation"    | 🔥🔥🔥      |

### Project Management (Strategic Thinkers)

| Agent      | Deep Expertise                       | Odoo-Specific Triggers             | Power Level |
|------------|--------------------------------------|------------------------------------|-------------|
| `planner`  | Architecture patterns, module design | "design module", "plan feature"    | 🔥🔥        |
| `refactor` | Mass changes across 100+ files       | "rename everywhere", "bulk update" | 🔥🔥🔥      |
| `phoenix`  | Odoo version migration patterns      | "18.0 migration", "deprecated API" | 🔥🔥🔥      |

### Documentation & Meta (System Experts)

| Agent                | Deep Expertise                  | Odoo-Specific Triggers                   | Power Level |
|----------------------|---------------------------------|------------------------------------------|-------------|
| `doc`                | Generates comprehensive docs    | "document", "README", "docstring"        | 🔥          |
| `odoo-engineer`      | COMPLETE Odoo framework mastery | ANY Odoo pattern, "_inherit", "ir.model" | 🔥🔥🔥🔥    |
| `anthropic-engineer` | Optimizes this entire system    | "improve agents", "delegation patterns"  | 🔥🔥🔥      |

## 🚨 MANDATORY Delegation Rules

**NEVER attempt these yourself - ALWAYS delegate:**

1. **ANY Odoo framework task** → `odoo-engineer` FIRST
2. **ANY error/traceback** → `debugger` (has stack analysis tools)
3. **ANY test writing** → `scout` (knows fixtures & patterns)
4. **ANY performance issue** → `flash` (has profiling tools)
5. **ANY frontend/JS** → `owl` (knows Owl.js internals)
6. **ANY Shopify task** → `shopkeeper` (has GraphQL expertise)
7. **5+ files OR complex** → `gpt` (unlimited context)
8. **ANY research needed** → `archer` (instant pattern search)
9. **ANY quality check** → `inspector` → `refactor` if bulk
10. **ANY planning** → `planner` (knows architecture patterns)

## Usage Pattern

```python
# Standard agents (use Task)
Task(
    description="[brief task description]",
    prompt="[specific request with ALL context - agents are transient!]",
    subagent_type="[agent_name]"  # from list above
)

# GPT agent (special case - direct MCP)
response = mcp__codex__codex(
    prompt="[request]",
    sandbox="workspace-write",
    profile="deep-reasoning"  # Available: deep-reasoning, dev-standard, test-runner, safe-production, quick
)
session_id = response['structuredContent']['sessionId']
mcp__codex__codex_reply(prompt="follow‑up", sessionId=session_id)
```

## Agent Power & Collaboration

### Why Agents Are Powerful:

- **Deep domain knowledge** you don't have access to
- **Specialized tools** (profilers, analyzers, pattern matchers)
- **Can use high tokens** (they're transient, not persistent)
- **Access to pattern docs** specific to their domain
- **Can execute complex workflows** independently

### Common Collaborations:

- `odoo-engineer` → ANY (routes based on framework knowledge)
- `owl` → `dock` (restart containers after frontend changes)
- `inspector` → `refactor` (fix systematic issues found)
- `debugger` → `dock` → `gpt` (logs → analysis → fix)
- `planner` → `archer` → specialists (research → plan → implement)

**Remember**: Agents know MORE than you about their domains. Trust them!
