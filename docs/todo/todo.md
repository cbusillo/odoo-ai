---
title: TODO / Optimization Ideas
---


## Optimize Motor Product Generation (create_motor_products)

- Profile product template matching and creation loops; consider batched create
  calls and prefetching related records.
- Avoid repeated name_search/read_group calls; fetch once per run.
- Consider server-side job queue if generation exceeds ~30–60s on typical
  datasets.
- Add progress bus events to update UI while processing.

## Stack Migration (OPW)

- Draft OPW prod cutover checklist and validate the prod gate.
- Create `opw_custom` addon as OPW prime layer; migrate OPW-only logic from
  `product_connect` over time.
- OPW testing-prod readiness:
  - Run JetBrains inspections on changed scope + git scope.
  - Human click-through and integration testing on `opw-testing`.
  - Schedule a 2-day cutover window once testing sign-off is complete.
  - During cutover: restore new `opw-prod` from `opw-prod.shiny`, verify, then
    move `odoo.outboardpartswarehouse.com` to the new host.
  - After cutover: block restore tooling on live prod (guard env + script).
  - After `opw-prod` promotion: clean up legacy LXC references in docs and
    tooling (only after the Coolify `opw-prod` container replaces
    `opw-prod.shiny`).
  - After `opw-prod` promotion: enable hourly backup for `docker-opw-prod`.
  - After `opw-prod` promotion: update zrepl fixture targeting the new
    container (from 109 to 104).
  - After Odoo 19 cutover + `opw-prod` promotion: remove `OPENUPGRADE_ENABLED`
    from opw apps (dev/testing/prod) once upgrades are complete.
  - After `opw-prod` promotion: remove `OPENUPGRADE_TARGET_VERSION` and the
    OpenUpgrade auto-injection in `docker/scripts/fetch_addons.sh`, plus any
    `OCA/OpenUpgrade@19.0` references if no longer needed.
  - After `opw-prod` promotion: remove `ODOO_UPSTREAM_*` env vars from
    `opw-prod` (no upstream once the docker prod becomes source of truth).
  - After `opw-prod` promotion: set `ENV_OVERRIDE_DISABLE_CRON=false` in
    Coolify so production cron jobs resume.
  - After `opw-prod` promotion: uninstall `environment_overrides` and remove it
    from `ODOO_INSTALL_MODULES` in `opw-prod`.

## Stack Migration (CM)

- Draft CM prod cutover checklist and validate the prod gate.
- CM testing-prod readiness:
  - Run JetBrains inspections on changed scope + git scope.
  - Human click-through and integration testing on `cm-testing`.
  - Schedule a cutover window once testing sign-off is complete.
  - During cutover: restore new `cm-prod` from upstream, verify, then move
    `connectmotors.com` to the new host.
  - After cutover: block restore tooling on live prod (guard env + script).
  - After `cm-prod` promotion: set `allow_prod_init = false` for `cm` in
    `docker/config/ops.toml` (or remove the flag entirely) to prevent prod
    bootstraps.
  - After `cm-prod` promotion: set `ENV_OVERRIDE_DISABLE_CRON=false` in Coolify
    so production cron jobs resume.
  - After `cm-prod` promotion: uninstall `environment_overrides` and
    `fishbowl_import`, and remove them from `ODOO_INSTALL_MODULES` in `cm-prod`.

## Health Checks

- Build a dedicated `odoo_healthcheck` addon with a DB/registry-aware endpoint
  (avoid `/web/health` false positives) and use it across all environments.
