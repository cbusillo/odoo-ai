---
title: Bulk Operations
---


Guidelines

- Prefer write in batch: `records.write({...})` instead of per-record writes.
- Use read_group for aggregation; avoid manual loops.
- Prefetch related fields before loops; avoid N+1.
- For massive changes, chunk work and commit at safe boundaries.

Verification

- Measure before/after where performance matters.
- Run scoped inspections and targeted tests per batch.
