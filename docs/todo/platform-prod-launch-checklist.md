---
title: Platform Prod Launch Checklist
---

Purpose

- Track deferred rollout actions that are intentionally postponed until new
  production cutovers.

Deferred actions

- [ ] Enable prod backup gate in `platform/dokploy.toml` for new prod targets:
  set `require_prod_gate = true` for `cm-prod` and `opw-prod` at launch time.
- [ ] Verify prod gate environment variables are configured before enabling
  backup gate (`<TARGET>_PROD_PROXMOX_HOST`, `<TARGET>_PROD_CT_ID`, optional
  storage/snapshot retention settings used by `uv run prod-gate`).
- [ ] Run one dry-run and one real `uv run prod-gate backup --target <target>`
  from platform workflow before first production deploy.
