from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

EBAY_CATEGORY_COLUMN = "ebay_category_id"
EBAY_CATEGORY_RESOURCE = "category"
EBAY_CONDITION_COLUMN = "ebay_condition_id"
EBAY_CONDITION_RESOURCE = "condition"


def migrate_product_type_ebay_category_external_ids(cr: Cursor) -> None:
    env = api.Environment(cr, SUPERUSER_ID, {})
    ebay_system = env["external.system"].ensure_system(
        code="ebay",
        name="eBay",
        id_format=r"^.+$",
        sequence=20,
        url="https://www.ebay.com",
        active=True,
        applicable_model_xml_ids=(
            "product_metadata.model_product_type",
            "product_metadata.model_product_condition",
        ),
    )
    external_id_model = env["external.id"].sudo().with_context(active_test=False)
    product_type_model = env["product.type"].sudo().with_context(active_test=False)
    product_condition_model = env["product.condition"].sudo().with_context(active_test=False)

    _migrate_model_column_to_external_ids(
        cr,
        model=product_type_model,
        external_id_model=external_id_model,
        system_id=ebay_system.id,
        table_name="product_type",
        column_name=EBAY_CATEGORY_COLUMN,
        resource=EBAY_CATEGORY_RESOURCE,
        model_name="product.type",
    )
    _migrate_model_column_to_external_ids(
        cr,
        model=product_condition_model,
        external_id_model=external_id_model,
        system_id=ebay_system.id,
        table_name="product_condition",
        column_name=EBAY_CONDITION_COLUMN,
        resource=EBAY_CONDITION_RESOURCE,
        model_name="product.condition",
    )


def _migrate_model_column_to_external_ids(
    cr: Cursor,
    *,
    model: "odoo.model.external_id_mixin",
    external_id_model: "odoo.model.external_id",
    system_id: int,
    table_name: str,
    column_name: str,
    resource: str,
    model_name: str,
) -> None:
    if not _column_exists(cr, table_name, column_name):
        return

    cr.execute(f"SELECT id, {column_name} FROM {table_name} WHERE {column_name} IS NOT NULL AND {column_name}::text != ''")
    for record_id, raw_external_id in cr.fetchall():
        normalized_external_id = str(raw_external_id).strip()
        if not normalized_external_id:
            continue
        record = model.browse(record_id).exists()
        if not record:
            continue

        conflicting_external_id = external_id_model.search(
            [
                ("system_id", "=", system_id),
                ("resource", "=", resource),
                ("external_id", "=", normalized_external_id),
            ],
            limit=1,
        )
        if (
            conflicting_external_id
            and conflicting_external_id.res_model == model_name
            and conflicting_external_id.res_id != record_id
            and conflicting_external_id.active
        ):
            raise RuntimeError(
                f"Unable to migrate {model_name}({record_id}) {resource} '{normalized_external_id}': "
                f"already mapped to {model_name}({conflicting_external_id.res_id})"
            )

        if not record.set_external_id("ebay", normalized_external_id, resource):
            raise RuntimeError(
                f"Unable to migrate {model_name}({record_id}) {resource} '{normalized_external_id}' into external_ids"
            )

    cr.execute(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS {column_name}")


def _column_exists(cr: Cursor, table_name: str, column_name: str) -> bool:
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = %s
           AND column_name = %s
         LIMIT 1
        """,
        (table_name, column_name),
    )
    return bool(cr.fetchone())
