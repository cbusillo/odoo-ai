# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Odoo 18 Enterprise project for Outboard Parts Warehouse (OPW), a company that buys outboard motors and parts
them out on eBay and Shopify. The codebase consists of custom Odoo addons with extensive Shopify and testing
integration.

## Core Development Commands

### Running Tests

```bash
# Run all tests for product_connect module via Docker
docker compose run --rm web /odoo/odoo-bin -d $ODOO_DB_NAME -u product_connect --addons-path=$ODOO_ADDONS_PATH --stop-after-init --test-enable --log-level=info

# Run specific tests with tags
docker compose run --rm web /odoo/odoo-bin -d $ODOO_DB_NAME --addons-path=$ODOO_ADDONS_PATH --stop-after-init --test-enable --test-tags=<tag>
# Use --test-tags[-][tag][/module][:class][.method]
```

### Code Quality (MUST pass before task completion)

#### 1. Built-in IDE Integration (Preferred for real-time checking)

When connected to PyCharm, Claude has direct access to IDE diagnostics:

- Use `mcp__ide__getDiagnostics` with file URIs to check individual files
- Provides instant feedback without startup delays
- Example: `mcp__ide__getDiagnostics(uri="file:///path/to/file.py")`
- Limitations: Single-file only, requires PyCharm to be running

#### 2. PyCharm MCP Server Tools (Optional)

The PyCharm MCP server (https://github.com/JetBrains/mcp-jetbrains) can provide additional tools:

- Dynamic tool discovery for extended IDE features
- Currently, not required for a basic development workflow
- May expose additional refactoring or analysis capabilities

#### 3. Command-line Tools (For comprehensive checks)

```bash
# Format and lint code with ruff
ruff format .
ruff check . --fix

# Run PyCharm inspections for full project analysis
./tools/run-pycharm-inspections.sh

# Note: Type checking is handled by PyCharm with the Odoo plugin
```

### Docker Development

```bash
# Start development environment
docker compose up web

# Run Odoo shell
docker compose run shell

# Run scripts
docker compose run script-runner <command>
```

### Local Development Scripts

```bash
# Sync from production database
./tools/init-and-run-odoo-dev.sh sync-prod local

# Initialize fresh dev environment
./tools/init-and-run-odoo-dev.sh init local

# Start in debug mode
./tools/init-and-run-odoo-dev.sh debug local

# Deploy to dev server
./tools/init-and-run-odoo-dev-server.sh
```

## Architecture

### Tech Stack

- **Backend**: Odoo 18 Enterprise, Python 3.12+
- **Frontend**: Owl.js 2.0, TypeScript/JavaScript
- **Database**: PostgreSQL 17
- **API**: Shopify GraphQL (using ariadne-codegen)
- **Build**: Webpack, Docker

### Main Addons

1. **product_connect** (v18.0.6.0) - Core business module
    - Motors, parts, and product management
    - Shopify bidirectional sync
    - Repair order workflows
    - Custom Owl.js widgets
    - PrintNode label printing

2. **disable_odoo_online** - Disables Odoo's online features

### Code Organization

- Models follow Odoo's inheritance patterns with extensive use of mixins
- Frontend uses Owl.js 2.0 components in `static/src/js/`
- GraphQL queries in `graphql/shopify/`
- Services layer in `services/` for external integrations
- Custom widgets extend Odoo's field widgets

## Project Dependencies

### Addon-Based Requirements

Each addon manages its own dependencies through requirements files:

- `addons/product_connect/requirements.txt` - Production dependencies
- `addons/product_connect/requirements-dev.txt` - Development dependencies

### Installation Process

Dependencies are automatically installed during Docker build via `/docker/scripts/install_addon_requirements.sh`, which:

1. Scans each addon directory for `requirements.txt` files
2. Installs production requirements for all addons
3. Installs development requirements when `DEV_MODE=true`

### Key Libraries

- `ariadne-codegen[subscriptions]` - GraphQL client generation from Shopify schema
- `printnodeapi` - Label printing integration (custom fork)
- `shopifyapi` - Shopify API client
- `pydantic-settings` - Configuration management
- `simple_zpl2` - ZPL label format generation (custom fork)
- `pillow`, `qrcode` - Image and QR code processing

### Code Quality Tools

Configured in `pyproject.toml`:

- `ruff` - Code formatting and linting (line-length: 133, ANN type annotation rules)

## Development Guidelines

### Code Standards

- **NO comments or docstrings** — use descriptive names
- Full type hints using Odoo magic types (e.g., `odoo.model.product_template` and `odoo.values.product_template`)
- Relative imports preferred
- Line length: 133 characters
- PEP 8 compliance required

### Testing Patterns

- Use `patch.object` instead of `patch` for mocking
- All tests must pass before completion
- Tour tests use Chromium for UI testing

### Generated Code (DO NOT MODIFY)

- `addons/product_connect/services/shopify/gql/*` - GraphQL client code
- `addons/product_connect/graphql/schema/*` - Shopify schema definitions

These are generated by Ariadne Codegen from GraphQL schemas.

### Workflow Process

1. Retrieve and examine relevant code before changes
2. Check existing patterns and dependencies
3. Make modifications following existing conventions
4. Run tests to validate changes
5. Ensure ruff formatting and PyCharm inspections pass

## Key Environment Variables

- `ODOO_DB_NAME` - Database name (opw: clone of prod)
- `ODOO_ADDONS_PATH` - Path to addons
- `GITHUB_TOKEN` - Required for Odoo Enterprise
- `SHOPIFY_*` - Various Shopify API credentials
- Python version: 3.12.8 (in Docker containers)

## Debugging

```bash
# Run with debug logging
docker compose run --rm web /odoo/odoo-bin -d $ODOO_DB_NAME --addons-path=$ODOO_ADDONS_PATH --log-handler=odoo.addons.product_connect:DEBUG --dev=all

# XML parsing debug (add to above command)
--log-handler=odoo.tools.convert:DEBUG
```

## Shopify Sync Operations

```bash
# Manual sync trigger (in Odoo shell)
docker compose run shell
>>> env['shopify.sync'].create({}).action_sync_all()

# Check sync status
>>> env['shopify.sync'].search([], order='create_date desc', limit=5)
```

## Common Issues

- **Type hint errors**: Use PyCharm with Odoo plugin for proper type resolution
- **Test failures**: Ensure a test database is clean, use `--test-tags`