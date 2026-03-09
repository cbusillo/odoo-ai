---
title: Dokploy Operations
---

Purpose

Keep Dokploy usage minimal and point to the real API docs when needed.

When

- When interacting with Dokploy-managed environments.

Sources of Truth

- Dokploy API/docs (official).
- `docs/ARCHITECTURE.md#runtime-topology` — environment layout.
- `docs/tooling/docker.md` — local container operations.

Inputs/Outputs

- Inputs: `DOKPLOY_HOST`, `DOKPLOY_TOKEN`, target id.
- Outputs: logs, environment variables, app metadata.

Notes

- Keep environment-specific details in a local note if needed.
- Dokploy is the source of truth for remote env vars. Local stacks use the
  platform-layered runtime env generated under `.platform/env/` via
  `uv run platform select` and should not drift from Dokploy.
- Primary automation commands are `uv run platform ship|rollback|gate|promote`
  and `uv run platform dokploy ...` helpers.
- Use `uv run platform dokploy inventory` before destructive Dokploy cleanup to
  snapshot the live project, server, and compose state into JSON artifacts.
- Remote target metadata contract lives in `platform/dokploy.toml`.
