---
title: Roles
---


Purpose

- Define role expectations and outputs for Codex-driven work.

## Analyst (Research & Discovery)

Purpose: find patterns and authoritative guidance; return concise evidence.

When

- API/patterns are unfamiliar or canonical guidance is needed.

Inputs -> Outputs

- Inputs: brief + doc handles
- Outputs: Decision, Evidence (handles), Next steps, Risks

Doc handles (typical)

- @docs/odoo/orm.md, @docs/odoo/security.md, @docs/odoo/performance.md
- @docs/style/python.md, @docs/style/testing.md, @docs/odoo/workflow.md

Notes

- Prefer handles over excerpts; keep evidence minimal and sourced.

## Engineer (Implementation & Refactoring)

Purpose: apply minimal, focused changes that pass tests and inspections.

When

- Implementing features, fixing bugs, refactors.

Inputs -> Outputs

- Inputs: Decision, Evidence (handles), Intended diffs/paths, Acceptance
- Outputs: Diffs/Paths, Test results, Inspection results, Next steps

Doc handles (typical)

- @docs/workflows/codex-workflow.md#working-loop
- @docs/style/python.md, @docs/style/javascript.md
- @docs/odoo/orm.md, @docs/odoo/workflow.md

Notes

- Keep patches surgical; follow batching/performance guidance.

## Tester (Unit/JS/Integration/Tour)

Purpose: run fast, scoped tests in the loop; full run at gate.

When

- During development loops and before declaring done.

Inputs -> Outputs

- Inputs: modules/files changed
- Outputs: JSON summaries (success, counts), failing specs list

Doc handles

- @docs/tooling/testing-cli.md, @docs/style/testing.md

Notes

- Prefer module-scoped phases in the loop; run `test run --json` at the end.

## Reviewer (Inspection & Code Review)

Purpose: enforce zero-warning policy efficiently.

When

- After each meaningful change and at pre-commit.

Inputs -> Outputs

- Inputs: changed files or git diff base
- Outputs: findings (id, severity, file:line, message), resolution notes

Doc handles

- @docs/tooling/inspection.md, @docs/policies/acceptance-gate.md

Notes

- Use scope=changed during the loop; scope=git pre-commit; full inspection at gate.

## Maintainer (Release & Hygiene)

Purpose: keep branches healthy and docs current.

When

- Preparing releases, pruning profiles, updating ToC.

Checklist

- Acceptance gate passes on main branch.
- ToC updated with new/renamed topics and anchors.
- Obsolete profiles removed from ~/.codex/config.toml.

Branch/worktree hygiene

- Keep deploy branches (`cm-*`, `opw-*`).
- Remove merged or abandoned Code branches (local + origin).
- Prune stale worktrees and remote refs (`git worktree prune`,
  `git fetch --prune`).
