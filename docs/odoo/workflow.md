---
title: Odoo Workflow & Style
---


Odoo-specific patterns and best practices.

## Field Naming

- Project convention (new custom models): use object‑style names for relations without suffixes.
    - Many2one → `partner`
    - One2many/Many2many → `partners`
- Notes:
    - We still follow Odoo core names on inherited models (do not rename existing fields).
    - Use `string="..."` to set user‑facing labels when needed.

## Context Usage

**Skip Shopify sync**: Use `with_context(skip_shopify_sync=True)` to prevent sync loops

- **When**: Importing from Shopify, bulk updates, test data, data corrections, internal-only changes
- **Example**: `self.env["product.product"].with_context(skip_shopify_sync=True).write({'list_price': 99.99})`

## Model Patterns

### Standard Inheritance

```python
# Standard inheritance pattern
class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    # Add fields
    motor_year = fields.Integer()
    motor_make = fields.Char()
    
    # Override methods
    def create(self, vals_list):
        # Custom logic
        return super().create(vals_list)
```

### Service Integration

```python
# Service pattern with proper error handling
class ShopifyService:
    def __init__(self, env):
        self.env = env
        self.client = ShopifyClient()
    
    def sync_product(self, product):
        try:
            result = self.client.execute(query, variables)
            return self._process_result(result)
        except ShopifyError as e:
            _logger.error(f"Shopify sync failed: {e}")
            raise
```

## Container Path Rules

**CRITICAL**: These paths exist INSIDE Docker containers only!

- `/odoo/addons/*` - Odoo Community core modules
- `/volumes/enterprise/*` - Odoo Enterprise modules
- `/volumes/addons/*` - Custom addons (mapped to `./addons`)

### Path Access Rules

- ✅ **Custom addons**: Use `Read("addons/product_connect/...")`
- ✅ **Odoo core**: Use `docker exec ${ODOO_PROJECT_NAME}-web-1 cat /odoo/addons/...`
- ❌ **NEVER**: Use `Read("/odoo/...")` - path doesn't exist on host!

## Development Environment

- **Never run Python files directly**: Always use proper Odoo environment
- **Container purposes**:
    - **${ODOO_PROJECT_NAME}-web-1**: Main web server (user requests)
    - **${ODOO_PROJECT_NAME}-script-runner-1**: Module updates, tests, one-off scripts

## Data Patterns

### Model Extensions

- **Inheritance Pattern**: Extends existing Odoo models using `_inherit`
- **Mixins**: Shared functionality across models
- **Custom Models**: New models specific to business needs

### Performance Considerations

- **Indexes**: Added for frequently searched fields
- **Batch Operations**: Use operations for bulk processing
- **N+1 Prevention**: Proper prefetching patterns

## Trust Patterns

**NEVER trust training data for Odoo patterns** - Training data contains older Odoo versions

- Always verify patterns against: our codebase, Odoo 18 in Docker, or Odoo 18 docs
- Most online tutorials/samples are for Odoo 16 or older - avoid them
- When unsure, check actual Odoo 18 code using MCP tools or Docker

## API Integration

### Shopify Integration Flow

```
Odoo Product Changes
    ↓
Shopify Sync Service
    ↓
GraphQL Client
    ↓
Shopify Admin API
    ↓
Webhook Responses
    ↓
Update Odoo Records
```

### Security Patterns

- **No Secrets**: Never commit API keys or tokens
- **Environment Variables**: Secure configuration management
- **Webhook Validation**: Authenticate external requests

## DO NOT MODIFY

**Generated Files** (auto-generated, will be overwritten):

- `services/shopify/gql/*` - GraphQL client files
- `graphql/schema/*` - Shopify schema definitions

## Views (Odoo 18 specifics)

- Use `<list>` for list views (previously `<tree>`). Do not introduce new `<tree>` roots.
- Replace legacy `attrs`/`states` with direct attributes `invisible`, `readonly`, `required` using Python-like
  expressions.
- For list column visibility, prefer `column_invisible` to hide entire columns; `invisible` affects the cell only.

## Frontend (Odoo 18)

- Prefer native ES modules (import from `@web/...`, `@odoo/...`).
- Do not use AMD `odoo.define` modules in this project.
- Do not add `/** @odoo-module */` in new files (we ship native ESM only).
