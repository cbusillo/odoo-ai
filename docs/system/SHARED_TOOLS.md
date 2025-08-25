# Shared Tools Reference

This document contains tools and patterns that ALL agents should be aware of. Include this in agent prompts when needed.

## File Creation Guidelines

**Before creating any files**, read `tmp/README.md` for the proper temporary file structure:

- `tmp/scripts/` - One-off analysis and utility scripts
- `tmp/tests/` - Test files and output
- `tmp/data/` - Export files and analysis results

This keeps the project clean and ensures files are in the right location.

## Universal MCP Tools

### Quick Python Execution

```python
# Run Python code directly in Odoo environment
mcp__odoo-intelligence__execute_code(
    code="""
    # Quick tests, data checks, or exploration
    products = env['product.template'].search([])
    print(f"Total products: {len(products)}")
    """
)
```

### Permission Debugging

```python
# Debug why a user can't access records
mcp__odoo-intelligence__permission_checker(
    user="user_login",
    model="sale.order",
    operation="read",
    record_id=123  # optional
)
```

### Workflow Analysis

```python
# Analyze state machines and transitions
mcp__odoo-intelligence__workflow_states(
    model_name="sale.order"
)
# Returns: state fields, transitions, button actions
```

### Field Value Analysis

```python
# Analyze actual data in the database
mcp__odoo-intelligence__field_value_analyzer(
    model="product.template",
    field="list_price",
    domain=[('active', '=', True)],
    sample_size=1000
)
# Returns: min, max, avg, distribution, nulls, etc.
```

### Dynamic Field Resolution

```python
# Understand computed and related field chains
mcp__odoo-intelligence__resolve_dynamic_fields(
    model_name="sale.order.line"
)
# Shows: compute dependencies, related paths, triggers
```

## Quick Odoo Operations

### Container Management

```python
# Check health
mcp__odoo-intelligence__odoo_status(verbose=True)

# View logs
mcp__odoo-intelligence__odoo_logs(lines=200)

# Restart services
mcp__odoo-intelligence__odoo_restart(services="web-1,shell-1")

# Update module
mcp__odoo-intelligence__odoo_update_module(modules="product_connect")

# Quick shell command
mcp__odoo-intelligence__odoo_shell(
    code="print(env['ir.module.module'].search_count([]))"
)
```

## Universal Search Patterns

### Find by Decorator

```python
# Find all methods with specific decorators
mcp__odoo-intelligence__search_decorators(
    decorator="depends"  # or "constrains", "onchange", "model_create_multi"
)
```

### Find by Field Type

```python
# Find all models with specific field types
mcp__odoo-intelligence__search_field_type(
    field_type="many2one"  # or "char", "float", "json", etc.
)
```

### Find by Field Properties

```python
# Find fields with specific properties
mcp__odoo-intelligence__search_field_properties(
    property="computed"  # or "related", "stored", "required", "readonly"
)
```

## When to Use These Tools

1. **execute_code**: Quick data checks, one-off scripts, testing snippets
2. **permission_checker**: User can't see records, access rights errors
3. **workflow_states**: Understanding approval flows, state machines
4. **field_value_analyzer**: Data quality checks, finding outliers
5. **resolve_dynamic_fields**: Debugging compute errors, understanding dependencies

## Performance Tips

- Use `execute_code` for quick checks instead of creating temporary files
- `permission_checker` is faster than manually checking ir.model.access and ir.rule
- `field_value_analyzer` can prevent performance issues by showing data patterns
- These tools run in the actual Odoo environment with full context