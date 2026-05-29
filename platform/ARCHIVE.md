# Retired Platform Archive

This directory is retained for historical reference only. It is not current
authority for Odoo runtime, deploy, restore, bootstrap, promotion, rollback,
preview, Dokploy, or secret-management work.

Current ownership:

- Launchplane owns shared/testing/prod mutations, durable runtime records,
  managed secret records, promotion, rollback, deploy orchestration, and preview
  lifecycle.
- Tenant repos own tenant addon code and thin Launchplane workflow calls.
- `odoo-devkit` owns manifest-backed local runtime DX and artifact handoff.
- Odoo image repos own base/runtime image construction.

Do not recreate `platform/secrets.toml` or use historical `platform/*.toml`
files as production input. If a historical value is still needed, re-enter it
through the current Launchplane-owned record or secret surface.
