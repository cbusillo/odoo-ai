# Refactor Safety

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
