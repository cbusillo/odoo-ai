---
title: Platform Migration Status
---

Purpose

- Track the durable follow-up work for the platform-first Dokploy migration.

Status

- Updated on 2026-04-11.
- Code/documentation migration is complete.
- Platform/tooling validation is complete (acceptance gates, local health, and
  Dokploy reconcile are green).
- No external blockers remain before final sign-off.
- Dokploy non-prod workloads were moved off the Dokploy control-plane host onto
  `docker-shiny-nonprod` (`192.168.1.36`) on 2026-04-05.
- Manifest-driven runtime ownership for restore/bootstrap/update now lives in
  `odoo-devkit`; `odoo-ai` retains its repo-local platform CLI workflow path as
  a transitional surface until the remaining migration cleanup lands.

Completed State

- Migration closeout work is complete as of 2026-03-02; this page now tracks
  only the durable follow-up items.

Completed Launch Gates

- [x] Configure CM prod backup gate env vars (`CM_PROD_PROXMOX_HOST`,
      `CM_PROD_CT_ID`, `CM_PROD_BACKUP_STORAGE`, and related settings), then run
      one dry-run + one real `uv run prod-gate backup --target cm` once CM backup
      infrastructure is available. Revalidated on 2026-04-08: dry-run resolved
      the live Proxmox target, and a real run succeeded with snapshot
      `cm-predeploy-20260408-194712-codexcheck` plus PBS archive
      `ct/200/2026-04-08T23:47:23Z`.
- [x] Keep OPW `environment_overrides` installed at the context level until the
      real OPW prod switchover. Current intentional state: `platform/stack.toml`
      `[contexts.opw].install_modules` includes `environment_overrides`; re-scope
      it only during the later OPW prod cutover rather than treating it as a
      Dokploy-host-migration blocker.

Durable Tooling Follow-ups

- [ ] Expand platform-first local operator helpers beyond
      `platform odoo-shell` to cover common stack-bound validation flows such as
      SQL/psql execution and structured log capture, so day-to-day debugging no
      longer falls back to raw `docker compose exec` commands.
- [ ] Restore normal Odoo non-prod build behavior on `docker-shiny-nonprod`.
      Current temporary state: `opw-dev`, `opw-testing`, `cm-dev`, and
      `cm-testing` were moved using transferred prebuilt `odoo-ai:latest` images
      plus no-build compose commands because authenticated pulls of
      the private Enterprise runtime image returned
      `manifest unknown` on the new host during redeploy.
- [x] Repair upstream image publishing in `odoo-docker` and
      the private Enterprise layer so stable Odoo base tags refresh normally again.
      Repaired on 2026-04-07: `odoo-docker` push run `24046795441` and the next
      scheduled run `24065168743` both completed successfully after the publish
      timeout increase, serialized publish, pinned binfmt image, split
      `requirements.txt` copy, and registry-backed Buildx cache changes. The push
      run triggered the private Enterprise publish run `24060171498`, which refreshed the
      stable `19.0-runtime` and `19.0-devtools` tags, and the scheduled run
      triggered the private Enterprise nightly run `24078968346`. Further
      validation on 2026-04-08 confirmed the persistent per-runner Buildx path
      stayed healthy across additional real publishes: overnight scheduled run
      `24118708176` completed in about `40m 46s`, manual dispatch run
      `24139897875` succeeded but had a slow `runtime-devtools` publish while
      resolving Odoo source revision `35bc748256de...`, manual dispatch run
      `24150190511` on later source revision `f7c309cdac75...` returned to a
      normal `48m 10s` total, and the latest downstream enterprise publish
      `24152214947` succeeded.
- [x] Re-verify public/operator URL routing after NPMplus changes.
      Browser checks on 2026-04-05 confirmed Odoo and Dokploy non-prod domains are
      serving real apps. After regenerating Dokploy Traefik configs on
      `docker-shiny-nonprod`, `ver-prod.shinycomputers.com` and
      `ver-testing.shinycomputers.com` now serve the intended VeriReel app.
      Revalidated on 2026-04-08: `verireel.me` and `www.verireel.me` also load
      the live VeriReel site, so the front-door cutover follow-up is complete.

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
  2026-03-02.
- CM prod-gate backup dry-run and real backup both completed successfully on
  2026-04-08. The real run created snapshot
  `cm-predeploy-20260408-194712-codexcheck` and PBS archive
  `ct/200/2026-04-08T23:47:23Z`.
- `uv run platform dokploy inventory` on 2026-04-05 shows these targets now on
  `docker-shiny-nonprod`: `cm-repairshopr-sync`, `cm-dev`, `cm-testing`,
  `opw-dev`, and `opw-testing`.
- `uv run platform dokploy inventory --json-output` revalidated on 2026-04-08
  with all seven compose targets present and still mapped to the expected
  servers, including `docker-shiny-nonprod` for non-prod and the dedicated CM
  and OPW prod hosts.
- `uv run platform dokploy reconcile --json-output` revalidated clean again on
  2026-04-08 with `matched_targets: 6` and `updated_targets: 0`.
- Live browser checks on 2026-04-05 confirmed:
  `cm-dev.shinycomputers.com`, `cm-testing.shinycomputers.com`,
  `opw-dev.shinycomputers.com`, `opw-testing.shinycomputers.com`,
  `cm-prod.shinycomputers.com`, and `opw-prod.shinycomputers.com` served real
  app pages or login screens.
- `ver-prod.shinycomputers.com` and `ver-testing.shinycomputers.com` were
  repaired on 2026-04-05 by recreating the missing Dokploy Traefik application
  config files on `docker-shiny-nonprod`; local and public checks now return
  the live VeriReel app.
- Browser-visible checks on 2026-04-08 confirmed:
  `cm-dev.shinycomputers.com`, `cm-testing.shinycomputers.com`,
  `cm-prod.shinycomputers.com`, `opw-dev.shinycomputers.com`,
  `opw-testing.shinycomputers.com`, `opw-prod.shinycomputers.com`,
  `ver-testing.shinycomputers.com`, `ver-prod.shinycomputers.com`,
  `verireel.me`, and `www.verireel.me` all loaded real app or login pages.
- `opw-dev` also needed a post-move repair on 2026-04-05: the initial filestore
  copy was incomplete, and after restoring the full volume the remaining login
  page breakage came from stale `/web/assets/...` attachment rows that pointed
  at already-missing filestore blobs. Clearing the asset attachments forced
  Odoo to regenerate fresh frontend bundles and restored the styled login page.
