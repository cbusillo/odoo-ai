from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    """
    Set is_published=True for all products that are ready for sale.
    This ensures consistency after adding is_published to the Shopify export filter.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    products_to_fix = env["product.template"].search(
        [
            ("is_ready_for_sale", "=", True),
            ("is_published", "=", False),
            ("type", "=", "consu"),
            ("source", "in", ["import", "motor", "standard"]),
        ]
    )

    if products_to_fix:
        cr.execute(
            """
            UPDATE product_template 
            SET is_published = TRUE 
            WHERE id IN %s
        """,
            (tuple(products_to_fix.ids),),
        )

        env.cr.commit()
