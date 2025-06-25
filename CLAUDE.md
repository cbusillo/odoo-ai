# CLAUDE.md

Claude Code guidance for this repository.

## Project Overview

Odoo 18 Enterprise project for Outboard Parts Warehouse (OPW). Custom addons for motor parts management with Shopify
integration.
**Stack**: Python 3.12+, PostgreSQL 17, Owl.js 2.0, Docker, GraphQL

## Docker MCP Tools (Use These First!)

**Container Management** (prefer over bash):

- `mcp__docker__list-containers` - Check container status (replaces `docker ps`)
- `mcp__docker__get-logs` container_name: "odoo-opw-web-1" - View logs (replaces `docker logs`)
- `mcp__docker__deploy-compose` - Restart entire stack when needed

**Bash only** (complex Odoo ops):

```bash
# Update module (use dedicated script-runner container)
docker exec odoo-opw-script-runner-1 /odoo/odoo-bin -u product_connect --stop-after-init --addons-path=/volumes/addons,/odoo/addons,/volumes/enterprise

# Odoo shell (use dedicated shell container)
echo "env['motor.product'].search_count([])" | docker exec -i odoo-opw-shell-1 /odoo/odoo-bin shell --database=opw

# Cleanup extra containers if needed
docker container prune -f
```

## Quick Command Reference

**Tests**: `./scripts/run_tests.sh` (all) or `./scripts/run_tests.sh [python|js|tour]`, `./scripts/list_tests.sh`

- Test runner uses random ports (8080-18079) to avoid conflicts with main Odoo instance
  **Format**: `ruff format . && ruff check . --fix`

## Bug Detection

**IMPORTANT**: Never run Python files directly - use proper Odoo environment.

### JetBrains Inspection API (v1.9.0+)

**Workflow**:

1. **Trigger inspection**: `mcp__inspection-pycharm__inspection_trigger()`
2. **Check status**: `mcp__inspection-pycharm__inspection_get_status()` until complete
3. **Key**: The status response will clearly tell you:
   - `clean_inspection: true` → Inspection passed with no problems (stop here!)
   - `has_inspection_results: true` → Problems found, call `inspection_get_problems`
   - Otherwise → No recent inspection, trigger one first

**Usage Examples**:

- `mcp__inspection-pycharm__inspection_get_problems()` - Get all problems (paginated)
- `mcp__inspection-pycharm__inspection_get_problems(severity="error")` - Get only critical errors
- `mcp__inspection-pycharm__inspection_get_problems(severity="warning")` - Get warnings (default)
- `mcp__inspection-pycharm__inspection_get_problems(severity="grammar")` - Get grammar issues
- `mcp__inspection-pycharm__inspection_get_problems(severity="typo")` - Get spelling issues
- `mcp__inspection-pycharm__inspection_get_problems(problem_type="PyUnresolvedReferences")` - Filter by inspection type
- `mcp__inspection-pycharm__inspection_get_problems(file_pattern="*.py", limit=50)` - Filter by file pattern with pagination
- `mcp__inspection-pycharm__inspection_get_problems(scope="addons/product_connect/")` - Scope to specific directory

**Parameters**:
- `scope`: `whole_project` (default) | `current_file` | custom path
- `severity`: `error` | `warning` (default) | `weak_warning` | `info` | `grammar` | `typo` | `all`
- `problem_type`: Filter by inspection name (e.g., "PyUnresolvedReferences", "PyTypeChecker")
- `file_pattern`: Regex or simple pattern (e.g., "*.py", "models/.*\.py$")
- `limit`: Max problems per request (default: 100)
- `offset`: Skip problems for pagination

**Handling Large Results**: When you encounter token limit errors:
- Start with errors only: `severity="error"`
- Filter by problem type: `problem_type="PyTypeChecker"`
- Use pagination: `limit=50, offset=0`
- Combine filters: `severity="error", file_pattern="models/", limit=100`

## Docker Paths (Container)

- `/odoo` - Odoo community source
- `/volumes/enterprise` - Enterprise addons
- `/volumes/addons` - Custom addons (mounted from `./addons`)
- `/volumes/data` - Filestore
- Database: `opw`

## Code Standards

- **NO comments/docstrings** - Self-documenting code via:
    - Descriptive names using full words (no abbreviations)
    - Clear function/variable names that state their purpose
    - Method chains that read like sentences
    - Exception: Comments are allowed in pyproject.toml files for configuration clarity
- **Type hints required**:
    - Use the Odoo Plugin for Jetbrains Magic Types when possible
        - Models: `odoo.model.product_template` (IDE resolves to actual model class)
        - Dicts/Values: `odoo.values.product_template` (dict with model's field names)
    - Never use `Any`/`object`
    - Python 3.12+ `type` statements supported (set `target-version = "py312"` in ruff)
- **Line length**: 133 chars
- **Tests**: 80% coverage minimum (see Testing Requirements)
- **F-strings preferred**: Use f-strings for all string formatting, including logging and exceptions
- **Early returns preferred**: No else after return (ignore TRY300 ruff rule)

## Development Workflow

**Tool preferences** (in order of efficiency):

1. **MCP tools** - Docker ops, Odoo intelligence, PyCharm inspection
2. **Built-in tools** - `Read`, `Edit`, `MultiEdit`, `Write`, `Grep`, `Glob`
3. **Bash** - Only for complex Docker commands that MCP can't handle

**NEVER use bash for**: `find`, `grep`, `cat`, `ls` - use Claude Code tools instead

**Development steps**:

1. **Check containers** - Use `mcp__docker__list-containers`
2. **Examine existing code** - Follow project patterns, not generic Odoo tutorials
3. **Code like a senior Odoo core engineer** - Use advanced patterns found in enterprise addons
4. **Check similar features** - If adding to motors, study existing motor models/views/tests
5. **Run code quality checks** before committing:
    - JetBrains Inspection API (see Bug Detection section)
    - Runtime validation: Add `--stop-after-init` to catch import/syntax errors
    - Note: ruff-odoo plugin exists but PyCharm's Odoo plugin is more mature
6. **Test and format** - See Quick Command Reference
7. **Check logs if tests fail** - Use `mcp__docker__get-logs`

## Testing Requirements

**Philosophy**: TDD - failing tests first, then implement.

### Test Categories Required

1. **Unit Tests**: Test individual methods and business logic
    - All public methods must have tests
    - Test edge cases, error conditions, and boundary values
    - Mock external dependencies (Shopify API, database queries)

2. **Integration Tests**: Test component interactions
    - Test model relationships and data flow
    - Test API integrations with realistic data
    - Test UI components with backend services

### Test Standards

- **Coverage**: 80% minimum for new code
- **Naming**: `test_method_name_condition_expected_result()`
- **Structure**: Arrange-Act-Assert pattern
- **Data**: Use factories/fixtures, never hardcoded values
- **Isolation**: Each test must be independent and repeatable

### Test Organization

- `addons/*/tests/` - Python unit and integration tests
- `addons/*/static/tests/` - JavaScript tests (Hoot framework)
- `addons/*/static/tests/tours/` - Browser tour tests
- `addons/*/services/tests/` - Service layer tests

**Before Committing**: All tests must pass.

### Temporary Files

**Naming**: Use prefixes for temp files in project root:

- `test_*.py` - Test scripts and temporary test files
- `temp_*.py` - Temporary scripts and investigation files
- `temp_*.*` - Any other temporary files

Prefixes are in gitignore for easy cleanup.

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

**GraphQL regen**: Run `generate_shopify_models.py` when .graphql files or `SHOPIFY_API_VERSION` change

## Enhanced Code Intelligence (MCP Server)

**Odoo Intelligence MCP Server** provides deep code analysis through MCP tools:

**Core Commands:**

- `mcp__odoo-intelligence-mcp__model_info` model_name: "motor.product" - Fields, methods, inheritance, decorators
- `mcp__odoo-intelligence-mcp__search_models` pattern: "motor" - Exact → partial → description matches
- `mcp__odoo-intelligence-mcp__module_structure` module_name: "product_connect" - Models, views, controllers, manifest
- `mcp__odoo-intelligence-mcp__find_method` method_name: "compute_display_name" - All models implementing method
- `mcp__odoo-intelligence-mcp__inheritance_chain` model_name: "product.template" - MRO, inherits, inherited fields
- `mcp__odoo-intelligence-mcp__field_usages` model_name: "motor.product", field_name: "motor_id" - Views, methods,
  domains
- `mcp__odoo-intelligence-mcp__search_code` pattern: "shopify", file_type: "py" - Regex search (py|xml|js)
- `mcp__odoo-intelligence-mcp__addon_dependencies` addon_name: "product_connect" - Manifest, depends, auto_install
- `mcp__odoo-intelligence-mcp__model_relationships` model_name: "motor.product" - M2O/O2M/M2M + reverse relationships
- `mcp__odoo-intelligence-mcp__pattern_analysis` type: "computed_fields" - Types: `computed_fields`, `related_fields`,
  `api_decorators`, `custom_methods`, `state_machines`, `all`
- `mcp__odoo-intelligence-mcp__performance_analysis` model_name: "sale.order.line" - N+1 queries, missing indexes
- `mcp__odoo-intelligence-mcp__search_field_type` type: "many2one" - Types: `many2one`, `char`, `selection`, `date`,
  `boolean`, etc
- `mcp__odoo-intelligence-mcp__search_field_properties` property: "computed" - Properties: `computed`, `related`,
  `stored`, `required`, `readonly`
- `mcp__odoo-intelligence-mcp__search_decorators` decorator: "depends" - Decorators: `depends`, `constrains`,
  `onchange`, `model_create_multi`
- `mcp__odoo-intelligence-mcp__resolve_dynamic_fields` model_name: "product.template" - Computed/related fields with
  cross-model deps
- `mcp__odoo-intelligence-mcp__field_dependencies` model_name: "product.template", field_name: "list_price" - Dependency
  graph
- `mcp__odoo-intelligence-mcp__view_model_usage` model_name: "motor.product" - Views using model, field coverage
- `mcp__odoo-intelligence-mcp__workflow_states` model_name: "repair.order" - State fields, transitions, button actions
- `mcp__odoo-intelligence-mcp__execute_code` code: "result = env['product.template'].search_count([])" - Run Python code
  in Odoo env
- `mcp__odoo-intelligence-mcp__odoo_shell` code: "print(env['res.partner'].search_count([]))" - Execute code in Odoo
  shell container
- `mcp__odoo-intelligence-mcp__test_runner` module: "product_connect" - Run Odoo tests (placeholder)
- `mcp__odoo-intelligence-mcp__field_value_analyzer` model: "res.partner", field: "name" - Analyze field data
  patterns/quality
- `mcp__odoo-intelligence-mcp__permission_checker` user: "admin", model: "res.partner", operation: "read" - Debug access
  rights

**Usage**: Call MCP tools directly - they connect to running Odoo container automatically. Large response tools
auto-paginate.
