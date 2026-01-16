# Docker Config Layering (Local Dev)

This directory holds local stack overlays used by `uv run ops local ...` and
ad-hoc `docker compose` commands. Coolify deployments use standalone compose
files under `docker/coolify/<app>.yml` instead of these overlays.

## Layer order

Environment files (later overrides earlier):

```text
.env
→ docker/config/base.env
→ docker/config/{project}-local.env
```

Compose overlays (most generic → most specific):

```text
docker-compose.yml
→ docker-compose.override.yml (local-only)
→ docker/config/base.yaml
→ docker/config/{project}-local.yaml
```

## Local stacks

- `opw-local`
- `cm-local`
- `opw-ci-local`
- `cm-ci-local`

## Quick start

1. Copy the templates you need:

   Edit the target env file (for example `docker/config/opw-local.env`).

2. Run the stack:

   ```bash
   uv run ops local up opw --build
   ```

## Notes

- Keep secrets in `.env` (untracked); tracked env files should stay non-secret.
- Create a local `docker-compose.override.yml` to expose ports and mount the
  repo for live-editing (see `docs/workflows/multi-project.md`).
- Local-only overrides live in the env files (for example `ODOO_WEB_COMMAND`
  and host port mappings).
- Restore runs (`uv run ops local restore <target>`) rely on `RESTORE_SSH_DIR`
  being set so the base compose mounts the SSH directory for upstream access.
