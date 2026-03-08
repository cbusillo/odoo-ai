---
title: Inspections (JetBrains)
---


Purpose

- Define inspection scope and zero-warning expectations.

When

- During development loops and before merge.
- Use the MCP tooling; avoid manual ad-hoc linting unless needed.

When not to use

- Never skip inspections for touched files.

Scope and order

1. Loop: `changed`, then `git` before commit.
2. Gate: `full` (or all touched modules) before merge.

Test-Focused Cleanup Guidance

- When unresolved-reference warnings cluster inside addon test files, look at
  the owning addon's `tests/fixtures/base.py` before editing many individual
  tests.
- For addon test import surfaces, prefer one small `tests/common_imports.py`
  built from `build_common_imports(__package__, ...)` plus direct imports from
  `test_support` for generic fixtures/helpers.
- Prefer consuming that shared object directly in tests (`common.tagged`,
  `common.UNIT_TAGS`, `common.patch`) rather than re-exporting many names from
  each addon shim.
- Avoid addon-local pass-through wrappers such as `tests/base_types.py`,
  `tests/test_helpers.py`, or fixture modules that only re-export
  `test_support` unchanged.
- If the shared base attaches dynamic model aliases, add typed properties there
  when that cleanly teaches PyCharm the real model types.
- Keep addon-specific typed test helpers local to that addon. Do not move model-
  specific knowledge into `addons/test_support/` just to satisfy inspections.

Scopes

- changed — current edits and nearby lines.
- git — files changed since base (e.g., HEAD or origin/branch).
- full — project or modules.

Platform inspection context

- Run `uv run platform validate-config` before inspection runs.
- Run `uv run platform select --context <context> --instance local` before
  opening JetBrains inspections; this writes the runtime env and generated
  PyCharm Odoo config path for that context.
- The `odoo-ide` JetBrains plugin may not expose a dedicated config UI.
  Use the generated `pycharm_odoo_conf_file`
  (`.platform/ide/<context>.local.odoo.conf`) for run configurations or
  tooling that accepts an explicit `-c/--config` Odoo file path.
- Do not use `platform.odoo.conf` as a Docker Compose file; Compose targets
  should point at compose YAML files such as `docker-compose.yml` and
  `platform/compose/base.yaml`.
- Use `uv run platform inspect --context <context> --instance local` for
  JetBrains inspection runs.
