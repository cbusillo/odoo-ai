# Dockerfile Refactor Plan

## Goal

Split container ownership into a reusable public-safe base image repo and a
private project overlay so runtime behavior is deterministic, reproducible, and
faster to rebuild.

See `docs/tooling/image-contracts.md` for the cross-repo image/tag contracts.

## Why Now

- Runtime behavior previously depended on third-party image defaults that were
  hard to reason about during restore incidents.
- We need predictable startup tuning (workers/memory/db connections) across
  contexts.
- We need cleaner control of optional runtime dependencies (for example
  `pdfminer.six`) without ad-hoc image patching.

## Non-Goals

- No feature flags for container behavior.
- No parallel legacy Dockerfile path after cutover.

## Target Shape

1. `cbusillo/odoo-docker` repository:
   - owns base runtime image (`runtime`) and devtools image (`runtime-devtools`)
   - contains no enterprise code, no secrets, no project addons
   - ships PostgreSQL 17 client tools + `uv` runtime + compatible OS packages
2. `cbusillo/odoo-enterprise-docker` repository (private):
   - consumes `odoo-docker` by digest/tag contract
   - adds enterprise/private source via BuildKit secret
   - publishes private runtime/devtools images after smoke gates
3. `odoo-ai` repository:
   - consumes private enterprise runtime images via
     `ODOO_BASE_RUNTIME_IMAGE` and `ODOO_BASE_DEVTOOLS_IMAGE`
   - keeps restore/bootstrap scripts and project addons in this repo

## Requirements

- Runtime config precedence remains deterministic:
  platform runtime env -> bootstrap config -> Odoo process args.
- Restore/openupgrade scripts remain available in both final images.
- `pdfminer.six` included in the dependency lock and installed in both targets.
- Image must run as non-root (`ubuntu`) for web workers and script-runner
  compatibility.
- Public base repo must be safe to publish (no enterprise/secrets in layers).
- Base CI publishes daily candidate tags (`nightly-*`) only after base smoke
  checks pass.
- Stable enterprise tags (`19.0-*`) are promotion tags and should only be
  consumed by `odoo-ai` after private integration gates pass
  (restore/openupgrade/test run).

## Validation Gate

1. Build `odoo-docker` targets (`runtime`, `runtime-devtools`) with no cache.
2. Run base smoke checks inside each target (`/odoo/odoo-bin`, uv, PostgreSQL
   client, Chromium in devtools).
3. Build `odoo-enterprise-docker` targets from `odoo-docker` inputs.
4. Run enterprise smoke checks inside each target.
5. Build `odoo-ai` development target using
   `ODOO_BASE_RUNTIME_IMAGE`/`ODOO_BASE_DEVTOOLS_IMAGE` from
   `cbusillo/odoo-enterprise-docker`.
6. Boot `opw-local` and confirm `web/health` pass.
7. Run clean restore from empty volumes.
8. Confirm:
   - no worker crash loop from memory limits
   - no unresolved `to install` module queue
   - image endpoints return HTTP 200

## Migration Steps

1. Publish `cbusillo/odoo-docker` base images (runtime + devtools).
2. Publish `cbusillo/odoo-enterprise-docker` private images (runtime +
   devtools).
3. Point `odoo-ai/docker/Dockerfile` and compose/env
   `ODOO_BASE_RUNTIME_IMAGE`/`ODOO_BASE_DEVTOOLS_IMAGE` to
   `cbusillo/odoo-enterprise-docker`.
4. Wire promotion flow: `odoo-docker` nightly candidate ->
   `odoo-enterprise-docker` private candidate -> `odoo-ai` integration gate ->
   stable tag promotion.
5. Update docs/env examples for the new image contract.
6. Run validation gate and fix regressions.
7. Remove obsolete references to legacy base image providers and one-off
   enterprise fetch layers in `odoo-ai`.
