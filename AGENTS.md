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
- **Update modules**:
  `/odoo/odoo-bin -u product_connect --stop-after-init --addons-path=/workspace,/odoo/addons,/volumes/enterprise`
- **Run tests**:
  `/odoo/odoo-bin --log-level=warn --stop-after-init --test-tags=product_connect --addons-path=/workspace,/odoo/addons,/volumes/enterprise -d odoo`
- **Odoo shell** (use `echo |` piping instead of heredoc):
  `echo "env['motor.product'].search_count([])" | /odoo/odoo-bin shell --addons-path=/workspace,/odoo/addons,/volumes/enterprise --database=odoo`
- **Code quality**: `ruff format . && ruff check . --fix`

## Bug Detection Priority

1. Runtime validation using `--stop-after-init`
2. PyCharm inspections (results in `./inspection-results/`)

## Code Standards

- No comments or docstrings; use descriptive names so code is self-explanatory.
- Type hints required. Use `odoo.model.*` for models and `odoo.values.*` for dictionaries. Avoid `Any` and `object`.
- Maximum line length is **133** characters.
- Tests must use real Odoo records, mock external services, rely on `TransactionCase`, and import using relative paths.

## Development Workflow

1. Inspect existing code and follow its patterns.
2. Write code like an experienced Odoo core engineer; check similar features first.
3. Execute tests with `--test-tags`.
4. Format code with `ruff`.

## Architecture Notes

- Primary addons: `product_connect` and `disable_odoo_online`.
- Key directories:
    - `models/` – Odoo inheritance and mixins
    - `static/src/js/` – Owl.js components
    - `services/` – External integrations

## Do Not Modify

- `services/shopify/gql/*`
- `graphql/schema/*`
