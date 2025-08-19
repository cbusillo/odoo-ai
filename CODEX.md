# CODEX.md - Project Context for Codex CLI

## Style Guides

All style rules are documented in `docs/style/`:
- **[Core Rules](docs/style/CORE.md)** - Tool hierarchy, naming, git practices
- **[Python](docs/style/PYTHON.md)** - Type hints, f-strings, Odoo patterns  
- **[JavaScript](docs/style/JAVASCRIPT.md)** - No semicolons, Owl.js 2.0
- **[Testing](docs/style/TESTING.md)** - Test patterns, SKU validation
- **[Odoo](docs/style/ODOO.md)** - Odoo 18 patterns, container paths

## Critical Rules

- **Python line length**: 133 characters max
- **JavaScript**: No semicolons, use Owl.js patterns
- **Tools**: ALWAYS use MCP tools over Bash (10-100x faster)
- **Git**: Use `git mv` to preserve history
- **Tests**: Run via `uv run` commands only

## Commands

```bash
# Testing
uv run test-unit          # Unit tests
uv run test-integration   # Integration tests  
uv run test-tour          # Browser/UI tests
uv run test-all           # Full test suite

# Code Quality
uv run ruff format .      # Format Python
uv run ruff check --fix   # Fix Python issues
```

## Project Structure

- **Custom addons**: `./addons/product_connect/`
- **Database**: `opw`
- **Odoo version**: 18 Enterprise
- **DO NOT MODIFY**: `services/shopify/gql/*`, `graphql/schema/*`

## Container Paths

- **Host paths**: `/Users/cbusillo/Developer/odoo-opw/`
- **Container paths**: `/volumes/` (mapped from host)
- **Never run Python directly**: Always use Odoo environment

## Implementation Focus

This file provides context for Codex CLI implementation tasks.
For coordination and delegation patterns, see CLAUDE.md.