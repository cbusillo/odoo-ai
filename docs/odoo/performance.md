---
title: Odoo ORM Performance Sources of Truth (18)
---


## Purpose

Keep ORM performance guidance concise and tied to real workflows.

## When

- Any time you touch batch operations, queries, or performance-sensitive flows.

## Sources of Truth

- `docs/odoo/orm.md` — batching, recordsets, computed fields.
- `docs/TESTING.md` — test guidance for perf regressions.

## Performance Review Workflow

1. Identify the hot path (traceback, logs, or slow operation).
2. Locate the code in `addons/*/models` or `addons/*/services`.
3. Check for N+1 patterns, repeated searches, or non-batched writes.
4. Apply a minimal fix; verify with scoped tests.
5. Run the full acceptance gate.

## Related Tooling

- `docs/tooling/db-tuning.md` — Postgres tuning for parallel test runs.
- `docs/TESTING.md` — fast -> full test flow.

## Related Guides

- `docs/odoo/workflow.md` — module layout and paths.
- `docs/roles.md` — review responsibilities and gate flow.
