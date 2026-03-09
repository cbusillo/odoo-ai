# Platform Config Layering (Local Dev)

This directory holds shared platform runtime defaults used by `uv run platform
...` and ad-hoc `docker compose` commands. Dokploy remote deployments use
Dokploy target settings (`composePath`) instead of these local overlays.

## Layer order

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

## Local stacks

- `opw-local`
- `cm-local`

## Quick start

1. Copy the templates you need:
   - `cp .env.example .env`
   - Fill required secrets in `.env` or `platform/secrets.toml`.

2. Run the stack:

   ```bash
   uv run platform up --context opw --instance local --build
   ```

## Notes

- Keep secrets in `.env` (untracked) or `platform/secrets.toml` (untracked).
- `ODOO_MASTER_PASSWORD` is required for all stacks; set it in `.env`.
- `ODOO_LIST_DB` must be `False` to disable the database manager UI.
- `platform/config/base.env` is fallback-only for platform runtime generation
  (`uv run platform ...`). If a canonical stack value conflicts, tooling fails
  closed and asks you to align or remove the duplicate from `base.env`.
- Raw `docker compose` still loads `.env` then `base.env` for service
  `env_file` entries, so later values in `base.env` win in that path.
- Create a local `docker-compose.override.yml` to expose ports and mount the
  repo for live-editing (see `docs/workflows/multi-project.md`).
- Restore runs (`uv run platform restore --context <target> --instance local`)
  rely on `DATA_WORKFLOW_SSH_DIR` being set so the base compose mounts the SSH
  directory for upstream access.
