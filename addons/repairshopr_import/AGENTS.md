# RepairShopr Import

Purpose

- Import RepairShopr entities into Odoo using the `repairshopr_api` client.
- This addon is transient for migration work and is expected to be removed once RepairShopr data is fully ingested.

Key Patterns

- Use `external.id.mixin` to link imported records to RepairShopr IDs.
- Keep imports idempotent; update existing records when external IDs match.
- Read config from `ir.config_parameter`, with env overrides when available.

Testing

- Targeted tests can be added under `addons/repairshopr_import/tests/`.

References

- @docs/odoo/orm.md
- @docs/odoo/security.md
