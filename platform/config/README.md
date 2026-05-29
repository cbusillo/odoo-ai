# Platform Config Layering (Local Dev)

Retired authority notice: this config surface is archival. Do not use files in
this repo to mutate live shared/testing/prod Odoo environments or to source
current secrets. Launchplane owns live runtime records and mutations;
`odoo-devkit` owns manifest-backed local runtime generation.

This directory holds historical platform runtime defaults that were used by
`uv run platform ...` and ad-hoc `docker compose` commands. It is retained only
to explain old local layering behavior.

## Historical Layer Order

Platform runtime generation (`uv run platform ...`):

```text
selected runtime env file (.platform/env/<context>.<instance>.env by default)
→ platform/secrets.toml overlays (shared → context → instance)
→ platform/config/base.env fallback defaults (tooling only, setdefault)
```

Raw Compose env-file loading (without platform runtime generation):

```text
.env
→ platform/config/base.env
```

Compose overlays (most generic → most specific):

```text
docker-compose.yml
→ platform/compose/base.yaml
→ docker-compose.override.yml (local-only)
```

## Historical Local Stacks

- `opw-local`
- `cm-local`

## Historical Quick Start

These commands are not current runtime guidance. Use `odoo-devkit` for local
runtime generation and Launchplane for live target mutation.

1. Copy the templates you need:
    - `cp .env.example .env`
    - Fill required secrets in an untracked local file if inspecting the old
      flow. Do not commit real values.
    - For local image builds, set private `ODOO_BASE_RUNTIME_IMAGE` and
      `ODOO_BASE_DEVTOOLS_IMAGE` there before running `platform up --build`.

2. Run the stack:

    ```bash
    uv run platform up --context opw --instance local --build
    ```

## Notes

- Keep secrets out of git. The historical `platform/secrets.toml` shape is not
  current live authority.
- `ODOO_MASTER_PASSWORD` is required for all stacks; set it in `.env`.
- `ODOO_LIST_DB` must be `False` to disable the database manager UI.
- `platform/config/base.env` is fallback-only for platform runtime generation
  (`uv run platform ...`). If a canonical stack value conflicts, tooling fails
  closed and asks you to align or remove the duplicate from `base.env`.
- Raw `docker compose` still loads `.env` then `base.env` for service
  `env_file` entries, so later values in `base.env` win in that path.
- Copy `docker-compose.override.example.yml` to `docker-compose.override.yml`
  when you need local port bindings or live code mounts. Keep
  `./addons:/opt/project/addons` in the shared section so `web` and
  `script-runner` execute the same addon source tree (see
  `docs/workflows/multi-project.md`).
- Historical restore runs relied on `DATA_WORKFLOW_SSH_DIR` so the base compose
  could mount the SSH directory for upstream access. Current restore/bootstrap
  authority belongs in Launchplane for live targets and `odoo-devkit` for local
  manifest-backed work.
