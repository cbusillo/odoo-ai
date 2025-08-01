---
description: Run comprehensive quality control checks
argument-hint: "[module_name|changed|all]"
---

@docs/agents/qc.md

Run comprehensive quality control checks for pre-commit validation.

Scope: $ARGUMENTS (default: changed files)

Coordinate quality checks across multiple agents:

1. Code style and formatting violations
2. Odoo-specific patterns and anti-patterns
3. Performance bottlenecks (N+1 queries, missing indexes)
4. Test coverage assessment
5. Security and access control gaps
6. Generate consolidated report with fixes

If issues found, coordinate fixes through appropriate specialist agents.