---
title: Performance Review Workflow
---


## Purpose

Keep performance review steps short and aligned with real code.

## Workflow

1. Identify the hot path (traceback, logs, or slow operation).
2. Locate the code in `addons/*/models` or `addons/*/services`.
3. Check for N+1 patterns, repeated searches, or non-batched writes.
4. Apply a minimal fix; verify with scoped tests.
5. Run the full acceptance gate.

## Sources of Truth

- `docs/odoo/performance.md` — performance pointers.
- `docs/workflows/bulk-operations.md` — batch safety.
- `docs/TESTING.md` — testing flow.
