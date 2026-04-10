---
title: Control Plane Bootstrap Layout
---

Purpose

- Define the minimum file and ownership layout for the future private
  control-plane repo.
- Keep bootstrap scope intentionally narrow so the first repo can exist without
  pretending to be a full platform product on day one.

When

- Before creating the private repo or moving release orchestration out of
  `odoo-ai`.

Principles

- The first private repo should be CLI-first and record-first.
- UI work is allowed later, but the bootstrap repo must stand on its own with
  explicit artifacts, promotion records, and environment inventory.
- Dokploy remains an executor, not the architectural center.

## Minimum Top-Level Layout

```text
control-plane/
  README.md
  docs/
    architecture.md
    operations.md
    records.md
  control_plane/
    __init__.py
    cli.py
    contracts/
      artifact_identity.py
      promotion_record.py
      environment_inventory.py
    workflows/
      build.py
      promote.py
      backup.py
      inventory.py
    providers/
      dokploy.py
      registry.py
      github.py
    storage/
      manifests.py
      promotions.py
      inventory.py
  tests/
    test_build.py
    test_promote.py
    test_inventory.py
```

## First Commands

- `build`
  - Build the final private artifact from explicit inputs.
- `promote`
  - Promote an existing immutable artifact between environments.
- `inventory`
  - Report environment -> artifact state and recent deployment status.
- `backup`
  - Trigger or validate the required backup gate.
- `deploy-status`
  - Report deployment id, rollout status, and destination health.

## First Persisted Records

- Artifact identity manifests.
- Promotion records.
- Environment inventory snapshots.
- Backup evidence records.

## Ownership Boundary

Inputs consumed from `odoo-ai`:

- Artifact identity manifest export.
- Stable addon/release metadata.
- Local validation and code-level test signals when needed.

Owned inside the private repo:

- Final private image build orchestration.
- Artifact publishing.
- Promotion execution.
- Environment inventory and deployment history.
- Backup and restore orchestration.

## Phase-One Bootstrap Exit Criteria

- Repo can persist and read artifact manifests.
- Repo can persist and read promotion records.
- Repo can describe what artifact is running in each environment.
- Repo can trigger or at least model promotion without relying on branch names
  as the primary contract.

Related Docs

- [@docs/control-plane-extraction-contract.md](control-plane-extraction-contract.md)
- [@docs/control-plane-roadmap.md](control-plane-roadmap.md)
