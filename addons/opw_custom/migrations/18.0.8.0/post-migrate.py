"""Migration to backfill is_ready_for_sale_last_enabled_date field"""

import logging
from datetime import date

from odoo import SUPERUSER_ID, api, fields
from odoo.sql_db import Cursor

_logger = logging.getLogger(__name__)


def migrate(cr: Cursor, version: str) -> None:
    """
    Backfill is_ready_for_sale_last_enabled_date for existing products.

    This migration is needed because we changed from a computed field to a
    direct field update in the write() method.
    """
    if not version:
        return

    _logger.info("Starting migration to backfill is_ready_for_sale_last_enabled_date")

    env = api.Environment(cr, SUPERUSER_ID, {})

    # Find products that are ready for sale but missing the timestamp
    products_needing_backfill = env["product.template"].search(
        [("is_ready_for_sale", "=", True), ("is_ready_for_sale_last_enabled_date", "=", False)]
    )

    _logger.info(f"Found {len(products_needing_backfill)} products needing backfill")

    updated_count = 0
    failed_count = 0
    skipped_noisy_count = 0

    for product in products_needing_backfill:
        try:
            # Try to find the last tracking message for is_ready_for_sale
            tracking_messages = product.message_ids.filtered(
                lambda message: any(
                    tracking.field_id.name == "is_ready_for_sale" and tracking.new_value_integer == 1
                    for tracking in message.tracking_value_ids
                )
            ).sorted(lambda message: message.create_date, reverse=True)

            if tracking_messages:
                # Use the most recent tracking date
                backfill_date = tracking_messages[0].create_date
                backfill_source = "tracking"
            else:
                if product.create_date:
                    backfill_date = product.create_date
                    backfill_source = "create_date"
                else:
                    backfill_date = None
                    backfill_source = "missing"

            if not backfill_date:
                continue

            if backfill_source == "create_date":
                backfill_datetime = fields.Datetime.to_datetime(backfill_date)
                if backfill_datetime and backfill_datetime.date() in {date(2024, 2, 1), date(2024, 2, 2)}:
                    skipped_noisy_count += 1
                    continue

            _logger.debug(f"Product {product.default_code}: Using {backfill_source} {backfill_date}")

            # Update the field directly (bypass write method to avoid logic)
            cr.execute(
                "UPDATE product_template SET is_ready_for_sale_last_enabled_date = %s WHERE id = %s", (backfill_date, product.id)
            )
            updated_count += 1

        except Exception as e:
            _logger.error(f"Failed to backfill product {product.id} ({product.default_code}): {e}")
            failed_count += 1

    cr.execute(
        """
        SELECT COUNT(*)
        FROM product_template
        WHERE is_ready_for_sale = TRUE
          AND is_ready_for_sale_last_enabled_date IS NULL
        """
    )
    remaining_missing_count = cr.fetchone()[0]

    _logger.info(
        "Migration completed: "
        f"{updated_count} updated, {remaining_missing_count} remaining without a date, "
        f"{failed_count} failed, {skipped_noisy_count} skipped (noisy create_date)"
    )

    # Commit the changes
    cr.commit()
