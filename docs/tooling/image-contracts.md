---
title: Image Contracts
---

Purpose

- Define responsibilities and tag contracts for the three-layer container
  strategy.

When

- When changing Docker build/publish pipelines, release tags, or runtime image
  promotion rules.

Layer Model

1. `odoo-docker` (public)
2. `odoo-enterprise-docker` (private)
3. `odoo-ai` (project runtime + code mounts)

`odoo-docker` contract

- Scope: community-safe runtime foundations only.
- No enterprise code, no project addons, no secrets in layers.
- Outputs:
  - immutable tags: `sha-<gitsha>-runtime`, `sha-<gitsha>-devtools`
  - nightly candidate tags: `nightly-*`
  - promoted tags: `19.0-runtime`, `19.0-devtools`
- Guarantees:
  - `/odoo/odoo-bin` exists
  - `/odoo/odoo-bin` remains subcommand-compatible with Odoo CLI
    (`server`, `shell`, `db`, etc.); base wrappers must not force server-mode
    parsing for non-server subcommands
  - `/venv` + `uv` present
  - PostgreSQL client tooling available

`odoo-enterprise-docker` contract

- Scope: private runtime layer that adds enterprise source and private runtime
  defaults.
- Inputs:
  - base images from `odoo-docker` (digest preferred)
  - BuildKit secret `github_token` for enterprise checkout
- Outputs:
  - immutable tags: `sha-<gitsha>-runtime`, `sha-<gitsha>-devtools`
  - nightly candidate tags: `nightly-*`
  - promoted tags: `19.0-runtime`, `19.0-devtools`
- Guarantees:
  - enterprise source at `/opt/enterprise`
  - `IMAGE_ODOO_ENTERPRISE_LOCATION=/opt/enterprise`
  - `ODOO_ADDONS_PATH` includes `/opt/enterprise`
  - inherits base `/odoo/odoo-bin` CLI behavior without overriding
    subcommand parsing semantics.

`odoo-ai` contract

- Scope: project orchestration, addon code, restore/openupgrade/test harness.
- Runtime source:
  - consume private enterprise images via `ODOO_BASE_RUNTIME_IMAGE` and
    `ODOO_BASE_DEVTOOLS_IMAGE`
  - pin digest for promoted environments
- Local iteration:
  - prefer mounting project addon code over rebuilding image for routine code
    changes
  - rebuild only when dependency/runtime layers change

Promotion Rule

1. `odoo-docker` publishes candidate tags after base smoke checks.
2. `odoo-enterprise-docker` consumes candidate base and publishes private
   candidate tags after enterprise smoke checks.
3. `odoo-ai` integration gate validates restore/openupgrade/test flow against
   candidate enterprise image.
4. Only then promote stable `19.0-*` tags and/or update pinned digests.

Operational Notes

- Treat `19.0-*` as promotion tags, not moving dev targets.
- Prefer digest references in `docker/config/base.env` for repeatable deploys.
- Keep enterprise fetch/publish workflows on private infrastructure (for
  example the `chris-testing` self-hosted runner).
