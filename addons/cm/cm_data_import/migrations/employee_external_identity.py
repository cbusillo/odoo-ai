from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

from ..external_identity import (
    EMPLOYEE_EXTERNAL_SYSTEM_APPLICABLE_MODEL_XMLIDS,
    EMPLOYEE_EXTERNAL_SYSTEM_DEFAULTS,
)

EMPLOYEE_EXTERNAL_IDENTITY_COLUMNS = {
    "cm_data_timeclock_id": "timeclock",
    "cm_data_repairshopr_id": "repairshopr",
    "cm_data_discord_id": "discord",
}


def migrate_employee_identity_external_ids(cr: Cursor) -> None:
    env = api.Environment(cr, SUPERUSER_ID, {})
    existing_columns = _filter_existing_columns(cr, "hr_employee", list(EMPLOYEE_EXTERNAL_IDENTITY_COLUMNS))
    if not existing_columns:
        return

    employee_model = env["hr.employee"].sudo().with_context(active_test=False)
    external_id_model = env["external.id"].sudo().with_context(active_test=False)
    external_system_model = env["external.system"]
    rows = _fetch_employee_identity_rows(cr, existing_columns)

    for row in rows:
        employee_id = _coerce_employee_id(row[0])
        if employee_id is None:
            continue
        employee_record = employee_model.browse(employee_id).exists()
        if not employee_record:
            continue
        row_values = row[1:]
        for column_name, raw_value in zip(
            existing_columns,
            row_values,
            strict=len(existing_columns) == len(row_values),
        ):
            normalized_external_id = _normalize_external_id_value(raw_value)
            if not normalized_external_id:
                continue
            system_code = EMPLOYEE_EXTERNAL_IDENTITY_COLUMNS[column_name]
            defaults = EMPLOYEE_EXTERNAL_SYSTEM_DEFAULTS[system_code]
            system = external_system_model.ensure_system(
                code=system_code,
                name=defaults["name"],
                id_format=defaults["id_format"],
                sequence=defaults["sequence"],
                url=defaults["url"],
                active=True,
                applicable_model_xml_ids=EMPLOYEE_EXTERNAL_SYSTEM_APPLICABLE_MODEL_XMLIDS,
            )
            conflicting_external_id = external_id_model.search(
                [
                    ("system_id", "=", system.id),
                    ("resource", "=", "default"),
                    ("external_id", "=", normalized_external_id),
                ],
                limit=1,
            )
            if (
                conflicting_external_id
                and conflicting_external_id.res_model == "hr.employee"
                and conflicting_external_id.res_id != employee_id
                and conflicting_external_id.active
            ):
                raise RuntimeError(
                    f"Unable to migrate {column_name}='{normalized_external_id}' for hr.employee({employee_id}): "
                    f"already mapped to hr.employee({conflicting_external_id.res_id})"
                )
            if not employee_record.set_external_id(system_code, normalized_external_id):
                raise RuntimeError(
                    f"Unable to migrate {column_name}='{normalized_external_id}' for hr.employee({employee_id}) into external_ids"
                )

    _drop_legacy_employee_identity_columns(cr, existing_columns)


def _filter_existing_columns(cr: Cursor, table_name: str, column_names: list[str]) -> list[str]:
    if not column_names:
        return []
    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_name = %s
           AND column_name = ANY(%s)
        ORDER BY ordinal_position
        """,
        (table_name, column_names),
    )
    return [column_name for (column_name,) in cr.fetchall()]


def _fetch_employee_identity_rows(cr: Cursor, column_names: list[str]) -> list[tuple[object, ...]]:
    if not column_names:
        return []
    where_clause = " OR ".join([f"{column_name} IS NOT NULL AND {column_name}::text != ''" for column_name in column_names])
    cr.execute(f"SELECT id, {', '.join(column_names)} FROM hr_employee WHERE {where_clause}")
    return cr.fetchall()


def _normalize_external_id_value(raw_value: object) -> str:
    if raw_value is None:
        return ""
    return str(raw_value).strip()


def _coerce_employee_id(raw_value: object) -> int | None:
    if isinstance(raw_value, bool):
        return None
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, str):
        normalized_value = raw_value.strip()
        if not normalized_value:
            return None
        return int(normalized_value)
    return None


def _drop_legacy_employee_identity_columns(cr: Cursor, column_names: list[str]) -> None:
    if not column_names:
        return
    drop_clauses = ", ".join([f"DROP COLUMN IF EXISTS {column_name}" for column_name in column_names])
    cr.execute(f"ALTER TABLE hr_employee {drop_clauses}")
