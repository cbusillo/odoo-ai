# Platform Reset Contract

This directory defines the new minimal platform contract for local runtime,
inspections, and remote deployment.

## Goals

- Keep addon business logic in `addons/` with minimal churn.
- Replace scattered environment/config files with a single typed stack config.
- Keep secrets local and layered (`shared -> context -> instance`) with a
  structured TOML contract.
- Run platform commands through `uv run platform ...`.

## Files

- `stack.toml`: typed source of truth for contexts and runtime mapping.
- `dokploy.toml`: typed source of truth for Dokploy targets/branches/domains.
  Also includes optional target policy (`auto_deploy`, gate requirements, and
  managed env key/value pairs).
- `secrets.toml.example`: schema and example for local
  `platform/secrets.toml` (gitignored).
- `.env.example`: local template for required secret keys.

Generated runtime files live under `.platform/`:

- `.platform/env/<context>.<instance>.env`: resolved runtime env file.
- root `.env`: your local file plus a generated managed block used by PyCharm
  Compose interpreter compatibility.

Deploy commands (`ship`/`rollback`) read Dokploy credentials from `.env`
(`DOKPLOY_HOST`, `DOKPLOY_TOKEN`).

Platform local env layering (highest wins):

1. `.env` or explicit `--env-file`
2. `platform/secrets.toml` shared values
3. `platform/secrets.toml` context shared values
4. `platform/secrets.toml` context instance values

If layered sources define different values for the same key, platform warns by
default. Set `PLATFORM_ENV_COLLISION_MODE=error` to fail-closed or
`PLATFORM_ENV_COLLISION_MODE=ignore` to suppress warnings.

Runtime passthrough keys from the layered env are projected to
`.platform/env/<context>.<instance>.env` for keys matching `ENV_OVERRIDE_*`
plus `ODOO_KEY`.

Runtime tuning keys should live in `platform/stack.toml` under `runtime_env`
at stack/context/instance scope. Merge precedence is `stack -> context ->
instance`, with later scopes overriding earlier ones.

`ODOO_KEY` is used by restore flows to provision deterministic GPT service
users and API keys; treat it as a high-privilege secret.

`ship` supports Dokploy application and compose targets. In `auto` mode it
prefers compose when both names exist.

Runtime data persistence uses Docker named volumes per context/instance:

- `odoo-<context>-<instance>-data` for `/volumes/data` (includes filestore)
- `odoo-<context>-<instance>-logs` for `/volumes/logs`
- `odoo-<context>-<instance>-db` for PostgreSQL data

`web` startup now runs a bootstrap wrapper that auto-initializes first deploys
using `install_modules` and then starts the normal Odoo HTTP server process.
This keeps remote and local behavior consistent without manual first-run steps.
The bootstrap runtime config now starts from `/volumes/config/_generated.conf`
when present, so tuning keys (workers, db pool, limits, logging) remain active
for the long-running web process.

If the merged runtime environment defines both `ODOO_ADMIN_LOGIN` and
`ODOO_ADMIN_PASSWORD`, `uv run platform init ...` applies the password to that
login after module initialization and verifies the login does not still
authenticate with the default password. Prefer scoping these keys per context
(for example `contexts.cm.shared` in `platform/secrets.toml`) so restore-based
contexts without an `admin` login can leave credentials unchanged.

Composite workflows (`restore-init`, `restore-update`,
`restore-init-update`) emit `workflow_phase_start=<phase>` and
`workflow_phase_end=<phase>` markers to improve long-run progress visibility.

## Command Examples

```bash
uv run platform validate-config
uv run platform list-contexts
uv run platform doctor --context cm --instance local
uv run platform select --context cm --instance local
uv run platform select --context cm --instance local --dry-run
uv run platform render-odoo-conf --context cm --instance local
uv run platform inspect --context cm --instance local
uv run platform build --context cm --instance local
uv run platform up --context cm --instance local
uv run platform init --context cm --instance local
uv run platform update --context cm --instance local
uv run platform run --context cm --instance dev --workflow restore --env-file docker/config/cm-dev.env
uv run platform logs --context cm --instance local
uv run platform down --context cm --instance local
uv run platform ship --context cm --instance dev --dry-run
uv run platform ship --context cm --instance testing --skip-gate
uv run platform rollback --context cm --instance dev --list
uv run platform secrets explain --context cm --instance dev
uv run platform dokploy reconcile --json-output
uv run platform dokploy reconcile --context cm --instance prod --apply
```

## Contexts

- `cm`: Connect Motors context.
- `opw`: Outboard Parts Warehouse context.
- `qc`: Quality-control union context across client addons (local inspection only).

Each context can define instance overrides (`local`, `dev`, `testing`, `prod`)
with
`install_modules_add` so local/testing environments can include helper modules
without duplicating full module lists in every instance.
Each scope can also define `runtime_env` values for context/instance-specific
performance and runtime tuning.

Contexts can also define a default `database` name. Instance-level `database`
still overrides the context default when explicitly set.

Dokploy deployment scope is intentionally limited to `cm` and `opw`.
