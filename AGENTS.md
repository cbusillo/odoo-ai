# AGENTS Guidance for Codex

This project contains Odoo 18 Enterprise addons for Outboard Parts Warehouse (OPW). The guidelines below are distilled
from `CLAUDE.md` and apply to the entire repository.

## Quick Commands

- **Update modules**:
  `docker compose run --rm --remove-orphans web /odoo/odoo-bin -u product_connect --stop-after-init --addons-path=/volumes/addons,/odoo/addons,/volumes/enterprise`
- **Run tests**:
  `docker compose run --rm --remove-orphans web /odoo/odoo-bin --log-level=warn --stop-after-init --test-tags=product_connect --addons-path=/volumes/addons,/odoo/addons,/volumes/enterprise`
- **Odoo shell** (use `echo |` piping instead of heredoc):
  `echo "env['motor.product'].search_count([])" | docker compose run --rm --remove-orphans web /odoo/odoo-bin shell --addons-path=/volumes/addons,/odoo/addons,/volumes/enterprise --database=opw`
- **Code quality**: `ruff format . && ruff check . --fix`

## Bug Detection Priority

1. `mcp__ide__getDiagnostics("file:///path/to/file.py")`
2. Runtime validation using `--stop-after-init`
3. PyCharm inspections (results in `./inspection-results/`)

## Code Standards

- No comments or docstrings; use descriptive names so code is self-explanatory.
- Type hints required. Use `odoo.model.*` for models and `odoo.values.*` for dictionaries. Avoid `Any` and `object`.
- Maximum line length is **133** characters.
- Tests must use real Odoo records, mock external services, rely on `TransactionCase`, and import using relative paths.

## Development Workflow

1. Inspect existing code and follow its patterns.
2. Write code like an experienced Odoo core engineer; check similar features first.
3. Run `mcp__ide__getDiagnostics` before committing changes.
4. Execute tests with `--test-tags`.
5. Format code with `ruff`.

## Architecture Notes

- Primary addons: `product_connect` and `disable_odoo_online`.
- Key directories:
    - `models/` – Odoo inheritance and mixins
    - `static/src/js/` – Owl.js components
    - `services/` – External integrations

## Do Not Modify

- `services/shopify/gql/*`
- `graphql/schema/*`
