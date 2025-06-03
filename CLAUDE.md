# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Odoo 18 Enterprise project for Outboard Parts Warehouse (OPW). Custom addons for motor parts management with Shopify
integration.
**Stack**: Python 3.12+, PostgreSQL 17, Owl.js 2.0, Docker, GraphQL

## Quick Command Reference

```bash
# Update module (ALWAYS use --stop-after-init to prevent server hanging)
docker compose run --rm --remove-orphans web /odoo/odoo-bin -u product_connect --stop-after-init --addons-path=/volumes/addons,/odoo/addons,/volumes/enterprise

# Run tests (--log-level=warn prevents context overflow)
docker compose run --rm --remove-orphans web /odoo/odoo-bin --log-level=warn --stop-after-init --test-tags=product_connect --addons-path=/volumes/addons,/odoo/addons,/volumes/enterprise

# Test specific class: --test-tags=product_connect:TestShopifyHelpers
# Odoo shell (use echo | pipe, NEVER heredoc <<EOF which causes parse errors)
echo "env['motor.product'].search_count([])" | docker compose run --rm --remove-orphans web /odoo/odoo-bin shell --addons-path=/volumes/addons,/odoo/addons,/volumes/enterprise --database=opw

# Code quality
ruff format . && ruff check . --fix
```

## Bug Detection Priority

1. **mcp__ide__getDiagnostics("file:///path/to/file.py")** - ALWAYS use first for Odoo-aware error checking
2. **Runtime validation**: Add `--stop-after-init` to catch import/syntax errors
3. **PyCharm inspections**: User exports to `./inspection-results/` (XML format)

## Docker Paths (Container)

- `/odoo` - Odoo community source
- `/volumes/enterprise` - Enterprise addons
- `/volumes/addons` - Custom addons (mounted from `./addons`)
- `/volumes/data` - Filestore
- Database: `opw`

## Code Standards

- **NO comments/docstrings** - Code must be self-documenting through:
    - Descriptive names using full words (never abbreviations)
    - Function names that clearly state what they do
    - Variable names that explain their purpose
    - Method chains that read like sentences
- **Type hints required**:
    - Models: `odoo.model.product_template` (IDE resolves to actual model class)
    - Dicts/Values: `odoo.values.product_template` (dict with model's field names)
    - Never use `Any`/`object`
- **Line length**: 133 chars
- **Tests**: Real Odoo records only, mock external services, use `TransactionCase`, use relative imports

## Development Workflow

1. **Examine existing code first** - Follow project patterns, not generic Odoo tutorials
2. **Code like a senior Odoo core engineer** - Use advanced patterns found in enterprise addons
3. **Check similar features** - If adding to motors, study existing motor models/views/tests
4. **Run `mcp__ide__getDiagnostics`** before committing
5. **Test with `--test-tags`**
6. **Format with `ruff`**

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
