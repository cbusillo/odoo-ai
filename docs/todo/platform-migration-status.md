---
title: Platform Migration Status
---

Purpose

- Track the durable follow-up work for the platform-first Dokploy migration.

Status

- Updated on 2026-04-12.
- Code/documentation migration is complete.
- Platform/tooling validation is complete (acceptance gates, local health, and
  Dokploy reconcile are green).
- No external blockers remain before final sign-off.
- Dokploy non-prod workloads were moved off the Dokploy control-plane host onto
  `docker-shiny-nonprod` (`192.168.1.36`) on 2026-04-05.
- Manifest-driven runtime ownership for extracted-tenant runtime now
  lives in `odoo-devkit`. On 2026-04-12, `odoo-ai` retired its repo-local
  local-runtime CLI lifecycle surface (`select`, `up`, `down`, `logs`,
  `build`, `odoo-shell`, and `inspect`) into explicit fail-closed migration
  shims that point operators at `odoo-devkit` plus tenant `workspace.toml`.
  Later that same day, `odoo-ai` also retired its direct repo-local
  `init`/`update`/`openupgrade` commands into matching manifest-backed handoff
  shims and narrowed `platform run` / `platform tui` so those local-only
  workflows are no longer reachable there either. Later on 2026-04-12,
  `odoo-ai` also retired repo-local local `restore`/`bootstrap` invocations
  into matching manifest-backed handoff guidance. On 2026-04-12, the surviving
  remote `restore`/`bootstrap` surface was retired as well, so those
  destructive flows now hand off to `odoo-devkit` runtime commands with the
  tenant manifest plus an explicit runtime `--instance` override. Later on
  2026-04-12, `odoo-devkit` also grew native manifest-backed `runtime logs`
  and `runtime psql` helpers for local debugging so common stack-bound
  validation no longer needs raw `docker compose` commands. Later that same
  day, `odoo-devkit` also gained a native manifest-backed
  `runtime odoo-shell` helper, and the retired `odoo-ai` shell shim now points
  at that command instead of treating shell access as homeless. Later that same
  day, `odoo-devkit` also gained a native manifest-backed `runtime down`
  helper, and the retired `odoo-ai` down shim now points at that command too.
  Later that same day, `odoo-devkit` also gained a native manifest-backed
  `runtime build` helper, and the retired `odoo-ai` build shim now points at
  that command as well.
- The extracted tenant proof now exists for both `odoo-tenant-opw` and
  `odoo-tenant-cm`: their tracked `workspace.toml` manifests drive
  `odoo-devkit` workspace/runtime commands, reusable shared addons now live in
  `odoo-shared-addons`, and the extracted tenant repos now target the flat
  tenant addon root (`sources/tenant/addons`) plus `sources/shared-addons`.
- Quarantine validation on 2026-04-12 proved that extracted tenant manifest
  and workspace flows do not require a live `odoo-ai` checkout: after a
  temporary local rename of the `odoo-ai` folder, both tenant manifests still
  resolved cleanly through `odoo-devkit`, and tenant `workspace status` /
  `runtime inspect` still worked. CM also passed a full quarantined
  `platform runtime up`, which bound tenant addons plus `odoo-shared-addons`
  without any `odoo-ai` mount. The one survivor was an old OPW materialized
  workspace symlink that still pointed at `odoo-ai/addons/shared`; re-running
  `platform workspace sync` rewired it to `odoo-shared-addons`.
- `odoo-ai` no longer carries its old repo-local `workspace.toml` overlay for
  the earlier OPW bucket layout. That migration seam was removed on 2026-04-12
  after extracted tenant manifests, workspace flows, and quarantined runtime
  validation proved the extracted repos no longer needed it.
- The old repo-local local-runtime helper implementation layer in `odoo-ai`
  was also removed on 2026-04-12 by deleting the now-dead
  `tools/platform/commands_selection.py` and
  `tools/platform/commands_lifecycle.py` modules after those commands were
  converted into retirement shims.

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

- [ ] Retire the remaining repo-local `uv run platform ...` workflow surfaces
      from `odoo-ai` after their final ownership moves into `odoo-devkit`, the
      tenant repos, or `odoo-control-plane`, then delete the obsolete
      compatibility docs/shims instead of preserving `odoo-ai` as a long-term
      host.
- [x] Expand the manifest-backed local operator helper surface in
      `odoo-devkit` to cover common stack-bound validation flows such as
      SQL/psql execution and structured log capture, so day-to-day debugging no
      longer falls back to raw `docker compose` commands. Completed on
      2026-04-12 with native `platform runtime logs` and
      `platform runtime psql` commands in `odoo-devkit`.
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
