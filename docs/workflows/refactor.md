---
title: Refactor Workflow
---


Purpose

- Provide a safe, repeatable workflow for refactors.

Phases

1) Analysis: identify hotpaths, deprecated patterns, and cross-file impacts.
2) Plan: group changes into safe batches; define acceptance checks.
3) Execute: small patches; run scoped inspections/tests after each batch.
4) Verify: full inspection and full test run before merge.

Checklist

- Create a checkpoint branch; ensure green tests before changes.
- Inspect dependencies and usages for touched models/fields/methods.
- Start with one small, reversible change; run scoped tests and inspections.
- Batch safely: prefer repetitive, mechanical edits with verification.
- Keep performance in mind (batch writes, prefetch, read_group).

Pre-flight

- Field changes: confirm compute/store/index impact; update search domains.
- View changes: validate XPath targets and view inheritance.
- Security: ensure ACLs/ir.rule remain correct.

Post-change

- Run inspection (changed → git); fix to zero.
- Run targeted tests; then full suite before merge.

Notes

- Prefer mechanical edits with automated verification.
- Avoid mixing unrelated changes in a single patch.
- Keep PRs small; easier to review and revert.
