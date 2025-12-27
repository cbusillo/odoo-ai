import logging

from odoo.sql_db import Cursor

_logger = logging.getLogger(__name__)


def migrate(cr: Cursor, version: str) -> None:
    # Count products to fix
    cr.execute("""
        SELECT COUNT(*) 
        FROM product_template 
        WHERE type = 'consu' 
        AND is_published = FALSE
    """)
    count_to_fix = cr.fetchone()[0]

    if count_to_fix:
        _logger.info(f"Fixing is_published for {count_to_fix} consumable products...")

        # Update all at once for better performance
        cr.execute("""
            UPDATE product_template 
            SET is_published = TRUE 
            WHERE type = 'consu' 
            AND is_published = FALSE
        """)

        # Flag ALL products with Shopify IDs for re-export to fix any status drift
        # This ensures ACTIVE/DRAFT status matches current inventory
        cr.execute("""
            UPDATE product_product 
            SET shopify_next_export = TRUE 
            WHERE shopify_product_id IS NOT NULL
            AND shopify_product_id != ''
            AND product_tmpl_id IN (
                SELECT id FROM product_template 
                WHERE type = 'consu'
                AND is_published = TRUE
                AND is_ready_for_sale = TRUE
            )
        """)

        shopify_count = cr.rowcount

        _logger.info(f"Migration complete: Fixed {count_to_fix} products, flagged {shopify_count} for Shopify export")
