---
title: Debugging Workflow
---


Use this practical, repeatable flow for diagnosing issues without relying on CLI‑specific code blocks.

Core steps

- Parse the traceback: identify model, method, field, and error type.
- Gather context: container logs (Docker CLI), Odoo server logs, failing request details.
- Locate code: search for the failing method/field and related overrides/usages across modules.
- Inspect inheritance: confirm where behavior comes from (model inheritance chain, method overrides).
- Reproduce with a minimal input: write a focused test or a small shell snippet.
- Fix in small patches: run scoped inspections and targeted tests; iterate to clean; then run the full gate.

Tactics by category

- AttributeError/NoneType
    - Search for attribute access “.attr” in relevant models.
    - Check for missing None checks or optional relationships; add guards; write a unit test.
- UniqueViolation/IntegrityError
    - Find constraint definitions (_sql_constraints) and duplicate‑prevention code (search_count/domain).
    - Ensure transactionally safe checks; consider SQL constraints where applicable.
- OperationalError/DB connectivity
    - Use Docker CLI to check DB container status and logs; verify DSN and env; retry logic only where justified.
- AccessError/Record rules
    - Verify model ACLs and ir.rule domain logic; reproduce with a user fixture; avoid sudo unless justified.

Tools to use

- Code search: use Odoo Intelligence’s search capabilities, or ripgrep for quick, narrow lookups.
- Inspections: run scoped inspections (changed → git) to surface anti‑patterns or rule hits.
- Tests: run unit/JS tests for touched modules; run the full suite at the gate.

References

- Odoo: docs/odoo/orm.md, docs/odoo/security.md, docs/odoo/performance.md
- Testing: docs/style/testing.md, docs/style/testing-advanced.md
- Tooling: docs/tooling/inspection.md, docs/tooling/odoo-intelligence.md, docs/tooling/testing-cli.md
