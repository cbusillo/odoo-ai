# Platform

Retired authority notice: this directory is archival. It is not live Odoo
runtime, deploy, restore, bootstrap, promotion, rollback, preview, Dokploy, or
secret-management authority. Use Launchplane for shared/testing/prod mutations
and durable runtime records, tenant repos for thin Launchplane workflows and
tenant addons, `odoo-devkit` for manifest-backed local runtime DX and artifact
handoff, and Odoo image repos for runtime image construction.

This directory holds the platform configuration and local secrets contract for
`uv run platform ...` workflows.

Start Here

- Operator workflows and command behavior:
  [@docs/tooling/platform-cli.md](../docs/tooling/platform-cli.md)
- Common invocation examples and workflow recipes:
  [@docs/tooling/platform-command-patterns.md](../docs/tooling/platform-command-patterns.md)
- Local compose layering and generated runtime files:
  [platform/config/README.md](config/README.md)
- Runtime topology and environment roles:
  [@docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)

Archived Files

- `ARCHIVE.md`: current quarantine note for this retired directory.
- `stack.toml`: historical snapshot of old contexts, instances, runtime tuning,
  and local runtime mapping.
- `dokploy.toml`: historical snapshot of old remote Dokploy targets, branches,
  domains, and release policy.
- `compose/base.yaml`: shared local compose overlay between
  `docker-compose.yml` and `docker-compose.override.yml`.
- `config/base.env`: shared local runtime defaults.
- `config/odoo.conf`: base Odoo config copied into `/volumes/config/`.
- `secrets.toml.example`: template for local `platform/secrets.toml`
  (gitignored).
- repo-root `.env.example`: minimal Dokploy credential and platform-key
  template.

Generated Files

- `.platform/env/<context>.<instance>.env`: resolved runtime environment for a
  selected stack.
- root `.env`: local file plus the managed block used for PyCharm Compose
  compatibility.

Historical Operator Contract Summary

These notes describe retired behavior and are not live operation guidance.
Use Launchplane for live shared/testing/prod mutation and `odoo-devkit` for
manifest-backed local runtime work.

- `local` is the only host runtime on this machine.
- Use `platform init`, `platform run`, `platform build`,
  `platform up`, `platform down`, `platform logs`, `platform inspect`, and
  `platform odoo-shell` only with `--instance local`.
- Treat `dev`, `testing`, and `prod` as Dokploy-managed remote targets.
  Use `platform ship`, `platform update`, `platform rollback`, `platform gate`,
  `platform promote`, `platform restore`, and `platform bootstrap` there.
- `platform ship` deploys and restarts remote code without replacing data, is
  the only supported deploy trigger for managed Dokploy targets, and when run
  with the default `--wait` behavior it follows the deploy with the shared
  module-update workflow before final health verification.
- `platform restore` replaces database and filestore state from upstream data.
- `platform bootstrap` clears database and filestore state, then builds a
  fresh runtime.
- `platform init` remains a local-only module initialization pass against an
  existing database.
- `platform update` applies module updates against the selected local or
  compose-backed managed runtime.

Historical Secrets and Env Notes

Do not recreate real secret files in this repo. Use Launchplane-owned secret
records for live targets and `odoo-devkit`/tenant-local non-secret manifests for
local runtime work.

- Historical template shape, for archive inspection only:

  ```bash
  cp platform/secrets.toml.example platform/secrets.toml
  ```

- Local env layering, collision handling, passthrough keys, `ODOO_KEY`
  provisioning behavior, and remote Dokploy env reconciliation are documented
  in [@docs/tooling/platform-cli.md](../docs/tooling/platform-cli.md).
- Deploy commands read Dokploy credentials from root `.env`
  (`DOKPLOY_HOST`, `DOKPLOY_TOKEN`).

Historical Working Pattern

This pattern is retained to understand old flows only.

- Use `platform select` to render `.platform/env/<context>.<instance>.env` for
  local stacks.
- Use a clean temporary worktree plus `platform ship --source-ref HEAD` for
  surgical remote deployment tests instead of `--allow-dirty` from a messy
  repo.
- Keep this README focused on file layout and contract; keep command details in
  [@docs/tooling/platform-cli.md](../docs/tooling/platform-cli.md).
