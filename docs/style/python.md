---
title: Python Style
---


Purpose

- Define our house style for Python used in Odoo 19 projects and utilities.

When

- Any time you edit Python in this repo.

Targets & Tooling

- Python version and runtime baselines come from repo config (not this doc);
  see @docs/tooling/runtime-baselines.md for details.
- Lint/format with Ruff: run `uv run ruff format .` then `uv run ruff check --fix`.
- Line length: 133 chars max (to match AGENTS.md).

Core Rules

- Type hints are required at API boundaries:
    - All function/method signatures (parameters + return types, including `-> None` for procedures).
    - Public data shapes (`TypedDict`, dataclasses, Pydantic models) and other
      “external contract” objects.
- Prefer type inference for local variables when the type is obvious.
- Add local annotations only when they materially improve clarity/tooling (e.g.
  complex unions, containers, third-party `Any` leaks, or ORM/SQL rows where the
  IDE cannot infer types correctly). Favor annotations for ambiguous empty
  containers (e.g., `records: list[...] = []`).
- f‑strings only; no `%` or `str.format()`.
- Early returns encouraged to reduce nesting.
- Prefer small, single‑purpose functions and modules.
- Do not run Python directly; use Odoo env and `uv run` tasks.
- Descriptive naming: functions as verbs (e.g., `compute_margin`), variables as clear nouns; avoid cryptic
  abbreviations. Prefer code that obviates comments.
- DRY: extract helpers for repeated logic/queries; prefer composition over copy/paste.

Odoo Plugin “Magic Types” (PyCharm)

- Enable the Odoo plugin and use its provided types for precise hints:
    - Recordsets: `odoo.model.product_template`, `odoo.model.res_partner`.
    - Values payloads: `odoo.values.product_templates`, `odoo.values.sale_orders`.
    - Environment: `odoo.api.Environment` for `self.env` when needed.
- Prefer the plugin’s magic types over `cast(...)`. Avoid `cast(...)` unless there is no reasonable magic-type
  annotation available.
- The plugin resolves recordset types from `self.env["..."]` without extra imports. Use explicit annotations only
  when the IDE cannot infer the type (for example: empty `list`/`dict`/`set` initializers) or when it materially
  improves readability.
- You can use magic types as string annotations directly; `TYPE_CHECKING` imports are optional and only needed if
  you want autocomplete in non-Odoo tooling.

```python
def ensure_product_defaults(product: 'odoo.model.product_template') -> None:
    if not product.default_code:
        product.default_code = f"SKU-{product.id}"


def bulk_create(vals: 'odoo.values.product_templates') -> None:
    self.env['product.template'].create(vals)
```

```python
# Magic types can be used without imports; PyCharm resolves them through the Odoo plugin.
unit_model = self.env["uom.uom"].sudo().with_context(IMPORT_CONTEXT)

order_model: 'odoo.model.sale_order' = self.env["sale.order"].sudo()
order_vals: 'odoo.values.sale_order' = {
    "partner_id": partner.id,
    "state": "draft",
}
```

JetBrains `noinspection` Policy

- PyCharm Inspection Problems are the authoritative cleanup list for Python.
- Zero‑warning gate on touched files. Add `noinspection` only when 100% appropriate:
    - Always fix the root cause before suppressing. Use `noinspection` only for
      confirmed tool false positives that cannot be resolved in code.
    - Scope narrowly (single line or the smallest block possible).
    - Include a one‑line justification and a reference link if helpful. Keep
      the justification on the line before or after the `# noinspection` line;
      trailing comments on the `# noinspection` line can prevent PyCharm from
      honoring it.
    - Never add broad or file‑level blanket suppressions.
    - If it might be an IDE/profile configuration issue rather than a real code
      problem, confirm with the operator before suppressing or adding typing
      workarounds.

```python
# noinspection PyTypeChecker
# False positive: Odoo plugin types refine recordset at runtime.
partner: 'odoo.model.res_partner' = self.env['res.partner'].browse(pid)
```

Typing Patterns (Recordsets & Domains)

```python
from typing import Iterable, TypedDict


class PartnerVals(TypedDict, total=False):
    name: str
    email: str
    company_id: int


def find_partners(self, domain: list[tuple]) -> 'odoo.model.res_partner':
    return self.env['res.partner'].search(domain)


def create_partners(self, vals_list: Iterable[PartnerVals]) -> 'odoo.model.res_partner':
    return self.env['res.partner'].create(list(vals_list))
```

Exceptions & Logging

- Raise specific Odoo exceptions (`ValidationError`, `AccessError`) for business rules and permissions.
- Log with `_logger` at the appropriate level (`info`, `warning`, `error`). No prints.

I/O, Dates, and Strings

- Use `pathlib.Path` for filesystem paths in utilities.
- Use timezone‑aware datetimes; prefer `fields.Datetime` within models.
- Always interpolate with f‑strings; escape external inputs where relevant.

Testing

- Put tests under `addons/<module>/tests/`.
- Keep fixtures small; prefer factories and Scout helpers where available.
- Use the Testing CLI (`docs/tooling/testing-cli.md`) and require JSON success.

Anti‑Patterns

- Broad `except Exception` without re‑raise or logging.
- Silent pass in `except` blocks.
- Untyped public functions or method parameters.
- Blanket JetBrains suppressions.

Structured Settings

- When you need structured configuration outside of Odoo models, prefer Pydantic v2 `BaseModel` classes over manual
  `os.environ` parsing. They provide typing, validation, and consistent alias handling.
- Use the existing deploy helpers (see `tools/deployer/settings.py`) to merge `.env` files rather than rolling a custom
  parser; this ensures stack settings inherit defaults like `ODOO_STATE_ROOT` and keeps behavior consistent across
  tools.
