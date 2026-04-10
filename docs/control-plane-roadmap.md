---
title: Control Plane Roadmap
---

Purpose

- Capture the durable long-term platform direction so deployment work can move
  forward without reopening the core architecture each turn.

When

- Before changing deployment, release, environment, or addon-ownership
  boundaries.

Target State

- `odoo-ai` remains the public code monorepo for shared addons, tenant addons,
  and thin tenant entrypoint addons.
- `odoo-docker` remains the public Odoo base image contract.
- `odoo-enterprise-docker` remains the private Enterprise image layer.
- A separate private control-plane repo owns build, deploy, promotion,
  backup/restore orchestration, environment inventory, and the operator UI.
- Dokploy remains the runtime substrate and should become a boring executor,
  not the center of day-to-day operator work.

Repository Boundaries

- `odoo-ai`
    - Public repo.
    - Owns shared and tenant addon code, tests, local DX, and minimal metadata
      needed by the control plane.
    - Does not own long-term production deploy orchestration, secrets-bearing
      build flows, or the operator control surface.
- `odoo-enterprise-docker`
    - Private repo.
    - Owns the licensed Enterprise layer and private image publishing.
- control-plane repo
    - Private repo.
    - Builds the final application image from an exact public `odoo-ai` SHA,
      a pinned private `odoo-enterprise-docker` digest, and the exact
      addon-source refs used by the release pipeline.
    - Publishes private immutable artifacts.
    - Promotes environments by artifact, not by environment-branch mutation.
    - Owns backup, restore, refresh, and Dokploy integration workflows.
    - Owns the operator UI.

Release Contract

- Build the final `odoo-ai` image in private infrastructure from the exact
  public commit SHA, the exact private `odoo-enterprise-docker` digest used
  for the Enterprise layer, and the exact addon-source refs used by the
  release pipeline.
- Publish only to a private registry because the final image contains
  Enterprise code transitively.
- Promote the same image digest or immutable `sha-*` tag across environments,
  and record the full build input set in promotion metadata, including
  `ODOO_ADDON_REPOSITORIES`, `OPENUPGRADE_ADDON_REPOSITORY`,
  `OPENUPGRADELIB_INSTALL_SPEC`, and any derived addon-skip flags that alter
  the build.
- Keep Odoo-specific post-deploy update hooks, but run them after artifact
  deployment instead of coupling them to branch-sync deploy flows.

Addon Ownership Layout

- `addons/shared/`
    - Reusable cross-client addons.
- `addons/<client>/`
    - Client-specific supporting addons and exceptions.
- `addons/<client>_custom/`
    - Thin tenant entrypoint addon kept visible at the root.

Ownership Rules

- Shared addons must not depend on tenant-specific addons.
- Tenant addons may depend on shared addons.
- Wrapper addons should stay thin and primarily compose dependencies,
  configuration, menus, and views.
- When tenant logic becomes reusable, promote it into `addons/shared/`.

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
2. Make artifact identity and promotion evidence exportable from `odoo-ai`
   before moving ownership.
3. Create the private control-plane repo once those read-only contracts and the
   bootstrap layout are stable enough to implement without reopening boundary
   questions.
4. Move long-term deploy and promotion logic out of `odoo-ai`.
5. Replace branch-sync deployment with private immutable artifact promotion.
6. Reduce `uv run platform ...` responsibilities inside `odoo-ai` to local DX,
   diagnostics, data workflows, and transitional compatibility helpers.
7. Make the UI the normal operator surface, with CLI as fallback.

Non-Goals

- Do not build a full self-hosted clone of Odoo.sh.
- Do not split the addon monorepo by client.
- Do not flatten the `odoo-docker -> odoo-enterprise-docker -> odoo-ai`
  layering while the current split continues to improve build speed and
  licensed-code isolation.
- Do not adopt Kubernetes just to make the architecture look cleaner.

Related Docs

- [@docs/ARCHITECTURE.md](ARCHITECTURE.md)
- [@docs/control-plane-extraction-contract.md](control-plane-extraction-contract.md)
- [@docs/tooling/platform-cli.md](tooling/platform-cli.md)
- [@docs/tooling/image-contracts.md](tooling/image-contracts.md)
- [@docs/workflows/multi-project.md](workflows/multi-project.md)
