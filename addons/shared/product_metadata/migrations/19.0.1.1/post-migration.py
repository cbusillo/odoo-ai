from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    from odoo.addons.product_metadata.migrations.product_type_external_identity import (
        migrate_product_type_ebay_category_external_ids,
    )

    migrate_product_type_ebay_category_external_ids(cr)
