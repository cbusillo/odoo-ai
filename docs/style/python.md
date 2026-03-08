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
- Line length: 133 chars max (to match `pyproject.toml`).

Core Rules

- Type hints are required at API boundaries:
  all function/method signatures and public data shapes (`TypedDict`,
  dataclasses, Pydantic models, and other external-contract objects).
- Prefer type inference for local variables when the type is obvious.
- Add local annotations only when they materially improve clarity/tooling.
  Required: ambiguous empty containers and Odoo values payload dicts assigned
  to variables for PyCharm key/type validation.
  Optional: complex unions, third-party `Any` leaks, or ORM/SQL rows the IDE
  cannot infer cleanly.
  Do not introduce a variable solely for typing when an inline dict literal can
  be passed directly to `create(...)` or `write(...)`.
- f‑strings only; no `%` or `str.format()`.
- Use PEP 604 union syntax (`str | None`) instead of `Optional[str]`.
- Early returns encouraged to reduce nesting.
- Prefer small, single‑purpose functions and modules.
- Do not run Python directly; use Odoo env and `uv run` tasks.
- Descriptive naming: functions as verbs (e.g., `compute_margin`), variables
  as clear nouns; avoid cryptic abbreviations. Prefer code that obviates
  comments.
- DRY: extract helpers for repeated logic/queries; prefer composition over copy/paste.

Odoo Plugin “Magic Types” (PyCharm)

- Enable the Odoo plugin and use its provided types for precise hints:
  recordsets like `odoo.model.product_template`, values payloads like
  `odoo.values.sale_order`, and `odoo.api.Environment` when needed.
- Prefer the plugin's magic types over `cast(...)`. Use `cast(...)` only when
  no reasonable magic-type annotation exists.
- The plugin resolves recordset types from `self.env["..."]` without imports.
  Add explicit annotations only when inference is weak, readability improves,
  or values payload dicts need key/type validation.
- For reusable Odoo search domains, prefer `fields.Domain` over raw `list`
  aliases so `&` and `|` composition stays available.
- When a helper or parameter is already typed precisely enough, prefer
  inference for the receiving local variable.
- You can use magic types as string annotations directly; `TYPE_CHECKING`
  imports are optional.
- In tests, when shared fixture bases attach dynamic model aliases (for example
  `self.Partner`, `self.ExternalId`, `self.RepairshoprImporter`), prefer adding
  typed properties in the addon's `tests/fixtures/base.py` that return
  `self.env["..."]` over sprinkling suppressions or broad local casts through
  individual test files.

```python
def ensure_product_defaults(product: 'odoo.model.product_template') -> None:
    if not product.default_code:
        product.default_code = f"SKU-{product.id}"


def bulk_create(vals: 'odoo.values.product_templates') -> None:
    self.env['product.template'].create(vals)
```

```python
# Magic types can be used without imports.
# PyCharm resolves them through the Odoo plugin.
unit_model = self.env["uom.uom"].sudo().with_context(IMPORT_CONTEXT)

order_model: 'odoo.model.sale_order' = self.env["sale.order"].sudo()
order_vals: 'odoo.values.sale_order' = {
    "partner_id": partner.id,
    "state": "draft",
}
```

JetBrains `noinspection` Policy

- PyCharm Inspection Problems are the authoritative cleanup list for Python.
- Zero‑warning gate on touched files. Add `noinspection` only for confirmed
  tool false positives that cannot be fixed in code.
- Prefer typed fixture-base properties or narrower local annotations before
  suppressing repeated unresolved references in tests.
- Scope suppressions narrowly, include a one-line justification, and avoid
  blanket file-level suppressions.
- If the issue may be IDE/profile configuration rather than code, confirm with
  the operator before adding suppressions or typing workarounds.

```python
# noinspection PyTypeChecker
# False positive: Odoo plugin types refine recordset at runtime.
partner: 'odoo.model.res_partner' = self.env['res.partner'].browse(pid)
```

Typing Patterns (Recordsets & Domains)

```python
from odoo import fields
from typing import Iterable, TypedDict


class PartnerVals(TypedDict, total=False):
    name: str
    email: str
    company_id: int


def find_partners(self, domain: fields.Domain) -> 'odoo.model.res_partner':
    return self.env['res.partner'].search(domain)


def create_partners(self, vals_list: Iterable[PartnerVals]) -> 'odoo.model.res_partner':
    return self.env['res.partner'].create(list(vals_list))
```

Exceptions & Logging

- Raise specific Odoo exceptions (`ValidationError`, `AccessError`) for
  business rules and permissions.
- Log with `_logger` at the appropriate level (`info`, `warning`, `error`). No prints.

I/O, Dates, and Strings

- Use `pathlib.Path` for filesystem paths in utilities.
- Use timezone‑aware datetimes; prefer `fields.Datetime` within models.
- Always interpolate with f‑strings; escape external inputs where relevant.

Testing

- Put tests under `addons/<module>/tests/`.
- Keep fixtures small; prefer factories and shared helpers where available.
- Use the Testing CLI (`docs/tooling/testing-cli.md`) and require JSON success.

Anti‑Patterns

- Broad `except Exception` without re‑raise or logging.
- Silent pass in `except` blocks.
- Untyped public functions or method parameters.
- Blanket JetBrains suppressions.

Structured Settings

- When you need structured configuration outside of Odoo models, prefer
  Pydantic v2 `BaseModel` classes over manual `os.environ` parsing.
- Use the platform environment helpers (see `tools/platform/environment.py`) to
  load and layer `.env` plus `platform/secrets.toml` values instead of rolling
  a custom parser.
