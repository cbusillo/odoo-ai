---
title: Platform Migration Status
---

Purpose

- Track the remaining launch blockers and durable follow-up work for the
  platform-first Dokploy migration.

Status

- Updated on 2026-03-02.
- Code/documentation migration is complete.
- Platform/tooling validation is complete (acceptance gates, local health, and
  Dokploy reconcile are green).
- One external blocker remains before final sign-off: CM prod backup proof on
  Proxmox infrastructure.

Completed State

- Migration closeout work is complete as of 2026-03-02; this page now tracks
  only the remaining launch blockers and durable follow-up items.

Remaining (Prod Launch Gates)

- [ ] Configure CM prod backup gate env vars (`CM_PROD_PROXMOX_HOST`,
  `CM_PROD_CT_ID`, `CM_PROD_BACKUP_STORAGE`, and related settings), then run
  one dry-run + one real `uv run prod-gate backup --target cm` once CM backup
  infrastructure is available.
- [ ] Re-scope OPW `environment_overrides` from context-level install to
  non-prod instance-only install during OPW prod promotion cutover.
  Current intentional temporary state: `platform/stack.toml`
  `[contexts.opw].install_modules` includes `environment_overrides`.

Durable Tooling Follow-ups

- [ ] Expand platform-first local operator helpers beyond
  `platform odoo-shell` to cover common stack-bound validation flows such as
  SQL/psql execution and structured log capture, so day-to-day debugging no
  longer falls back to raw `docker compose exec` commands.

Validation Evidence

- `uv run platform dokploy reconcile --json-output` revalidated clean on
  2026-03-02 with `matched_targets: 6` and `updated_targets: 0`.
- Full destructive local runtime proof completed on 2026-03-02 for both
  stacks, including cold rebuild and successful local init/restore workflows.
- Acceptance gate reruns completed on 2026-03-02 for both `cm` and `opw`
  stacks with unit, JS, integration, and tour categories green.
- `platform ship` succeeded for all active Dokploy targets on 2026-03-02 with
  healthy `/web/health` responses.
- OPW prod-gate backup completed successfully on 2026-02-27 and again on
  2026-03-02; CM prod backup proof remains blocked on backup infrastructure.
