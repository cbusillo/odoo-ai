---
title: Platform Config Cleanup Backlog
---

Purpose

- Track deferred cleanup of old config/secrets sources after platform parity is
  proven, so we do not regress or forget migration debt.

Deferred cleanup targets

- [ ] Define the final role of root `.env`:
  keep only minimal bootstrap/operator-local keys + managed runtime block, or
  reduce further once all workflows consume `.platform/env` + `platform/secrets.toml`.
- [ ] Remove legacy `docker/config/<stack>.env` and `docker/config/.env.<stack>`
  fallback usage from day-to-day workflows after transition is complete.
- [ ] Remove/retire ops-era config authority (`docker/config/ops.toml`) once
  platform command surface fully covers required workflows.
- [ ] Audit docs and command help so each config class has one clear authority:
  runtime contract (`platform/stack.toml`),
  deploy policy (`platform/dokploy.toml`),
  local secrets (`platform/secrets.toml`).
- [ ] Add a pre-cutover checklist to assert no secrets are duplicated across
  old/new sources (root `.env`, `platform/secrets.toml`, Dokploy env).
