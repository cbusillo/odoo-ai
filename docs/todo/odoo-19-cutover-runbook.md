---
title: Odoo 19 OPW Cutover Runbook
---

Purpose

- Provide one active runbook for OPW Odoo 19 production cutover,
  validation, and post-cutover cleanup.

Current Status

- Updated on 2026-02-27.
- Current live production is `opw-prod.shiny` on Odoo 18.
- Dokploy `opw-prod` is running Odoo 19 candidate runtime and has not been
  declared production of record yet.
- Until cutover is complete, `opw-prod.shiny` remains the read-only upstream
  restore source for `opw-*` local refresh workflows.

Scope

- In scope: OPW cutover execution, validation, and cleanup of upgrade artifacts.
- Out of scope: CM production cutover (CM prod is not live yet).

Pre-Cutover Checklist

- [ ] Confirm final Odoo 19 image tag/digest to deploy on `opw-prod`.
- [ ] Confirm last successful restore + init/update + smoke checks on the
  candidate environment.
- [ ] Confirm prod-gate backup runs clean for OPW before cutover window.
- [ ] Confirm rollback operator and rollback command path are ready.
- [ ] Freeze non-essential schema-changing merges during cutover window.

Cutover Execution

1. Capture a fresh OPW production backup via `uv run prod-gate backup --target opw`.
2. Deploy/pin the approved Odoo 19 runtime to `opw-prod`.
3. Run immediate health checks (`/web/health`) and login sanity checks.
4. Run focused business-critical path checks (orders, inventory, shipping,
   Shopify sync touchpoints).
5. Announce cutover completion or trigger rollback on failed gate.

Validation Checklist (Post-Deploy)

- [ ] Health endpoints return HTTP 200.
- [ ] Admin/user authentication works with expected SSO/local flows.
- [ ] Core OPW workflows succeed (sales, stock, repair, shipping labels).
- [ ] No unresolved module install queue remains.
- [ ] No severe errors in Odoo logs and deployment logs.

Rollback Criteria

- Trigger rollback if any core workflow is blocked, data integrity is at risk,
  or login/admin access is broken.
- Use the latest pre-cutover snapshot from `uv run prod-gate list --target opw`
  and execute rollback per incident owner direction.

Post-Cutover Cleanup

- [ ] Create Odoo 18 archive branch (example: `production-odoo18-archive`) for
  historical rollback reference.
- [ ] Remove OpenUpgrade addon/runtime wiring once no longer needed.
- [ ] Remove obsolete Odoo 19 upgrade planning docs and one-off test-session
  prompts.
- [ ] Confirm restore/bootstrap flows no longer depend on upgrade-only assets.

Evidence to Record

- Timestamped backup artifact/snapshot name used for cutover.
- Deployed image tag/digest and commit SHA.
- Health check outputs and validation checklist results.
- Rollback decision (not needed / executed) and operator sign-off.
