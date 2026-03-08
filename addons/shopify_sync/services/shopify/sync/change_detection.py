from typing import Any

from odoo import models
from odoo.exceptions import UserError
from odoo.tools import float_compare, html_sanitize


def _normalize_html_for_comparison(value: str | None) -> str:
    return str(html_sanitize(value or "")).strip()


def changed_values(record: models.Model, vals: dict[str, Any]) -> dict[str, Any]:
    remaining_values = vals.copy()

    for field_name, new_value in list(remaining_values.items()):
        current_value = record[field_name]
        field = record._fields[field_name]

        if isinstance(new_value, (list, tuple)):
            raise UserError(f"write_if_changed(): unsupported value for field '{field_name}'. lists and tuples are not supported.")
        if isinstance(current_value, models.BaseModel):
            if len(current_value) > 1:
                raise UserError(
                    f"write_if_changed(): field '{field_name}' contains a multi‑record recordset which is not supported."
                )
            current_id = current_value.id if current_value else False
            new_id = new_value.id if isinstance(new_value, models.BaseModel) else new_value
            if current_id == new_id:
                remaining_values.pop(field_name)
            continue
        if isinstance(current_value, float):
            digits_specification = getattr(field, "digits", None)
            raw_digits = digits_specification(record.env) if callable(digits_specification) else digits_specification
            precision_digits = raw_digits[1] if isinstance(raw_digits, (list, tuple)) and len(raw_digits) > 1 else 2
            try:
                normalized_new_value = float(new_value)
            except (TypeError, ValueError) as error:
                raise UserError(
                    f"write_if_changed(): unsupported value for float field '{field_name}'."
                ) from error
            if float_compare(current_value, normalized_new_value, precision_digits=precision_digits) == 0:
                remaining_values.pop(field_name)
            continue
        if field.type == "html":
            normalized_current_value = _normalize_html_for_comparison(current_value)
            normalized_new_value = _normalize_html_for_comparison(new_value)
            if normalized_current_value == normalized_new_value:
                remaining_values.pop(field_name)
            continue
        if field.type in {"char", "text"}:
            normalized_current_value = current_value or ""
            normalized_new_value = new_value or ""
            if normalized_current_value == normalized_new_value:
                remaining_values.pop(field_name)
            continue
        if current_value == new_value:
            remaining_values.pop(field_name)

    return remaining_values


def write_if_changed(record: models.Model, vals: dict[str, Any]) -> bool:
    remaining_values = changed_values(record, vals)
    if remaining_values:
        record.with_context(skip_shopify_sync=True, force_sku_check=True).write(remaining_values)

    return bool(remaining_values)
