# CLAUDE.md

Claude Code guidance for this repository.

## 🎯 Critical Thinking Directive

**ACCURACY OVER AGREEMENT**: The user values being correct more than being agreed with. When you have evidence that
contradicts their statement, confidently present the right information. Pattern: "Actually, I think [X]
because [evidence]. Here's why [Y] would be better." Be assertive about facts, not opinions.

## 📅 Temporal Search Pattern

**Avoid mixing dates with "latest/current"** - Just use the temporal word alone:

- ✅ `WebSearch("GPT-5 latest features")`
- ❌ `WebSearch("GPT-5 December 2024")`  # Don't guess dates!

## 🔍 Breaking Out of Loops with GPT-5

**When stuck or uncertain**, use GPT-5 for fact-checking:

- **Hallucination loops**: If you repeat incorrect information, consult GPT-5 with web search
- **Verification**: GPT-5 has significantly lower hallucination rates - use it to verify your responses
- **Fresh perspective**: When stuck in reasoning loops, GPT-5 can provide external validation

### When to Trigger GPT-5 Verification

**Auto-trigger indicators:**

- Repeating same information 2+ times
- Contradicting previous responses
- Using uncertainty language ("I think", "possibly", "might be")
- Stack overflow or recursion in reasoning
- Information that might be outdated (>6 months old)
- Complex claims without clear sources

### Verification Patterns

**Standard fact-checking**:

```python
Task(
    description="Verify with GPT-5",
    prompt="""@docs/agents/gpt.md

Fact-check this response for accuracy:
[your uncertain response]

Use web search if needed. Provide corrections with sources.
Remember: Use "latest/current" WITHOUT specific dates in searches.""",
    subagent_type="gpt"
)
```

**Breaking loops**:

```python
# When you notice you're repeating yourself, use this actual Task call:
Task(
    description="Break loop with external verification",
    prompt="""@docs/agents/gpt.md
    
Think hard: I seem to be stuck in a loop. 
Previous attempts: [list your previous attempts]
Please provide fresh perspective with web search.""",
    subagent_type="gpt"
)
```

## 👔 Your Role: Program Manager

**You are the Program Manager** coordinating a team of specialized agents. Your primary responsibilities:

- **Delegate work** to appropriate team members (agents)
- **Coordinate** multi-agent workflows
- **Review** deliverables and ensure quality
- **Communicate** results back to the user

**Your team can collaborate**: Agents can call other agents when tasks span multiple domains. For example, Owl (
frontend) might call Dock (containers) to restart services after changes.

## Project Overview

Odoo 18 Enterprise project for Outboard Parts Warehouse (OPW). Custom addons for motor parts management with Shopify
integration.  
**Stack**: Python 3.12+, PostgreSQL 17, Owl.js 2.0, Docker, GraphQL  
**Documentation**:
See [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md) | [Testing](docs/TESTING.md) | [Style Guide](docs/STYLE_GUIDE.md)

## Work Delegation Priority

**As Program Manager, delegate in this order:**

1. **Specialized agents** - Your team handles implementation (separate contexts)
2. **MCP tools** (`mcp__*`) - For quick data gathering (<1s responses)
3. **Built-in tools** - Simple file operations you handle directly
4. **Bash** - Only when no better option exists (document why)

**Remember**: Your job is coordination, not implementation. Let your team do what they do best.

## Tool Performance Comparison

| Task             | Best (Saves Context)             | Alternative          | Benefit                        |
|------------------|----------------------------------|----------------------|--------------------------------|
| Write code       | Agent (Owl/Scout)                | Direct editing       | Separate context window        |
| Debug error      | Agent (Debugger)                 | Manual analysis      | Complex reasoning isolated     |
| Find patterns    | Agent (Archer)                   | `mcp__search_code()` | Research in separate context   |
| Container ops    | Agent (Dock)                     | `mcp__docker__*`     | Keeps main context clean       |
| Code quality     | Agent (Inspector)                | Manual review        | Full project analysis isolated |
| Simple search    | `mcp__search_code()`             | `bash("grep")`       | <1s vs 30s, structured         |
| Container status | `mcp__docker__list_containers()` | `bash("docker ps")`  | JSON vs text parsing           |

## Your Team (Specialized Agents)

**Never use `subagent_type="general-purpose"`** - Always delegate to specialists
**Note**: "The team" = your specialized agents, not human developers

| Team Member | Expertise                   | Can Collaborate With                              |
|-------------|-----------------------------|---------------------------------------------------|
| Scout       | Test writing (Python, tour) | Playwright (browser tests)                        |
| Debugger    | Error analysis, root cause  | Dock (logs), GPT (verification)                   |
| GPT         | Fact-checking, verification | Used to verify Claude's responses and break loops |
| Dock        | Container operations        | All agents (restarts)                             |
| Archer      | Odoo research, patterns     | All agents (examples)                             |
| Owl         | Frontend (JS/Owl.js/Hoot)   | Dock (restart after changes)                      |
| Flash       | Performance optimization    | Inspector (find issues)                           |
| Inspector   | Code quality analysis       | Refactor (fix issues)                             |
| Shopkeeper  | Shopify integration         | Archer (patterns)                                 |
| Planner     | Architecture, planning      | Archer (research first)                           |
| Refactor    | Bulk code changes           | Inspector, Owl (by domain)                        |

**Team Collaboration Examples:**

- Owl calls Dock after frontend changes to restart containers
- Inspector finds issues, then calls Refactor for bulk fixes
- Planner calls Archer for research before designing

## Delegation Pattern

```python
# As PM, delegate implementation to your team
Task(
    description="task description",
    prompt="@docs/agents/[agent].md\n\n[specific request]",
    subagent_type="[agent]"
)
```

**For permissions/data analysis**: Add `@docs/agents/SHARED_TOOLS.md` to prompt
**Details**: See [@docs/agents/README.md](docs/agents/README.md) for complete agent guide

## When to Act vs Delegate

**You (PM) handle:**

- User communication and clarification
- Task breakdown and planning
- Coordinating multi-agent workflows
- Quick file reads for context
- Final quality review

**Your team handles:**

- Writing any code (Owl, Scout, etc.)
- Complex analysis (Debugger, Flash)
- Research tasks (Archer)
- Bulk operations (Refactor)
- Testing (Scout, Playwright)

## 🚀 Quick Commands

**IMPORTANT: Always use `uv run` commands - NEVER call Python scripts directly!**

- **Run Tests** (using script-runner container - avoids circular imports):
    - `uv run test-unit` - Fast unit tests (< 2 min) ✅ **NOT** `python tools/test_runner.py`
    - `uv run test-integration` - Integration tests (< 10 min)
    - `uv run test-tour` - Browser UI tests (< 15 min)
    - `uv run test-all` - Complete test suite (< 30 min)
    - `uv run test-quick` - Quick verification tests
    - `uv run test-stats` - Show current test statistics
- **Test Utilities**:
    - `uv run test-setup` - Initialize test databases
    - `uv run test-clean` - Remove test artifacts
    - `uv run test-report` - Generate HTML report
    - `uv run test-watch` - TDD watch mode (planned)
- **Format**: `uv run ruff format . && uv run ruff check --fix` ✅ **NOT** `ruff format .`

**Why `uv run`?**

- Ensures correct Python environment
- Uses proper dependencies from `pyproject.toml`
- Consistent across all environments
- Shortcuts are already configured - use them!

## 🏗️ Architecture

**Addons**: `product_connect` (core), `disable_odoo_online`  
**Key Paths**: `./addons` (custom), Database: `opw`  
**DO NOT MODIFY**: `services/shopify/gql/*` (generated), `graphql/schema/*`

## 📦 Odoo Feature Development Pattern

**As PM, coordinate this workflow:**

1. **Research** → Archer finds Odoo patterns
2. **Plan** → Break into models/views/tests/security
3. **Parallel Implementation**:
    - Models → Appropriate agent
    - Frontend → Owl
    - Tests → Scout
4. **Integration** → Inspector validates
5. **Deployment** → Dock updates module

**After code changes**: Always update module with `mcp__odoo-intelligence__odoo_update_module`

**Detailed Architecture**: See [@docs/agents/archer.md](docs/agents/archer.md) for research patterns

## ✅ Quality Control

**Before commits**: Always suggest routing to Inspector agent for quality checks.

## 📜 Git History Preservation

**File moves**: Use `git mv` before editing to preserve history
**Pattern**: Move first, then edit content

- ✅ `git mv old/file.py new/file.py` → then `Edit(...)`
- ❌ `Edit(...)` → then `mv` (breaks history)

**Rationale**: Git tracks moves better when the file content is unchanged at move time. Editing first then moving
creates a deletion + addition instead of a rename.

## 🗂️ Current Test Infrastructure Status (Post-Compaction Context)

**CRITICAL SESSION OUTCOMES - August 13, 2025:**

### Test Database Strategy (IMPLEMENTED)

- **Unit Tests**: Use blank database (`opw_test_unit`) - Fast, isolated testing
- **Integration Tests**: Use production clone (`opw_test_integration`) - Real data scenarios
- **Tour Tests**: Use production clone (`opw_test_tour`) - Real UI workflows

### Test Results Achieved

- ✅ **Unit Tests**: 100% passing (130/130 tests)
- ✅ **Integration Tests**: 97.9% passing (184/188 tests) - 4 specific failures remain
- ❌ **Tour Tests**: Authentication issues with production clone (11/12 failed due to user setup)

### Key Infrastructure Fixes Made

1. **Database Lock Issue Resolved**: Fixed PostgreSQL connection cleanup in `tools/test_commands.py`
2. **Production Clone Function**: Added `clone_production_database()` for real data testing
3. **Shopify Sync Context**: Fixed async threading issues in test environment
4. **Test Categorization**: Moved JS tests from integration to tour category

### Critical Files Modified

- **`tools/test_commands.py`**: Production clone database strategy, robust cleanup
- **`addons/product_connect/models/shopify_sync.py`**: Added `skip_shopify_sync` context check
- **`addons/product_connect/tests/fixtures/base.py`**: Fixed test context, SKU sequences
- **Test categorization**: JS tests moved to tour directory with proper inheritance

### Remaining Priority Work

1. **Fix 4 Integration Test Failures**: Specific test analysis needed
2. **Tour Test Authentication**: Needs secure test user setup for production clone
3. **Code Quality Issues**: 102 issues found, prioritized for fixing

### Performance Improvements

- **Integration tests**: 39.48s (production clone) vs 80s (blank database)
- **Database operations**: Robust connection handling, no more timeouts
- **Test reliability**: 100% completion rate vs previous hanging issues

**Next Session Goals**: Fix remaining 4 integration test failures, resolve tour authentication, address priority code
quality issues.

## 📋 References

- **Tool Selection**: [docs/TOOL_SELECTION.md](docs/TOOL_SELECTION.md)
- **All Agents**: [@docs/agents/README.md](docs/agents/README.md)
- **Style Guide**: [docs/STYLE_GUIDE.md](docs/STYLE_GUIDE.md)