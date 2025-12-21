# Migration Patterns (Odoo 18)

Key changes

- List views: use `<list>` (not `<tree>`) as the root element for list views.
- View attrs/states: replaced by direct attributes `invisible`, `readonly`, `required`; use `column_invisible` for list
  columns.
- JavaScript: prefer native ES modules; avoid adding new `odoo.define` modules; do not add `/** @odoo-module */` to new
  ESM files.

Process

- Inventory current views/models for deprecated constructs; plan small batches.
- Migrate XML views to `<list>` and direct attributes; verify with view loader and UI.
- Migrate JS to ESM incrementally; keep components small and testable.
- Run scoped inspections/tests after each batch; run full gate before merge.

References

- docs/odoo/workflow.md, docs/style/javascript.md
