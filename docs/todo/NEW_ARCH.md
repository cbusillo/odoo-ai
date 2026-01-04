---
title: Stack Migration & Addon Modularization (Living Doc)
---


## Front-matter

- Purpose: Track OPW/CM migration status and addon modularization decisions.
- Applies to: OPW (prod/dev/testing/local), CM (dev/testing/local), Docker deploy.
- References: @docs/tooling/docker.md, @docs/workflows/multi-project.md,
  @docker/config/README.md
- Maintainer: cbusillo
- Last Updated: 2026-01-04

## Intent

- Keep local dev stacks simple (`opw-local`, `cm-local`).
- Run remote environments via Coolify.
- Extract shared logic into dedicated addons over time.

## Target state

- OPW prod runs in Docker (Coolify or equivalent).
- Shared features live in separate addons; site-specific addons stay isolated.

## Next actions

1. Validate OPW dev/testing stability in Coolify.
2. Stabilize cm-testing (restart loops) if still present.
3. Draft OPW prod cutover checklist when ready.
4. Create `opw_custom` addon as OPW prime layer; migrate OPW-only logic from
   `product_connect` over time.
