# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Odoo 18 Enterprise project for Outboard Parts Warehouse (OPW). Custom addons for motor parts management with Shopify
integration, using Python 3.12+, Owl.js 2.0, and PostgreSQL 17.

## Core Development Commands

### Running Tests

```bash
# Run all tests for product_connect module (PyCharm "Odoo Web Tests" equivalent)
docker compose run --rm --remove-orphans web /odoo/odoo-bin --log-level=info --stop-after-init --test-tags=product_connect --addons-path=/volumes/addons,/odoo/addons,/volumes/enterprise

# Run specific tests with tags  
docker compose run --rm --remove-orphans web /odoo/odoo-bin --stop-after-init --test-tags=<tag> --addons-path=/volumes/addons,/odoo/addons,/volumes/enterprise
# Use this to limit tests run --test-tags[-][tag][/module][:class][.method]

# Run individual test classes
docker compose run --rm --remove-orphans web /odoo/odoo-bin --stop-after-init --test-tags=product_connect:TestShopifyHelpers --addons-path=/volumes/addons,/odoo/addons,/volumes/enterprise
```

### Code Quality (MUST pass before task completion)

1. **IDE Integration**: Use `mcp__ide__getDiagnostics(uri="file:///path/to/file.py")` for real-time checking
2. **CLI Tools**:
    - `ruff format .` and `ruff check . --fix`
    - User runs and exports inspection results to `./inspection-results/`. They will be in XML format

### Docker Development

```bash
docker compose up web          # Start development environment
docker compose run shell       # Run Odoo shell
```

## Development Guidelines

### Code Standards

- **NO comments or docstrings** — use descriptive names and/or descriptive logging
- Full type hints using Odoo magic types (e.g., `odoo.model.product_template` for models or
  `odoo.values.product_template` for dicts)
- **Avoid vague types**: Never use `Any`, `object`, or other overly general types. Use specific types:
    - `str | int | bool` instead of `object` for kwargs
    - Union types or specific classes instead of `Any`
    - Real Odoo records in tests instead of mock objects with `cast(Any, ...)`
- Line length: 133 characters, PEP 8 compliance required

### Testing Patterns — Write Tests the "Odoo Way"

```python
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMyFeature(TransactionCase):
    def setUp(self) -> None:
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Test Partner'})
```

**Key Rules**:

- Use real Odoo records instead of mock objects when possible
- Use `TransactionCase` for database operations (auto-rollback)
- Mock external services, not Odoo models
- Use `patch.object` instead of `patch`
- Avoid `cast()` by using real Odoo objects

### Architecture

**Main Addons**:

- `product_connect` - Core business module (motors, Shopify sync, custom widgets)
- `disable_odoo_online` - Disables Odoo's online features

**Code Organization**:

- Models: Odoo inheritance patterns with mixins
- Frontend: Owl.js 2.0 components in `static/src/js/`
- Services: External integrations in `services/`

### Generated Code (DO NOT MODIFY)

- `addons/product_connect/services/shopify/gql/*` - GraphQL client code
- `addons/product_connect/graphql/schema/*` - Shopify schema definitions

### Workflow Process

1. Examine relevant code before changes
2. Follow existing patterns and dependencies
3. Use mcp__ide__getDiagnostics to check that there are no errors or warnings
4. Run tests to validate changes. If code coverage is not available, add it.
5. Ensure ruff formatting and PyCharm inspections pass