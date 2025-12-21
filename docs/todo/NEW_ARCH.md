# Stack Migration & Addon Modularization (Living Doc)

## Front-matter

- Title: Stack Migration & Addon Modularization (Living Doc)
- Purpose: Track the OPW/CM migration plan, current status, and key decisions
  in one place.
- When to Use: Start of any session, architecture discussions, deploy planning,
  or migration updates.
- Applies To: OPW (prod/dev/testing/local), CM (testing/local), Docker deploy,
  addon modularization.
- Inputs/Outputs: Inputs = stack env files, deploy/restore tooling, addon repo
  state. Outputs = decisions, status, next actions.
- References: @docs/tooling/docker.md, @docs/workflows/multi-project.md,
  @docker/config/README.md, @tools/docker_runner.py
- Maintainers: cbusillo
- Last Updated: 2025-12-21

This doc is the single, durable source of truth for the OPW production
migration, Docker deploy path, and addon modularization strategy. It is
intentionally concise and updated as we progress.

## Intent and Scope

- Move OPW from legacy host deployment to Docker-based deploys without breaking
  prod.
- Keep CM as a non-production test site while shared modules are extracted.
- Extract shared features into small addons; keep site-specific logic isolated.

## Current State

- OPW prod is live on a legacy host (system service, not Docker).
- OPW dev/testing Docker stacks exist and are the target for validation.
- CM is a test site only (not production).
- `product_connect` is OPW-specific today and still monolithic.

## Target State

- OPW prod runs on Docker with the same deploy/restore tooling as dev/testing.
- CM continues as a Docker stack using the same deploy tooling.
- Shared features live in dedicated addons; site-specific addons remain separate.

## Non-Goals (for now)

- Full docs refactor.
- Renaming `product_connect` (unless we decide to later).
- CI/CD overhaul beyond the minimal deploy flow.

## Stack Matrix

- OPW prod: opw-prod (legacy) — Docker stack planned, not created yet.
- OPW testing: opw-testing (target) — validate Docker deploy + restore.
- OPW dev: opw-dev (target) — validate Docker deploy + restore.
- OPW local: opw-local (active) — local dev stack.
- CM testing: cm-testing (target) — non-production test.
- CM local: cm-local (active) — local dev stack.

## Addon Map (direction)

- OPW-specific: `product_connect` (treat as `opw_custom` in mental model).
- CM-specific: `cm_custom`.
- Shared (extract from OPW as needed): `printnode`, `repair`, `motor` (OPW only),
  `shopify` (OPW only), `external_ids` (already shared).

Rule: shared addons must never depend on `product_connect`.

## Deploy & Restore (stack-based)

- Deploy: `uv run deploy deploy --stack <stack>`
- Restore + sanitize: `uv run restore-from-upstream --stack <stack>`
- Stack env files live under `docker/config/<stack>.env` (git-ignored).
- Compose overlays are layered via `DEPLOY_COMPOSE_FILES` or defaults.

## Push-to-Deploy Flow (target)

Goal: keep the same "push branch → deploy" experience while using Docker.

Status (2025-12-21)

- This automation is not wired up yet in `odoo-ai` (no `repository_dispatch`
  listener).
- Today, deploys run from this repo by updating addon submodules and running:
  `uv run deploy deploy --stack <stack>`.

Summary

- Target: addon repo push triggers a `repository_dispatch` event to `odoo-ai`.
- Target: `odoo-ai` updates the submodule pointer, commits, and deploys the stack.
- Target: deploys are always driven by `odoo-ai`.

Mapping (branch → stack)

- OPW: `dev` → `opw-dev`, `testing` → `opw-testing`, `prod` → `opw-prod` (legacy
  host today; Docker stack planned).
- CM: `testing` → `cm-testing` (only deployable remote CM stack today). Local dev
  uses `cm-local`.

Target steps (for a single addon)

1. Push to addon branch (e.g., `product_connect` → `testing`).
2. Addon workflow sends `repository_dispatch` to `odoo-ai` with addon + branch.
3. `odoo-ai` updates submodule to that commit and records the bump.
4. `odoo-ai` deploys the target stack (`uv run deploy deploy --stack <stack>`).

Notes

- Shared addons may target multiple stacks (deploy testing first, then prod).
- Concurrency should be per-stack to avoid overlapping deploys.

## Remote Layout (docker.shiny)

```text
/opt/odoo-ai/
├── repos/<stack>/
└── data/<stack>/
    ├── .env
    ├── filestore/
    ├── postgres/
    └── logs/
```

## CI/CD Direction (reference)

- Legacy workflows in `addons/product_connect` use SSH + system service.
- Future: build image per branch, deploy via `uv run deploy` with rollback tags.
- Keep secrets out of git; render `.env` during deploy.

## Rollback Strategy (target)

- Keep previous image tags; re-deploy with a known-good tag.
- Keep DB/filestore snapshot or restore path prior to prod cutover.

## OPW Prod Cutover Checklist (draft)

Preparation

- Confirm OPW dev/testing Docker stacks restore and run cleanly.
- Create `opw-prod` stack env values if missing (host, paths, ports, base URL).
- Confirm restore/sanitize steps are safe for prod data.
- Verify rollback image tag and restore path before cutover.

Cutover window

- Freeze prod changes (announce maintenance window).
- Backup prod DB + filestore (VM snapshot or dump + rsync).
- Deploy Docker stack for `opw-prod`.
- Run module upgrade(s) for OPW addons.
- Validate health endpoint and critical flows.

Rollback

- Re-deploy last known-good image tag if health checks fail.
- Restore DB + filestore from snapshot if data issues occur.

## Restore + Sanitize Checklist (per stack)

Inputs

- Ensure stack env file exists: `docker/config/<stack>.env`.
- Confirm upstream host/db/filestore and SSH key settings.

Run

- `uv run restore-from-upstream --stack <stack>`
- If upstream is unavailable, use `--bootstrap-only`.

Validate

- Confirm DB is reachable and Odoo boots.
- Confirm key modules are updated (`ODOO_UPDATE` or `ODOO_AUTO_MODULES`).
- Confirm sanitization: emails disabled, crons disabled, base URL set.

Notes

- Restores are per stack, not per addon.
- Use unique `ODOO_STATE_ROOT` for each stack.

## Decisions Log

- 2025-12-21: Use this doc as the living migration record. Rationale: survives
  compactions and aligns sessions.

## Open Questions

- Do we create an explicit `opw-prod` stack in `docker/config` before cutover?
- Which shared features are next to extract (printnode vs repair)?
- What is the minimal CI/CD change needed for Docker deploys?

## Next Actions

1. Validate OPW dev/testing Docker deploy + restore flow.
2. Draft prod cutover checklist (with rollback).
3. Extract the first shared addon (likely printnode).
