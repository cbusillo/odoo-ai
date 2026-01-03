---
title: Refactor Workflows
---


Phases

1) Analysis: identify hotpaths, deprecated patterns, and cross-file impacts.
2) Plan: group changes into safe batches; define acceptance checks.
3) Execute: small patches; run scoped inspections/tests after each batch.
4) Verify: full inspection and full test run before merge.

Notes

- Prefer mechanical edits with automated verification.
- Avoid mixing unrelated changes in a single patch.
- Keep PRs small; easier to review and revert.
