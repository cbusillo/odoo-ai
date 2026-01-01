# Docker Config Layering (Local Dev)

This directory holds local stack overlays used by `uv run ops local ...` and
ad-hoc `docker compose` commands. Coolify deployments ignore these files and
use the repo's `docker-compose.yml` only.

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
→ optional extras (used by restore flows)
```

## Local stacks

- `opw-local`
- `cm-local`

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
- Restore runs (`uv run ops local restore <target>`) automatically include the
  `_restore_ssh_volume.yaml` overlay so the container can reach upstream hosts.
