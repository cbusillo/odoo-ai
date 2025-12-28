---
title: Tester (Unit/JS/Integration/Tour)
---


Purpose: run fast, scoped tests in the loop; full run at gate.

When

- During development loops and before declaring done.

Inputs → Outputs

- Inputs: modules/files changed
- Outputs: JSON summaries (success, counts), failing specs list

Doc handles

- @docs/tooling/testing-cli.md, @docs/style/testing.md

Notes

- Prefer module-scoped phases in the loop; run `test run --json` at the end.
