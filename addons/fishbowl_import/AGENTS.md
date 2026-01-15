# Fishbowl Import

Purpose

- Import Fishbowl entities into Odoo.
- This addon is transient for migration work and is expected to be removed once Fishbowl data is fully ingested.

Key Patterns

- Use `external.id.mixin` to link imported records to Fishbowl IDs.
- Keep imports idempotent; update existing records when external IDs match.
- Read config from `ir.config_parameter`, with env overrides when available.

Testing

- Targeted tests can be added under `addons/fishbowl_import/tests/`.

References

- @docs/odoo/orm.md
- @docs/odoo/security.md
