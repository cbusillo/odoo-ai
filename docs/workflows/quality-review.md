---
title: Quality Review Workflow
---


## Purpose

Keep quality checks aligned with real policies and tooling.

## Workflow

1. Run inspections (changed → git) and fix all findings.
2. Run targeted tests for touched modules.
3. Verify security rules and access controls.
4. Run the full acceptance gate before merge.

## Sources of Truth

- `docs/policies/acceptance-gate.md` — zero-warning gate.
- `docs/policies/coding-standards.md` — top-level rules.
- `docs/tooling/inspection.md` — inspection commands.
- `docs/workflows/testing-workflow.md` — test flow.
