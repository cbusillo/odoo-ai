# Docker Config Layering (Local Dev)

This directory holds local stack overlays used by `uv run stack` and ad-hoc
`docker compose` commands. Coolify deployments ignore these files and use the
repo's `docker-compose.yml` only.

## Layer order

Environment files (later overrides earlier):

```text
.env
→ docker/config/base.env
→ docker/config/{project}.env
→ docker/config/{project}-local.env
```

Compose overlays (most generic → most specific):

```text
docker-compose.yml
→ docker-compose.override.yml (local-only)
→ docker/config/base.yaml
→ docker/config/{project}.yaml
→ optional extras (used by restore flows)
```

## Local stacks

- `opw-local`
- `cm-local`

## Quick start

1. Copy the templates you need:

   ```bash
   cp docker/config/base.env.example docker/config/base.env
   cp docker/config/opw.env.example docker/config/opw.env        # or cm.env
   cp docker/config/opw-local.env.example docker/config/opw-local.env
   ```

2. Fill in real values (DB credentials, API tokens, ports, etc.).

3. Run the stack:

   ```bash
   uv run stack up --stack opw-local
   ```

## Notes

- Real `*.env` files are untracked; keep secrets out of git.
- Create a local `docker-compose.override.yml` to expose ports and mount the
  repo for live-editing (see `docs/workflows/multi-project.md`).
- Local-only overrides live in the env files (for example `ODOO_WEB_COMMAND`
  and host port mappings).
- Restore runs (`uv run stack up --restore`) automatically include the
  `_restore_ssh_volume.yaml` overlay so the container can reach upstream hosts.
