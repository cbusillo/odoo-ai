---
title: Dokploy Operations
---

Purpose

Keep Dokploy usage minimal and point to the real API docs when needed.

Retirement Notice

- This `odoo-ai` Dokploy guide is archival. Do not use it as current authority
  for live target mutation, environment edits, release, rollback, or data
  workflows.
- Launchplane owns current Dokploy-backed shared/testing/prod operations and
  durable runtime records. Tenant repos call Launchplane through thin workflows;
  `odoo-devkit` owns local runtime DX and artifact handoff.

When

- When interacting with Dokploy-managed environments.

Historical Sources

- Dokploy API/docs (official).
- `docs/ARCHITECTURE.md#runtime-topology` — environment layout.
- `docs/tooling/docker.md` — local container operations.

Inputs/Outputs

- Inputs: `DOKPLOY_HOST`, `DOKPLOY_TOKEN`, target id.
- Outputs: logs, environment variables, app metadata.

Notes

- Keep environment-specific details in a local note if needed.
- Historical remote env vars lived in Dokploy. Current authority belongs in
  Launchplane-owned records and workflows.
- Historical automation commands included `uv run platform ship|rollback|gate`
  and `uv run platform dokploy ...` helpers. Do not use this retired checkout
  for live target mutation.
- Managed Dokploy targets used to keep auto deploy disabled and rely on
  `uv run platform ship` as the deploy trigger. Current deployment authority is
  Launchplane.
- Destructive remote data workflows now start from the manifest-backed
  `odoo-devkit` runtime surface (`platform runtime restore` and
  `platform runtime workflow --workflow bootstrap`). Those remote workflows
  execute through Dokploy schedule jobs triggered by the Dokploy API.
  Dokploy-managed targets are no longer mutated over SSH; only the upstream
  source host inside the restore script still uses SSH.
- Historical inventory used `uv run platform dokploy inventory` before
  destructive Dokploy cleanup.
- Historical remote target metadata lived in `platform/dokploy.toml`.
- Historical platform release/status/helper commands used pinned `target_id`
  and optional `target_name` values instead of scanning Dokploy by target name.
