# AGENTS.md — hr_employee_name_extended

Purpose

- Structured first/last/nickname fields on `hr.employee` with locale‑aware formatting and safe inverse writes.

Key Models/Fields

- `hr.employee` adds: `first_name`, `last_name`, `nick_name`, `name_format` (selection: western|asian|custom).
- `name`: stored compute + inverse; composes from parts; inverse parses back to parts.

Settings

- `res.config.settings`: `user_name_format` (default format) and `user_custom_name_pattern` (when custom).

Admin Tools

- Server Action `action_recompute_employee_names` → `env['hr.employee']._action_recompute_names()`.
- Menu: HR → Configuration → Recompute Employee Names.

Usage Notes

- Changing defaults doesn’t retro‑update records; use the server action to recompute in batches.
- Writing `employee.name` with a single token keeps the last name unchanged.

Tests

- See `tests/` for settings, inverse, per‑employee overrides, and bulk recompute cases.

References

- @docs/style/testing.md, @docs/odoo/orm.md
