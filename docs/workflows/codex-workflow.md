---
title: Codex Workflow
---


Purpose

- Define the default loop for safe, minimal changes.

When

- Before any code change and again before merge.

Working Loop

1) Plan: define smallest next change and acceptance.
2) Patch: minimal diffs only.
3) Inspect: scope=changed -> scope=git before commit.
4) Test: unit/js scoped to touched modules.
5) Iterate: repeat until clean.
6) Gate: full inspection + `uv run test run --json`.

Planning Notes

- Identify the smallest change that delivers value.
- Locate the existing model/view/service code to extend.
- List acceptance checks (inspection + tests).
- Batch work into small, reversible patches.

Odoo Development Principles

- Minimal viable change; batch ORM operations; avoid N+1 patterns.
- Respect access rules; default to safe security rules.
- Use context flags (for example `skip_shopify_sync=True`) when bulk updates
  would trigger sync loops.

Quality Review

- Run inspections (changed -> git) and fix all findings.
- Run targeted tests for touched modules.
- Verify security rules and access controls.
- Run the full acceptance gate before merge.

Notes

- Use separate Codex sessions for analysis vs implementation to keep context
  lean; pass document handles, not content.
