---
title: Stack Migration & Addon Modularization (Living Doc)
---


## Front-matter

- Purpose: Track OPW/CM migration status and addon modularization decisions.
- Applies to: OPW (prod/dev/testing/local), CM (dev/testing/local), Docker deploy.
- References: @docs/tooling/docker.md, @docs/workflows/multi-project.md,
  @docker/config/README.md
- Maintainer: cbusillo
- Last Updated: 2025-12-27

## Intent

- Keep local dev stacks simple (`opw-local`, `cm-local`).
- Run remote environments via Coolify.
- Extract shared logic into dedicated addons over time.

## Current state

- OPW prod: legacy host (not Docker).
- OPW dev/testing: Coolify-managed.
- CM dev/testing: Coolify-managed.
- Local dev: `opw-local`, `cm-local`.
- Addons are monorepo-based; external addons are pulled at build time via
  `ODOO_ADDON_REPOSITORIES`.

## Target state

- OPW prod runs in Docker (Coolify or equivalent).
- Shared features live in separate addons; site-specific addons stay isolated.

## Stack matrix

- OPW local: `opw-local` (active)
- CM local: `cm-local` (active)
- OPW dev/testing: Coolify (active)
- CM dev/testing: Coolify (active)
- OPW prod: legacy (migration pending)

## Deploy & restore

- Local deploy: `uv run stack up --stack <stack>`
- Local restore: `uv run stack up --stack <stack> --restore`
- Remote deploys: Coolify UI (source = repo `docker-compose.yml` + env vars)
- Local port bindings + live mounts: `docker-compose.override.yml` (local-only)

## Addon map (direction)

- OPW-specific: `opw_custom` (planned prime layer)
- Shared/base: `product_connect` (migrate common pieces here)
- CM-specific: `cm_custom`
- Shared (extract as needed): `printnode`, `repair`, `external_ids`

Rule: shared addons must never depend on `product_connect`.

## Decisions log

- 2025-12-25: Prune remote stack overlays/docs; keep local stacks + Coolify.
- 2025-12-27: Move addons into monorepo; pull external addons at build time via
  `ODOO_ADDON_REPOSITORIES` (token required). Keep Coolify as control plane.

## Next actions

1. Validate OPW dev/testing stability in Coolify.
2. Stabilize cm-testing (restart loops) if still present.
3. Draft OPW prod cutover checklist when ready.
4. Create `opw_custom` addon as OPW prime layer; migrate OPW-only logic from
   `product_connect` over time.

## Completed

- Coolify dev/testing env vars normalized and deduplicated (build vs runtime
  split; minimal custom vars).
- Codex Cloud tooling removed from repo (no longer used).
