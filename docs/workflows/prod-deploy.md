---
title: Production Deploy Gate
---

Purpose

- Keep production deploys deliberate: run tests, take a pre-deploy backup
  (including Proxmox snapshot/vzdump where that infrastructure exists), then
  deploy via Dokploy. Rollbacks use the recorded backup path.

When

- Before production deploys.

Required environment variables

Set these in your `.env` or shell before running the gate (prefix per client):

- `<PREFIX>_PROD_PROXMOX_HOST` (e.g., `OPW_PROD_PROXMOX_HOST=prox-main`)
- `<PREFIX>_PROD_PROXMOX_USER` (optional, defaults to `root`)
- `<PREFIX>_PROD_CT_ID` (LXC container ID)
- `<PREFIX>_PROD_BACKUP_STORAGE` (PBS storage name for `vzdump`)
- `<PREFIX>_PROD_BACKUP_MODE` (default `both`; options: `snapshot`, `vzdump`, `both`)
- `<PREFIX>_PROD_SNAPSHOT_KEEP` (optional; keep N snapshots with the prefix)
- `<PREFIX>_PROD_SNAPSHOT_PREFIX` (optional; default `<prefix>-predeploy`)

Example for OPW (commented):

```text
# OPW_PROD_PROXMOX_HOST=prox-main
# OPW_PROD_CT_ID=111
# OPW_PROD_BACKUP_STORAGE=pbs
# OPW_PROD_BACKUP_MODE=both
# OPW_PROD_SNAPSHOT_KEEP=10
# OPW_PROD_SNAPSHOT_PREFIX=opw-predeploy
```

Deploy flow (OPW example)

1. Run tests + backup gate:
    - `uv run prod-gate backup --target opw --run-tests --control-plane-record-dir tmp/prod-gates`

1. Persist the emitted backup-gate record into the control plane:
    - `uv run --project ../odoo-control-plane control-plane backup-gates write --input-file tmp/prod-gates/<record-id>.json`

1. Promote testing to prod with the control plane:

```bash
uv run --project ../odoo-control-plane control-plane promote resolve \
  --context opw --from-instance testing --to-instance prod \
  --artifact-id <artifact-id> --backup-record-id <record-id> > tmp/promotion-request.json
uv run --project ../odoo-control-plane control-plane promote execute \
  --input-file tmp/promotion-request.json
```

1. If rollback needed:
    - `uv run prod-gate list --target opw`
    - `uv run prod-gate rollback --target opw --snapshot <snapshot-name>`

Notes

- `vzdump` provides the full CT backup (PBS). `pct snapshot` gives fast rollback.
- `PROD_BACKUP_MODE=none` skips the snapshot/vzdump steps (tests still run),
  but it cannot emit a control-plane backup record because no backup evidence
  exists to promote, so the gate skips record emission in that mode.
- The gate intentionally does not auto-deploy; prod deploy stays manual.
- `odoo-control-plane` now owns Dokploy target resolution and waited post-
  deploy update execution natively, so promotion execution no longer needs an
  `odoo-ai` repo path.
- Explicit shell or workflow env values override repo `.env` defaults for
  `prod-gate`; use that to avoid accidental local default leakage in
  automation.
