# CLAUDE.md

Claude Code guidance for this repository.

## Project Overview

Odoo 18 Enterprise project for Outboard Parts Warehouse (OPW). Custom addons for motor parts management with Shopify
integration.
**Stack**: Python 3.12+, PostgreSQL 17, Owl.js 2.0, Docker, GraphQL

## Documentation

See [Documentation](docs/DOCUMENTATION.md) for all available documentation resources, including:

- [Testing Guide](docs/TESTING.md) - Test patterns, coverage requirements, and examples
- [Style Guide](docs/STYLE_GUIDE.md) - Code standards and naming conventions
- [Work-in-progress notes](docs/todo) - Development notes and future improvements

## CRITICAL: Tool Selection Hierarchy

**ALWAYS follow this order - using the wrong tool wastes time and causes errors:**

1. **MCP Tools FIRST** - Purpose-built for specific tasks
    - `mcp__odoo-intelligence__*` - For ANY Odoo code analysis (PROJECT-WIDE)
    - `mcp__docker__*` - For container operations
    - `mcp__inspection-pycharm__*` - For code quality (single file only)
    - `mcp__pycharm__*` - For IDE interactions

2. **Built-in Tools SECOND** - For file operations
    - `Read`, `Write`, `Edit`, `MultiEdit` - File modifications
    - `Grep`, `Glob` - File searching
    - `Task` - For complex multi-step operations

3. **Bash LAST RESORT** - Only when no other option exists
    - Complex Docker exec commands not covered by MCP
    - See @docs/agents/dock.md for Docker operations

**NEVER use Bash for**: `find`, `grep`, `cat`, `ls`, `docker ps`, `docker logs`

## 🚀 Proven Success Patterns

### Fast Code Search

```python
# ✅ RIGHT: Instant project-wide search
mcp__odoo - intelligence__search_code(pattern="extends.*Controller", file_type="js")

# ❌ WRONG: Slow bash grep
docker
exec
odoo - opw - web - 1
grep - r
"extends.*Controller" / odoo /
```

### Container Operations

```python
# ✅ RIGHT: Instant, formatted output
mcp__docker__list - containers()
mcp__docker__get - logs(container_name="odoo-opw-web-1")

# ❌ WRONG: Creates temporary containers
docker
compose
run - -rm
web / odoo / odoo - bin...
```

### Quality Checks

```python
# ✅ RIGHT: Comprehensive analysis
mcp__odoo-intelligence__pattern_analysis(pattern_type="all")
mcp__odoo-intelligence__performance_analysis(model_name="product.template")

# ❌ WRONG: Limited single-file inspection
# PyCharm inspection only sees one file at a time
```

### Testing

```python
# ✅ RIGHT: Use test runner with proper base classes
./ tools / test_runner.py - -test - tags
TestFeatureName

# ❌ WRONG: Direct odoo-bin without test infrastructure
docker
exec
odoo - opw - web - 1 / odoo / odoo - bin
test...
```

## Quick Command Reference

**Tests**: `./tools/test_runner.py` - Enhanced test runner (no docker SDK required)

- `./tools/test_runner.py summary` - Quick test summary (default)
- `./tools/test_runner.py all` - Run all tests
- `./tools/test_runner.py python` - Python tests only
- `./tools/test_runner.py js` - JavaScript unit tests only
- `./tools/test_runner.py tour` - Tour tests only (UI automation)
- `./tools/test_runner.py failing` - List currently failing tests
- `./tools/test_runner.py -v` - Verbose output with error details
- `./tools/test_runner.py --test-tags TestOrderImporter` - Run specific test class
- `./tools/test_runner.py --test-tags TestOrderImporter.test_import_order` - Run specific test method
- `./tools/test_runner.py -j` - JSON output for parsing
- `./tools/test_runner.py -u` - Update module before running tests (use only if needed, can cause timeouts)

**Testing**: See @docs/agents/scout.md for comprehensive test writing patterns

**Format**: `ruff format . && ruff check . --fix`

**File Moves**: Always use `git mv` instead of `mv` to preserve Git history.

**Browser Debugging**: Use `mcp__playwright__` tools - See @docs/agents/owl.md for frontend debugging

## Code Quality

**IMPORTANT**: Never run Python files directly - use proper Odoo environment.

For comprehensive code quality analysis, see @docs/agents/inspector.md

**Quick check**: `mcp__odoo-intelligence__pattern_analysis(pattern_type="all")`

## Key Paths

- **Custom addons**: `./addons` (accessible from host)
- **Container paths**: See @docs/agents/archer.md for Odoo source research
- **Database**: `opw`

## Code Standards

See [Style Guide](docs/STYLE_GUIDE.md) for complete coding standards including Python, JavaScript, naming conventions,
and formatting rules.

## Development Workflow

**Tool preferences** (in order of efficiency):

1. **MCP tools** - Docker ops, Odoo intelligence, PyCharm inspection
2. **Built-in tools** - `Read`, `Edit`, `MultiEdit`, `Write`, `Grep`, `Glob`
3. **Bash** - Only for complex Docker commands that MCP can't handle

**NEVER use bash for**: `find`, `grep`, `cat`, `ls` - use Claude Code tools instead

**Development steps**:

1. **Check containers** - Use `mcp__docker__list-containers`
2. **Follow project patterns** - Not generic tutorials
3. **Run tests before completion** - `./tools/test_runner.py`
4. **Format code** - `ruff format . && ruff check . --fix`

## Architecture

**Addons**:

- `product_connect` - Core business (motors, Shopify sync, widgets)
- `disable_odoo_online` - Disables online features

**Structure**:

- Models: `models/` - Odoo inheritance with mixins
- Frontend: `static/src/js/` - Owl.js 2.0 components
- Services: `services/` - External integrations

**DO NOT MODIFY**:

- `services/shopify/gql/*` - Generated GraphQL client
- `graphql/schema/*` - Shopify schema

**Shopify Integration**: See @docs/agents/shopkeeper.md for GraphQL and sync patterns

## Specialized Development Agents

For focused expertise without context pollution, use our specialized agents:

| Agent              | Specialty                              | Documentation              |
|--------------------|----------------------------------------|----------------------------|
| 🏹 **Archer**      | Odoo source research, finding patterns | @docs/agents/archer.md     |
| 🔍 **Scout**       | Writing comprehensive tests            | @docs/agents/scout.md      |
| 🔬 **Inspector**   | Code quality analysis                  | @docs/agents/inspector.md  |
| 🚢 **Dock**        | Docker container operations            | @docs/agents/dock.md       |
| 🛍️ **Shopkeeper** | Shopify integration                    | @docs/agents/shopkeeper.md |
| 🦉 **Owl**         | Frontend development (Owl.js)          | @docs/agents/owl.md        |
| 🔥 **Phoenix**     | Migrating old patterns                 | @docs/agents/phoenix.md    |
| ⚡ **Flash**        | Performance optimization               | @docs/agents/flash.md      |

**Using Agents**:

```python
Task(
    description="Find graph view patterns",
    prompt="@docs/agents/archer.md\n\nFind how Odoo 18 implements graph views",
    subagent_type="general-purpose"
)
```

See @docs/agents/README.md for complete agent overview.
