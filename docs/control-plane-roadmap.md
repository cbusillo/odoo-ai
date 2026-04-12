---
title: Control Plane Roadmap
---

Purpose

- Capture the durable long-term platform direction so deployment work can move
  forward without reopening the core architecture each turn.

When

- Before changing deployment, release, environment, or addon-ownership
  boundaries.

Pivot Status

- The older monorepo-centered roadmap in this repo is no longer the intended
  end state.
- The active DX-first retirement pivot is documented in the local planning note
  `/Users/cbusillo/.codex/plans/odoo-dx-repo-pivot-detailed.md`.
- Treat any remaining "keep the addon monorepo" wording in older docs as
  transitional or stale unless it is explicitly called out as migration-only.
- This roadmap now records the intended repository boundaries during the
  retirement of `odoo-ai`, even where implementation is still in flight.

Target State

- `odoo-ai` is retired after code, tooling, and docs ownership are extracted to
  their native homes.
- `odoo-devkit` owns shared DX, workspace assembly, runtime/tooling helpers,
  and the shared operator/developer guidance surface.
- `odoo-shared-addons` owns reusable cross-client addon code.
- tenant repos such as `odoo-tenant-opw` and `odoo-tenant-cm` own tenant
  addons and thin tenant entrypoint addons.
- `odoo-docker` remains the public Odoo base image contract.
- A private Enterprise image layer remains outside public repos and docs.
- A separate private control-plane repo owns build, deploy, promotion,
  backup/restore orchestration, environment inventory, and the operator UI.
- Dokploy remains the runtime substrate and should become a boring executor,
  not the center of day-to-day operator work.

Repository Boundaries

- `odoo-ai`
    - Transitional migration workspace only.
    - May temporarily host compatibility wrappers, migration notes, or still-
      live surfaces that have not been extracted yet.
    - Must not be treated as the durable long-term home for addon ownership,
      shared tooling, or operator workflows.
- `odoo-devkit`
    - Public repo.
    - Owns shared DX, manifest-driven workspace assembly, shared runtime
      tooling, and the shared AGENTS/docs surface.
- `odoo-shared-addons`
    - Public repo.
    - Owns reusable shared addon code.
- tenant repos
    - Public repos.
    - Own tenant-specific addon code, tests, and thin tenant-facing docs.
- private Enterprise image layer repo
    - Private repo.
    - Owns the licensed Enterprise layer and private image publishing.
- control-plane repo
    - Private repo.
    - Builds the final application image from exact tenant/shared/devkit refs,
      a pinned private Enterprise layer digest, and the exact addon/runtime
      inputs used by the release pipeline.
    - Publishes private immutable artifacts.
    - Promotes environments by artifact, not by environment-branch mutation.
    - Owns backup, restore, refresh, and Dokploy integration workflows.
    - Owns Dokploy target metadata and the deploy target source-of-truth.
    - Owns the operator UI.

Release Contract

- Build the final application image in private infrastructure from the exact
  public repo/ref tuple, the exact private Enterprise layer digest used for the
  Enterprise layer, and the exact addon/runtime inputs used by the release
  pipeline.
- Publish only to a private registry because the final image contains
  Enterprise code transitively.
- Promote the same image digest or immutable `sha-*` tag across environments,
  and record the full build input set in promotion metadata, including
  `ODOO_ADDON_REPOSITORIES`, `OPENUPGRADE_ADDON_REPOSITORY`,
  `OPENUPGRADELIB_INSTALL_SPEC`, and any derived addon-skip flags that alter
  the build.
- Keep Odoo-specific post-deploy update hooks, but run them after artifact
  deployment instead of coupling them to the historical branch-sync deploy
  flow.

Addon Ownership Layout

- `odoo-shared-addons`
    - Reusable cross-client addons.
- `odoo-tenant-<client>`
    - Client-specific supporting addons, exceptions, and thin tenant entrypoint
      addons.

Ownership Rules

- Shared addons must not depend on tenant-specific addons.
- Tenant addons may depend on shared addons.
- Wrapper addons should stay thin and primarily compose dependencies,
  configuration, menus, and views.
- When tenant logic becomes reusable, promote it into `odoo-shared-addons`.
- Shared infrastructure addons that apply cross-tenant runtime behavior (for
  example `environment_overrides`) may remain in `odoo-shared-addons` even if
  they are installed selectively by context or instance. Long term, prefer
  moving that behavior into native runtime or control-plane surfaces when the
  replacement can preserve the same fail-closed guarantees.

Control Plane UI Scope

- Environment inventory and health.
- Current code SHA and image per environment.
- Deploy and promotion history.
- Backup status.
- Promote testing to prod.
- Refresh non-prod from prod.
- Links or launch actions for logs and shell access.

Implementation Direction

1. Keep current local DX and image layering stable.
2. Extract shared DX/runtime/tooling ownership out of `odoo-ai` into
   `odoo-devkit` before splitting tenant code.
3. Split shared addons and tenant addons into their native repos, then retire
   `odoo-ai` instead of preserving it as a compatibility monorepo.
4. Keep exact-ref deployment on the control-plane artifact path rather than in
   `odoo-ai` branch-mutation workflows.
5. Make the UI the normal operator surface, with CLI as fallback.

Non-Goals

- Do not build a full self-hosted clone of Odoo.sh.
- Do not keep `odoo-ai` as a permanent compatibility shell after extraction.
- Do not flatten the `odoo-docker -> private Enterprise layer -> final
application image` layering while the current split continues to improve
  build speed and licensed-code isolation.
- Do not adopt Kubernetes just to make the architecture look cleaner.

Related Docs

- [@docs/ARCHITECTURE.md](ARCHITECTURE.md)
- [@docs/tooling/platform-cli.md](tooling/platform-cli.md)
- [@docs/tooling/image-contracts.md](tooling/image-contracts.md)
- [@docs/workflows/multi-project.md](workflows/multi-project.md)
