---
title: Secrets Layering
---

Purpose

- Document where secrets live and how precedence works for platform commands.

When

- When adding/changing credentials, runtime overrides, or Dokploy env keys.

Sources of Truth

- `platform/README.md` — runtime contract and generated env behavior.
- `tools/platform/environment.py` — env layering, collision detection, and
  merge order implementation.
- `platform/secrets.toml.example` — supported structure for local secrets file.

Setup

- `cp platform/secrets.toml.example platform/secrets.toml`
- Keep `platform/secrets.toml` untracked (gitignored) with real values only.

Layers

- Base env file: `.env` (or explicit `--env-file`).
- Shared secrets: `platform/secrets.toml` `[shared]`.
- Context secrets: `platform/secrets.toml` `[contexts.<context>.shared]`.
- Instance secrets: `platform/secrets.toml` `[contexts.<context>.instances.<instance>.env]`.

Notes

- `platform select` writes runtime env to
  `.platform/env/<context>.<instance>.env` and does not modify root `.env`.
- Set `PLATFORM_ENV_COLLISION_MODE=warn|error|ignore` to control collision
  handling.
- Dokploy remote targets are managed through `uv run platform dokploy ...`
  helpers and `platform/dokploy.toml` source-of-truth values.
