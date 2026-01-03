---
title: Acceptance Gate (Zero‑Warning + Full Tests)
---


Purpose

- Define the minimum bar for merge readiness.

When

- Before merging to shared branches or shipping.

Definition of Done

- Zero findings from inspection (errors, warnings, weak_warnings, infos) on
  touched scope -> then full scope.
- Full `uv run test run --json` success across all phases.

Loop vs Gate

- Loop: run inspection `scope=changed`, then `scope=git` before commit; run
  scoped tests per touched modules.
- Gate: run full inspection (or all touched modules) and full tests.

Notes

- Narrow suppressions only, with one-line justification and reference; no
  blanket suppressions.
