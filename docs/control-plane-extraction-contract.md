---
title: Control Plane Extraction Contract
---

Purpose

- Define the first concrete extraction contract between `odoo-ai` and the
  future private control-plane repo.
- Turn the roadmap into an implementation boundary that can be built without
  re-deciding ownership on every change.

When

- Before moving any more release, promotion, backup, or environment-inventory
  logic out of `odoo-ai`.

Sources of Truth

- `tools/platform/cli.py` - current operator entrypoints.
- `tools/platform/commands_release.py` - current `ship` orchestration.
- `tools/platform/release_workflows.py` - current `promote` and gate flow.
- `tools/platform/models.py` - Dokploy target models plus artifact identity and
  promotion record contracts.
- `tools/platform/release_contract.py` - helpers that translate current runtime
  inputs into artifact identity manifests and promotion records.
- `platform export-artifact-identity` - read-only export command for the typed
  artifact identity manifest.
- `platform handoff-artifact-identity` - cross-repo handoff command that
  persists the typed artifact manifest into `odoo-control-plane`.
- `platform export-promotion-record` - read-only export command for the typed
  promotion record used by the compatibility promote flow.
- `docs/control-plane-roadmap.md` - durable target-state decisions.
- `docs/tooling/platform-cli.md` - current operator contract.

Current State

- `odoo-ai` still owns both local DX and long-term remote operator workflows.
- `platform ship` currently does all of the following inside this repo:
  - resolve environment layers
  - load Dokploy target definitions
  - verify clean working tree state unless explicitly overridden
  - compute branch-sync source ref and source commit
  - mutate the managed target branch before deploy
  - trigger Dokploy deployment
  - run post-deploy update hooks
  - verify target health
- `platform promote` currently does all of the following inside this repo:
  - resolve source target branch and commit from Dokploy target definitions
  - optionally verify source environment health
  - run the production backup gate
  - delegate deployment by calling `platform ship` with the source commit

Current extraction progress:

- Phase 1: complete
  - typed artifact/promotion contracts are defined
  - `platform export-artifact-identity` exists
- Phase 2: in progress
  - `platform export-promotion-record` makes current promote checkpoints
    explicit without moving live deploy ownership yet
  - bootstrap and ownership docs are being tightened so repo creation does not
    reopen boundary questions
- Phase 3: next
  - create the private control-plane repo and start moving build/promotion
    ownership there behind thin compatibility wrappers

Current phase-3 progress:

- The private repo now exists as `odoo-control-plane`.
- `platform promote` is the first live compatibility handoff: `odoo-ai`
  performs Odoo-specific prechecks, then delegates promotion execution and
  promotion-record ownership to `odoo-control-plane`, which in turn delegates
  the underlying `ship` worker back to `odoo-ai` during the transition.
- `platform export-ship-request` now defines the first explicit ship handoff
  contract even though live `ship` ownership remains in `odoo-ai` for now.
- Artifact manifests can now be handed off explicitly into `odoo-control-plane`
  instead of remaining implied metadata in `odoo-ai` only.

Updated phase-4 progress:

- Public `platform ship` now delegates into `odoo-control-plane` as a
  fail-closed wrapper.
- The old `ship` executor no longer owns the live path. Public `ship` now
  hands off directly into `odoo-control-plane`.

Updated phase-5 progress:

- `odoo-control-plane` now persists first-class deployment records for
  compatibility `ship` execution before and after delegation.
- Live gate enforcement for public `platform ship` now runs in the thin
  `odoo-ai` handoff wrapper before the request crosses into
  `odoo-control-plane`.
- Public `platform ship` now also computes branch-sync planning before the
  handoff and includes that metadata in the request so the control plane owns
  the deploy intent record even while the transitional worker still performs
  the actual git push.
- Compatibility `ship` branch-sync application now runs from
  `odoo-control-plane` before delegation, and the internal worker only needs to
  accept the pre-applied branch-sync evidence instead of owning that git push
  itself.
- Compatibility `ship` destination health verification now also runs from
  `odoo-control-plane`, so the internal worker only needs to complete the
  delegated deploy and Odoo-specific post-deploy update path.
- Compatibility `ship` Dokploy target resolution now also runs from
  `odoo-control-plane`, so the control plane owns the exact target identity and
  timeout used for deployment.
- Compatibility `ship` now also executes Dokploy trigger/wait from
  `odoo-control-plane`, including Dokploy credential loading.
- Dokploy credentials are now expected to live with `odoo-control-plane`
  instead of piggybacking on `odoo-ai` local env files.
- The only remaining delegated runtime step is the Odoo-specific post-deploy
  update, which now goes through the canonical `platform update` path rather
  than a hidden compatibility worker.

Phase-One Goal

- Move the long-term release contract out of branch mutation and repo-local
  operator choreography.
- Replace implicit release inputs with an explicit artifact identity manifest
  plus promotion metadata.
- Leave `odoo-ai` owning code, local DX, and only the minimal metadata needed
  by the private repo.

## Artifact Identity Contract

The private control plane must treat a release artifact as the tuple below,
not as a branch name or a loose image tag.

- `odoo_ai_commit`
  - Exact public `odoo-ai` git commit SHA.
- `enterprise_base_digest`
  - Exact private `odoo-enterprise-docker` digest used in the build.
- `addon_sources`
  - Exact refs for any addon repositories included through
    `ODOO_ADDON_REPOSITORIES`.
- `openupgrade_inputs`
  - Exact `OPENUPGRADE_ADDON_REPOSITORY` and
    `OPENUPGRADELIB_INSTALL_SPEC` inputs.
- `build_flags`
  - Derived build-affecting values such as addon skip flags or equivalent
    switches that materially change the artifact.
- `image`
  - Final immutable private image digest and any `sha-*` style publish tag.

Required properties:

- The identity must be complete enough to reproduce the exact final image.
- The identity must be serializable as a manifest owned by the private repo.
- Promotions must reference the manifest or its immutable artifact identifier,
  not a mutable branch.

## Promotion Metadata Contract

Every promotion record must capture enough evidence to explain what was moved,
why it was allowed, and what happened after deploy.

Required fields:

- `artifact_identity`
  - Reference to the full artifact identity manifest.
- `context`
  - For example `cm` or `opw`.
- `from_instance`
  - Source environment such as `testing`.
- `to_instance`
  - Destination environment such as `prod`.
- `source_health`
  - Whether source health was verified, which URLs were checked, and result.
- `backup_gate`
  - Whether the required backup gate ran, its evidence, and result.
- `deploy`
  - Deployment target, deployment id, deploy mode, timestamps, and result.
- `post_deploy_update`
  - Whether the Odoo update hook ran and its result.
- `destination_health`
  - Health verification URLs, timeout, and result.

Required properties:

- Promotion records must stand alone as audit evidence.
- Backup gate evidence must be first-class metadata, not hidden in logs.
- Post-deploy update status must remain explicit even if the deploy succeeds.

## Ownership Split

What stays in `odoo-ai`:

- Shared and tenant addon code.
- Thin wrapper addons.
- Local runtime DX.
- Odoo-specific tests and validation scenarios.
- Minimal metadata that the private control plane consumes.

What moves to the private control-plane repo:

- Final app-image build orchestration.
- Immutable artifact publishing.
- Promotion orchestration.
- Backup and restore orchestration.
- Environment inventory as an operator surface.
- Dokploy deploy and rollout control.

What may remain temporarily as transitional compatibility:

- Thin `uv run platform ...` compatibility commands that forward to the private
  repo contract.
- Read-only diagnostics that help local development or emergency debugging.

## Current Command Mapping

The current remote operator surface in `odoo-ai` should be split as follows.

- `platform ship`
  - Long-term owner: private control plane.
  - Transitional state: optional compatibility wrapper only.
- `platform promote`
  - Long-term owner: private control plane.
  - Transitional state: optional compatibility wrapper only.
- `platform rollback`
  - Long-term owner: private control plane.
  - Transitional state: wrapper or explicitly unsupported until parity exists.
- `platform gate`
  - Long-term owner: shared between code repo validation and private release
    workflows, depending on gate type.
- `platform restore` and `platform bootstrap`
  - Long-term owner: private control plane for remote targets.
  - Local-only helpers may remain in `odoo-ai`.
- `platform doctor`, `platform validate`, `platform odoo-shell`, `platform up`,
  `platform down`, and similar local DX commands
  - Long-term owner: `odoo-ai`.

## First Private Repo Bootstrap

The first private repo slice should be intentionally narrow.

Minimum command surface:

- `build`
  - Build the final private artifact from explicit inputs.
- `promote`
  - Promote an existing artifact between environments.
- `inventory`
  - Report environments, artifacts, and recent deployment state.
- `backup`
  - Trigger or verify the required backup gate.
- `deploy-status`
  - Report deploy result and health evidence.

Minimum persisted records:

- Artifact identity manifest.
- Promotion records.
- Environment inventory records.
- Backup evidence records.

Planned sequence:

- Finish phase 2 inside `odoo-ai` by making artifact and promotion exports
  explicit and by freezing the bootstrap boundary.
- Start phase 3 by creating the private repo only after those read-only
  contracts are accepted, so the new repo begins from stable persisted record
  shapes instead of log-parsing or branch-coupled behavior.

## Transitional Rules

- Do not add more long-term deploy ownership to `odoo-ai`.
- New release-sensitive fields must be added to the explicit artifact or
  promotion contract, not inferred later from logs.
- If a private-repo feature is not ready, fail closed instead of silently
  preserving branch-coupled behavior as the durable solution.

## Exit Criteria

Phase one is complete when:

- The artifact identity manifest schema is written and accepted.
- The promotion metadata schema is written and accepted.
- Every current remote release command is classified as stay, move, or
  transitional.
- The private repo bootstrap shape is clear enough to start implementation
  without reopening core boundary questions.

Related Docs

- [@docs/control-plane-bootstrap-layout.md](control-plane-bootstrap-layout.md)
- [@docs/control-plane-roadmap.md](control-plane-roadmap.md)
- [@docs/tooling/platform-cli.md](tooling/platform-cli.md)
- [@docs/tooling/image-contracts.md](tooling/image-contracts.md)
