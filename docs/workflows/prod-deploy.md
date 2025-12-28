---
title: Production Deploy Gate
---


This workflow keeps production deploys deliberate: run tests, take a full
Proxmox backup + snapshot, then deploy via Coolify. Rollbacks use snapshots.

## Required environment variables

Set these in your `.env` or shell before running the gate (prefix per client):

- `<PREFIX>_PROD_PROXMOX_HOST` (e.g., `OPW_PROD_PROXMOX_HOST=prox-main`)
- `<PREFIX>_PROD_PROXMOX_USER` (optional, defaults to `root`)
- `<PREFIX>_PROD_CT_ID` (LXC container ID)
- `<PREFIX>_PROD_BACKUP_STORAGE` (PBS storage name for `vzdump`)
- `<PREFIX>_PROD_BACKUP_MODE` (default `both`; options: `snapshot`, `vzdump`, `both`)
- `<PREFIX>_PROD_SNAPSHOT_PREFIX` (optional; default `<prefix>-predeploy`)

Example for OPW (commented):

```text
# OPW_PROD_PROXMOX_HOST=prox-main
# OPW_PROD_CT_ID=111
# OPW_PROD_BACKUP_STORAGE=pbs
# OPW_PROD_BACKUP_MODE=both
# OPW_PROD_SNAPSHOT_PREFIX=opw-predeploy
```

## Deploy flow (OPW example)

1) Run tests + backup gate:
   - `uv run prod-gate backup --target opw --run-tests`

2) Deploy in Coolify (prod app).

3) If rollback needed:
   - `uv run prod-gate list --target opw`
   - `uv run prod-gate rollback --target opw --snapshot <snapshot-name>`

## Notes

- `vzdump` provides the full CT backup (PBS). `pct snapshot` gives fast rollback.
- The gate intentionally does not auto-deploy; prod deploy stays manual.
