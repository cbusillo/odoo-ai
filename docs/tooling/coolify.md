---
title: Coolify Operations
---

## Purpose

Keep Coolify usage minimal and point to the real API docs when needed.

## Inputs/Outputs

- Inputs: `COOLIFY_HOST`, `COOLIFY_TOKEN`, app UUID.
- Outputs: logs, environment variables, app metadata.

## Sources of Truth

- Coolify API docs (official).
- `docs/ARCHITECTURE.md#runtime-topology` — environment layout.
- `docs/tooling/docker.md` — local container operations.

## Notes

- Keep environment-specific details in a local note if needed.
- Coolify is the source of truth for remote env vars. Local stacks use the
  layered env files under `docker/config/` and should not drift from Coolify.
- Coolify shows "No health check configured" if the UI health check is unset
  even when Docker health checks are healthy.
