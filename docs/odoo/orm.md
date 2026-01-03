---
title: Odoo ORM Sources of Truth (18)
---


## Purpose

Keep ORM guidance accurate by pointing to real code and authoritative docs.

## When

- Any time you touch Odoo models, recordsets, or ORM-heavy flows.

## Sources of Truth

- `addons/*/models/*.py` — real ORM usage in this repo.
- `docs/odoo/workflow.md` — module layout and container paths.
- `docs/odoo/performance.md` — performance review workflow.
- `docs/resources.md` — external Odoo ORM references.

## Batch Operations

- Prefer batch writes: `records.write({...})` instead of per-record writes.
- Use `read_group` for aggregation; avoid manual loops.
- Prefetch related fields before loops; avoid N+1.
- For massive changes, chunk work and commit at safe boundaries.

## Verification

- Measure before/after where performance matters.
- Run scoped inspections and targeted tests per batch.
