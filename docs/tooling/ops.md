---
title: Ops CLI
---

Purpose

- Provide a single, UI-friendly command for the common OPW/CM workflows
  (local init/restore/up/down, branch shipping, prod gating).

Quick start

- Run the interactive menu:

  ```bash
  uv run ops
  ```

- Example shortcuts:

  ```bash
  uv run ops local init opw
  uv run ops local restore opw
  uv run ops local up all
  uv run ops local down all
  uv run ops local restart opw
  uv run ops local upgrade opw
  uv run ops local up opw --build --no-cache

  uv run ops ship testing opw
  uv run ops ship testing all
  uv run ops ship prod opw --confirm
  uv run ops ship testing opw --after restore

  uv run ops gate opw --confirm

  uv run ops status testing opw
  uv run ops status testing all --no-wait
  ```

Remembered choices

- The menu remembers your last selections in:
  `~/odoo-ai/ops.json`.
- Favorites are derived from recent usage and shown as quick picks.
- Interactive prompts use arrow keys when `questionary` is available; otherwise
  they fall back to typed prompts.
- Install `rich` + `questionary` with `uv sync --extra dev`.

Configuration

- Source of truth: `docker/config/ops.toml` (targets + Coolify host). Branches,
  app names, and local stack/env paths follow conventions by default. No secrets
  live in this file.

Conventions

- Local stack name: `{target}-local`.
- Local env file: `docker/config/{target}-local.env`.
- Branch names: `{target}-dev`, `{target}-testing`, `{target}-prod`.
- Coolify app names: `{target}-dev`, `{target}-testing`.

Targets & environments

- Targets: `opw`, `cm`, `all`.
- Environments: `local`, `dev`, `testing`, `prod`.

Behavior notes

- Local actions map to `uv run stack up/down` and use the stack env files
  (`docker/config/opw-local.env`, `docker/config/cm-local.env`).
- `ops local restart` performs a fast `docker compose restart web` for the
  target stack.
- `ops local upgrade` runs module upgrades using the stack's configured module
  list (AUTO by default) without rebuilding the image.
- `--no-cache` forces a clean local build; for `all`, only the first target
  uses `--no-cache` and the rest use normal cache.
- Ship actions push to the correct branch:
  - `opw-testing`, `cm-testing`, `opw-dev`, `cm-dev`, `opw-prod`, `cm-prod`.
- Ship actions for dev/testing can optionally run a post-deploy `restore` or
  `init` via Coolify post-deployment commands (requires `--wait`).
- Prod ship runs the prod gate first using `uv run prod-gate backup`.
- Prod actions require an explicit confirmation (interactive prompt or
  `--confirm` for non-interactive usage).
- For dev/testing, `ops ship` can optionally trigger Coolify deploys if
  `COOLIFY_TOKEN` is available in `.env` (default is off, since Coolify can
  auto-deploy on branch updates). Deploy waits are on by default; use `--no-wait`
  to skip.
- `ops status` uses the Coolify API and requires `COOLIFY_TOKEN` (waits by
  default; use `--no-wait`).
- For interactive runs, `uv run ops --no-wait` skips deploy waiting.
- Local actions default to `--no-build` for speed; pass `--build` to force a rebuild.
