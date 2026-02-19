# Platform Reset Contract

This directory defines the new minimal platform contract for local runtime,
inspections, and remote deployment.

## Goals

- Keep addon business logic in `addons/` with minimal churn.
- Replace scattered environment/config files with a single typed stack config.
- Keep secrets in one local `.env` file for compatibility with common tooling.
- Run platform commands through `uv run platform ...`.

## Files

- `stack.toml`: typed source of truth for contexts and runtime mapping.
- `.env.example`: local template for required secret keys.

Deploy commands (`ship`/`rollback`) read Dokploy credentials from `.env`
(`DOKPLOY_HOST`, `DOKPLOY_TOKEN`).

`ship` supports Dokploy application and compose targets. In `auto` mode it
prefers compose when both names exist.

Runtime data persistence uses Docker named volumes per context/instance:

- `odoo-<context>-<instance>-data` for `/volumes/data` (includes filestore)
- `odoo-<context>-<instance>-logs` for `/volumes/logs`
- `odoo-<context>-<instance>-db` for PostgreSQL data

`web` startup now runs a bootstrap wrapper that auto-initializes first deploys
using `install_modules` and then starts the normal Odoo HTTP server process.
This keeps remote and local behavior consistent without manual first-run steps.

## Command Examples

```bash
uv run platform validate-config
uv run platform list-contexts
uv run platform doctor --context cm --instance local
uv run platform render-odoo-conf --context cm --instance local
uv run platform inspect --context cm --instance local
uv run platform build --context cm --instance local
uv run platform up --context cm --instance local
uv run platform init --context cm --instance local
uv run platform update --context cm --instance local
uv run platform logs --context cm --instance local
uv run platform down --context cm --instance local
uv run platform ship --context cm --instance dev --dry-run
uv run platform rollback --context cm --instance dev --list
```

## Contexts

- `cm`: Connect Motors context.
- `opw`: Outboard Parts Warehouse context.
- `qc`: Quality-control union context across client addons (local inspection only).

Each context can define instance overrides (`local`, `dev`, `testing`, `prod`)
with
`install_modules_add` so local/testing environments can include helper modules
without duplicating full module lists in every instance.

Dokploy deployment scope is intentionally limited to `cm` and `opw`.
