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
  - downstream images must keep `/venv` as the only runtime environment and
    must not recreate it
  - downstream images use fixed project layout paths:
    `/opt/project`, `/opt/project/addons`, `/opt/extra_addons`
  - downstream runtime env generation may append grouped addon roots under
    `/opt/project/addons` (for example `/opt/project/addons/shared` or
    `/opt/project/addons/cm`) when those directories organize non-wrapper
    addons
  - `odoo-ai` keeps `/opt/project` as a real source tree while preserving the
    specific local workflow links still required for tooling: `/volumes/pyproject.toml`,
    `/volumes/uv.lock`, and local devtools images link `/opt/project/tools` to the `/volumes/tools`
    bind mount used by testkit
  - `odoo-python-sync.sh <prod|dev>` provides the supported additive install
    path for root lockfile-backed dependencies and addon `pyproject.toml`
    dependencies; legacy `requirements*.txt` support exists only for older
    addons that have not been migrated yet
  - `odoo-fetch-addons.sh` provides the supported external addon fetch path for
    `ODOO_ADDON_REPOSITORIES`
  - PostgreSQL client tooling available
  - `runtime-devtools` may add dev-only source/addon path shaping, but runtime
    targets stay free of IDE-only `.pth` entries

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
  - `runtime-devtools` appends `/opt/enterprise` to the inherited dev-only
    addon path shaping from `odoo-docker`
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
  - local compose builds one canonical `odoo-ai` image and both `web` and
    `script-runner` consume that same image tag to avoid service-level source
    skew
  - managed targets may override the normal `DOCKER_IMAGE` +
    `DOCKER_IMAGE_TAG` pair with `DOCKER_IMAGE_REFERENCE=<repo>@<digest>` when
    the control plane needs an exact immutable runtime image for deploy or
    promotion execution
  - both production and local `development` targets bake project addons into
    `/opt/project/addons`; runtime env generation expands grouped addon roots
    under that tree when present, and live-edit workflows must override that
    path with a bind mount when they need the mounted repo tree to win
  - rebuild only when dependency/runtime layers change
  - call the inherited `odoo-python-sync.sh` helper instead of owning local
    dependency-install mechanics
  - preserve the inherited `/venv`; do not recreate or destructively sync the
    base environment
  - do not own `.pth` addon-path shaping; that belongs in the upstream devtools
    layers
  - request external addons explicitly with `ODOO_ADDON_REPOSITORIES`; do not
    auto-inject OpenUpgrade or other workflow-specific repos into every build
  - pin OpenUpgrade workflows explicitly through tracked
    `OPENUPGRADE_ADDON_REPOSITORY` and `OPENUPGRADELIB_INSTALL_SPEC` values so
    local and remote restores use the same tested stack

Promotion Rule

1. `odoo-docker` publishes candidate tags after base smoke checks.
2. `odoo-enterprise-docker` consumes candidate base and publishes private
   candidate tags after enterprise smoke checks.
3. `odoo-ai` integration gate validates restore/openupgrade/test flow against
   candidate enterprise image.
4. Only then promote stable `19.0-*` tags and/or update pinned digests.

Operational Notes

- Treat `19.0-*` as promotion tags, not moving dev targets.
- Prefer digest references in `platform/config/base.env` for repeatable deploys.
- The compose runtime contract now accepts either `repo:tag` or an exact
  `DOCKER_IMAGE_REFERENCE` so the control plane can promote known immutable
  artifacts without changing the local developer image flow.
- Keep enterprise fetch/publish workflows on private infrastructure (for
  example the `chris-testing` self-hosted runner).
