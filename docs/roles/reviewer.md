# Reviewer (Inspection & Code Review)

Purpose: enforce zero‑warning policy efficiently.

When

- After each meaningful change and at pre‑commit.

Inputs → Outputs

- Inputs: changed files or git diff base
- Outputs: findings (id, severity, file:line, message), resolution notes

Doc handles

- @docs/tooling/inspection.md, @docs/policies/acceptance-gate.md

Notes

- Use scope=changed during the loop; scope=git pre‑commit; full inspection at gate.
