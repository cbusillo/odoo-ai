# Platform

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

Files

- `stack.toml`: source of truth for contexts, instances, runtime tuning, and
  local runtime mapping.
- `dokploy.toml`: source of truth for remote Dokploy targets, branches,
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

Operator Contract Summary

- `local` is the only host runtime on this machine.
- Use `platform init`, `platform update`, `platform run`, `platform build`,
  `platform up`, `platform down`, `platform logs`, `platform inspect`, and
  `platform odoo-shell` only with `--instance local`.
- Treat `dev`, `testing`, and `prod` as Dokploy-managed remote targets.
  Use `platform ship`, `platform rollback`, `platform gate`,
  `platform promote`, `platform restore`, and `platform bootstrap` there.
- `platform ship` deploys and restarts remote code without replacing data.
- `platform restore` replaces database and filestore state from upstream data.
- `platform bootstrap` clears database and filestore state, then builds a
  fresh runtime.
- `platform init` remains a local-only module initialization pass against an
  existing database.

Secrets and Env Notes

- Create `platform/secrets.toml` from the template when needed:

  ```bash
  cp platform/secrets.toml.example platform/secrets.toml
  ```

- Local env layering, collision handling, passthrough keys, `ODOO_KEY`
  provisioning behavior, and remote Dokploy env reconciliation are documented
  in [@docs/tooling/platform-cli.md](../docs/tooling/platform-cli.md).
- Deploy commands read Dokploy credentials from root `.env`
  (`DOKPLOY_HOST`, `DOKPLOY_TOKEN`).

Working Pattern

- Use `platform select` to render `.platform/env/<context>.<instance>.env` for
  local stacks.
- Use a clean temporary worktree plus `platform ship --source-ref HEAD` for
  surgical remote deployment tests instead of `--allow-dirty` from a messy
  repo.
- Keep this README focused on file layout and contract; keep command details in
  [@docs/tooling/platform-cli.md](../docs/tooling/platform-cli.md).
