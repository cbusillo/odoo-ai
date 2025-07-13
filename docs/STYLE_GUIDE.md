# Code Style Guide

This document captures our project-specific style preferences that may differ from common Python/Odoo practices.

## JavaScript Style

### Semicolons

- **No semicolons**: Omit semicolons at the end of statements
- Modern JavaScript with proper file separation doesn't require them
- Cleaner and easier to read

### Libraries and Frameworks

**Use:**

- **Owl.js 2.0**: Odoo's modern component framework
    - Use hooks: `useState`, `useRef`, `onMounted`, etc.
    - Component-based architecture
- **Odoo Web Framework** (`@web/*`): Core Odoo utilities
- **@odoo/hoot**: For JavaScript testing
- **Chart.js**: Via Odoo's asset bundle for visualizations

**Do NOT use:**

- **jQuery** (`$` or `jQuery`): Odoo 18 is jQuery-free
- **Legacy widget system**: No `widget.extend` or `include()`
- **Old translation**: Use `import { _t } from "@web/core/l10n/translation"` not global `_t`
- **RequireJS/AMD**: Use ES6 modules instead
- **odoo.define()**: Use ES6 imports/exports instead

### JavaScript Patterns

- **Module files**: Start directly with ES6 imports (no module declaration comment needed)
- **Imports**: Use ES6 imports from Odoo namespaces
  ```javascript
  import { Component } from "@odoo/owl"
  import { registry } from "@web/core/registry"
  ```
- **Components**: Extend Owl Component, not old Widget class
- **No inline scripts**: All JS should be in module files
- **Type hints**: Use JSDoc for better IDE support
  ```javascript
  /** @type {import("./model").MyModel} */
  const model = this.model
  ```

## Python Style

### Type Hints

- **Use built-in types**: `list`, `dict`, `set` instead of `List`, `Dict`, `Set` from typing
- **Use union operator**: `str | None` instead of `Optional[str]`
- **Avoid unnecessary imports**: Prefer fewer imports when the result is the same
- **Never use `Any` or `object`**: Be specific with types
- **Use Odoo Plugin types**: `odoo.model.product_template`, `odoo.values.product_template`

### String Formatting

- **Always use f-strings**: Even for logging and exceptions
- **No % formatting or .format()**: F-strings only

### Comments and Documentation

- **NO comments or docstrings**: Code should be self-documenting through:
    - Descriptive names using full words (no abbreviations)
    - Clear function/variable names that state their purpose
    - Method chains that read like sentences
- **Exception**: Comments allowed in config files when the file type allows. Only add them when its not clear what a
  thing does or why its set to a value

### Control Flow

- **Early returns preferred**: No else after return
- **Ignore ruff rule TRY300**: Early returns are our preference

### Odoo Specific

- **Field naming**:
    - Use standard Odoo field names (e.g., `carrier_id` not `delivery_method_id`)
    - **Newer Odoo 18 pattern**: For Many2one fields, omit `_id` suffix when the field returns a recordset
        - Old pattern: `order.carrier_id` returns a recordset (confusing name)
        - New pattern: `order.carrier` returns a recordset (clearer)
        - Use `_id` only for fields that return an actual ID integer
    - **In practice**: Follow existing patterns in the codebase - Odoo 18 mixes both styles
- **Never run Python files directly**: Always use proper Odoo environment
- **Skip Shopify sync**: Use `with_context(skip_shopify_sync=True)` to prevent sync loops
    - When: Importing from Shopify, bulk updates, test data, data corrections, internal-only changes
    - Example: `self.env["product.product"].with_context(skip_shopify_sync=True).write({'list_price': 99.99})`

### Python Fields

- **String attributes**: Omit `string` attribute when the display text should match the field name
    - **Python fields**: `processed_today = fields.Boolean()` displays as "Processed Today"
    - Odoo automatically converts underscores to spaces and capitalizes appropriately
    - This ensures consistency and reduces duplication
    - Use explicit `string` only when display text differs from name: `qty = fields.Integer(string="Quantity")`

## File Organization

- **Test files in services**: Service-layer tests go in `services/tests/`
- **Model tests**: Model tests go in `tests/`
- **Temporary files**: Use prefixes `test_*` or `temp_*` in project root

## Development Workflow

- **Tool preference order**:
    1. MCP tools (odoo-intelligence, inspection-pycharm)
    2. Built-in Claude Code tools (Read, Edit, MultiEdit)
    3. Bash (only for complex operations)
- **Avoid using bash for**: `find`, `grep`, `cat`, `ls` - use Claude Code tools

## Common Mistakes to Avoid

1. Creating files unnecessarily - always prefer editing existing files
2. Creating documentation proactively - only create docs when requested
3. Using emojis - avoid unless explicitly requested
4. Long explanations - be concise, answer directly
5. Using generic Odoo tutorials - follow our existing patterns
6. **Trusting training data for Odoo patterns** - Training data contains older Odoo versions
    - Always verify patterns against: our codebase, Odoo 18 in Docker, or Odoo 18 docs
    - Most online tutorials/samples are for Odoo 16 or older - avoid them
    - When unsure, check actual Odoo 18 code using MCP tools or Docker

## Line Length

- **Python**: 133 characters max
- **Markdown**: No limit, but be reasonable

## Naming Conventions

- **Full words**: `calculate_total_amount` not `calc_tot_amt`
- **Descriptive**: code should describe itself, so use variable and function names that create descriptions of what
  things do
- **Boolean fields**: Use `is_` or `has_` prefix
- **Constants**: UPPER_SNAKE_CASE
- **Private methods**: Single underscore prefix `_method_name`

## Git Commits

- **Never commit unless asked**: User controls when to commit
- **Suggest to commit**: When at a good stopping point. Ideally commits should be a single feature or fix.

## Test Patterns

### SKU Validation Rules

- **Consumable products require 4-8 digit SKUs**: Products with `type='consu'` must have numeric SKUs
- **Valid examples**: "1234", "12345678", "00001234"
- **Invalid examples**: "ABC123", "TEST-001", "12", "123456789"
- **Service products exempt**: Products with `type='service'` can have any SKU format
- **Bypass validation**: Use `with_context(skip_sku_check=True)` when needed

### Test Class Inheritance

- **Always use base test classes** to avoid SKU validation errors
- **See [TESTING.md](TESTING.md#base-test-classes)** for details on available base classes and pre-created test data

This is a living document. Add new style decisions as they come up.