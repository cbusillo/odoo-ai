# CM Data Import

Purpose

- Import cm-data entities into Odoo for ongoing sync during migration.
- This addon is transient for migration work and is expected to be removed once cm-data is fully ingested.

Key Patterns

- Use `external.id.mixin` to link imported records to cm-data IDs.
- Keep imports idempotent; update existing records when external IDs match.
- Read config from `ir.config_parameter`, with env overrides when available.

Testing

- Targeted tests can be added under `addons/cm_data_import/tests/`.

References

- @docs/odoo/orm.md
